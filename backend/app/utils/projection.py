"""ROI and route-grid lat/lon <-> Lambert Conformal Conic, for map frames.

The map draws in LCC, the model forecasts in geographic coordinates, so every
frame is warped once here. Nearest-neighbour throughout: SIC is a categorical
field visually, and interpolating across the coastline would invent ice.

Two grids come through here and they mean different things:

* the **ROI grid** (``[101, 361]``) is what the forecaster emits;
* the **route grid** (``[185, 321]``) is the canvas those frames are painted
  on, so the PNG's extent covers the corridor instead of ending where the SIC
  data ends.

Both go through the same warp — only the source bounds and shape differ.
"""

from __future__ import annotations

import numpy as np
from affine import Affine
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from app.utils.constants import LCC_PROJ, ROI_CRS, ROI_SHAPE, ROUTE_SHAPE
from app.utils.grid import roi_bounds, route_bounds


def _boundary_lon_lat(
    bounds: tuple[float, float, float, float], samples_per_edge: int = 180
) -> tuple[np.ndarray, np.ndarray]:
    """Dense sample of a cell-edge rectangle boundary in degrees.

    Sampling the whole boundary (not just the four corners) matters: a conic
    projection bows the parallels, so an extreme can sit mid-edge.
    """
    west, south, east, north = bounds
    lon = np.concatenate(
        [
            np.linspace(west, east, samples_per_edge),
            np.full(samples_per_edge, east),
            np.linspace(east, west, samples_per_edge),
            np.full(samples_per_edge, west),
        ]
    )
    lat = np.concatenate(
        [
            np.full(samples_per_edge, south),
            np.linspace(south, north, samples_per_edge),
            np.full(samples_per_edge, north),
            np.linspace(north, south, samples_per_edge),
        ]
    )
    return lon, lat


def _lcc_bounds(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Projected ``(xmin, ymin, xmax, ymax)`` of a degree box in the LCC CRS."""
    lon, lat = _boundary_lon_lat(bounds)
    transformer = Transformer.from_crs(ROI_CRS, LCC_PROJ, always_xy=True)
    x, y = transformer.transform(lon, lat)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        raise RuntimeError("grid boundary did not project into the LCC CRS")
    return (
        float(np.min(x[finite])),
        float(np.min(y[finite])),
        float(np.max(x[finite])),
        float(np.max(y[finite])),
    )


def lcc_bounds() -> tuple[float, float, float, float]:
    """Projected ``(xmin, ymin, xmax, ymax)`` of the ROI in the LCC CRS (metres)."""
    return _lcc_bounds(roi_bounds())


def route_lcc_bounds() -> tuple[float, float, float, float]:
    """Projected ``(xmin, ymin, xmax, ymax)`` of the route grid (metres).

    This is the ``extent_lcc`` every SIC frame publishes: the canvas the PNG
    is painted on, not the SIC region inside it.
    """
    return _lcc_bounds(route_bounds())


def _lcc_grid(bounds: tuple[float, float, float, float], dst_width: int) -> dict:
    """Landing geometry for a warped frame over ``bounds``.

    The width is pinned to the grid's column count so the aspect ratio of the
    PNGs stays constant across runs; the height follows from the projected
    extent with square pixels.
    """
    if dst_width < 2:
        raise ValueError("dst_width must be at least 2")
    xmin, ymin, xmax, ymax = _lcc_bounds(bounds)
    x_res = (xmax - xmin) / float(dst_width)
    height = max(int(round((ymax - ymin) / x_res)), 1)
    transform = from_bounds(xmin, ymin, xmax, ymax, dst_width, height)
    return {
        "transform": transform,
        "width": dst_width,
        "height": height,
        "x_res": x_res,
        "extent": [xmin, ymin, xmax, ymax],
    }


def lcc_grid(dst_width: int = ROI_SHAPE[1]) -> dict:
    """Landing geometry for a warped ROI frame."""
    return _lcc_grid(roi_bounds(), dst_width)


def route_lcc_grid(dst_width: int = ROUTE_SHAPE[1]) -> dict:
    """Landing geometry for a warped route-grid frame."""
    return _lcc_grid(route_bounds(), dst_width)


def _reproject_to_lcc(
    array: np.ndarray,
    shape: tuple[int, int],
    bounds: tuple[float, float, float, float],
    dst_width: int,
    label: str,
) -> tuple[np.ndarray, list[float]]:
    """Warp a grid into LCC. Returns ``(lcc_array, extent)``.

    ``extent`` is ``[xmin, ymin, xmax, ymax]`` in projected metres. Cells that
    fall outside the source footprint stay NaN — they are rendered transparent
    downstream.

    The source transform is deliberately south-up: row 0 of every grid here is
    its southernmost row, but ``from_bounds`` would hand GDAL a north-up
    transform and quietly flip the frame upside down.
    """
    if array.shape != shape:
        raise ValueError(f"expected {label} shape {shape}, got {array.shape}")

    west, south, east, north = bounds
    x_res = (east - west) / float(shape[1])
    y_res = (north - south) / float(shape[0])
    # row 0 -> south, column 0 -> west.
    src_transform = Affine(x_res, 0.0, west, 0.0, y_res, south)

    grid = _lcc_grid(bounds, dst_width)
    dst = np.full((grid["height"], grid["width"]), np.nan, dtype=np.float32)

    reproject(
        source=np.ascontiguousarray(array, dtype=np.float32),
        destination=dst,
        src_transform=src_transform,
        src_crs=ROI_CRS,
        src_nodata=np.nan,
        dst_transform=grid["transform"],
        dst_crs=LCC_PROJ,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    return dst, grid["extent"]


def reproject_roi_to_lcc(array: np.ndarray, dst_width: int = ROI_SHAPE[1]) -> tuple[np.ndarray, list[float]]:
    """Warp a ``[101, 361]`` ROI frame into LCC.

    Kept for callers that want the raw model grid in projected space; the SIC
    display path warps the route canvas instead (see
    :func:`reproject_route_to_lcc`).
    """
    return _reproject_to_lcc(array, ROI_SHAPE, roi_bounds(), dst_width, "ROI")


def reproject_route_to_lcc(array: np.ndarray, dst_width: int = ROUTE_SHAPE[1]) -> tuple[np.ndarray, list[float]]:
    """Warp a ``[185, 321]`` route-grid canvas into LCC.

    The canvas carries the SIC region plus a NaN margin on every side, so the
    returned frame covers the corridor while everything outside the SIC grid
    comes back NaN — transparent once it reaches the PNG.
    """
    return _reproject_to_lcc(array, ROUTE_SHAPE, route_bounds(), dst_width, "route grid")
