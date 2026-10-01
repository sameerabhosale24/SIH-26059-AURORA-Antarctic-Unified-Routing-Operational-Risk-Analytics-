"""ROI lat/lon <-> Lambert Conformal Conic, for rendering the map frames.

The map draws in LCC, the model forecasts in geographic coordinates, so every
frame is warped once here. Nearest-neighbour throughout: SIC is a categorical
field visually, and interpolating across the coastline would invent ice.
"""

from __future__ import annotations

import numpy as np
from affine import Affine
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from app.utils.constants import LCC_PROJ, ROI_CRS, ROI_SHAPE
from app.utils.grid import roi_bounds


def _boundary_lon_lat(samples_per_edge: int = 180) -> tuple[np.ndarray, np.ndarray]:
    """Dense sample of the ROI cell-edge rectangle boundary in degrees.

    Sampling the whole boundary (not just the four corners) matters: a conic
    projection bows the parallels, so an extreme can sit mid-edge.
    """
    west, south, east, north = roi_bounds()
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


def lcc_bounds() -> tuple[float, float, float, float]:
    """Projected ``(xmin, ymin, xmax, ymax)`` of the ROI in the LCC CRS (metres)."""
    lon, lat = _boundary_lon_lat()
    transformer = Transformer.from_crs(ROI_CRS, LCC_PROJ, always_xy=True)
    x, y = transformer.transform(lon, lat)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        raise RuntimeError("ROI boundary did not project into the LCC CRS")
    return (
        float(np.min(x[finite])),
        float(np.min(y[finite])),
        float(np.max(x[finite])),
        float(np.max(y[finite])),
    )


def lcc_grid(dst_width: int = ROI_SHAPE[1]) -> dict:
    """Landing geometry for the warped frame.

    The width is pinned to the ROI column count so the aspect ratio of the
    PNGs stays constant across runs; the height follows from the projected
    extent with square pixels.
    """
    if dst_width < 2:
        raise ValueError("dst_width must be at least 2")
    xmin, ymin, xmax, ymax = lcc_bounds()
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


def reproject_roi_to_lcc(array: np.ndarray, dst_width: int = ROI_SHAPE[1]) -> tuple[np.ndarray, list[float]]:
    """Warp a ``[101, 361]`` ROI frame into LCC.

    Returns ``(lcc_array, extent)`` where ``extent`` is
    ``[xmin, ymin, xmax, ymax]`` in projected metres. Cells that fall outside
    the source footprint stay NaN — they are rendered transparent downstream.

    The source transform is deliberately south-up. ``roi_lat_array()`` puts
    row 0 at ``ROI_LAT_MIN`` (the southern edge) and every adapter writes
    its fields that way, but ``from_bounds`` would hand GDAL a north-up
    transform and quietly flip the frame upside down.
    """
    if array.shape != ROI_SHAPE:
        raise ValueError(f"expected ROI shape {ROI_SHAPE}, got {array.shape}")

    west, south, east, north = roi_bounds()
    x_res = (east - west) / float(ROI_SHAPE[1])
    y_res = (north - south) / float(ROI_SHAPE[0])
    # row 0 -> south, column 0 -> west.
    src_transform = Affine(x_res, 0.0, west, 0.0, y_res, south)

    grid = lcc_grid(dst_width)
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
