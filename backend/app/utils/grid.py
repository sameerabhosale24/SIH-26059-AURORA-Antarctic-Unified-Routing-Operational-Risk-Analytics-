"""Coordinate arrays for the ROI grid.

Single source of truth: nothing in AURORA is allowed to hand-roll a latitude
or longitude vector, because a half-cell mistake here is invisible until the
forecast lands in the wrong place.
"""

from __future__ import annotations

import math

import numpy as np

from app.utils.constants import (
    ROI_LAT_MAX,
    ROI_LAT_MIN,
    ROI_LON_MAX,
    ROI_LON_MIN,
    ROI_RES,
    ROI_SHAPE,
    ROUTE_RES,
    ROUTE_ROI_LAT_MAX,
    ROUTE_ROI_LAT_MIN,
    ROUTE_ROI_LON_MAX,
    ROUTE_ROI_LON_MIN,
    ROUTE_SHAPE,
)


def roi_lat_array() -> np.ndarray:
    """Latitude centres, shape ``[101]`` (float64), -75.125 .. -50.125."""
    n_rows = ROI_SHAPE[0]
    expected = round((ROI_LAT_MAX - ROI_LAT_MIN) / ROI_RES)
    if expected != n_rows:
        raise ValueError(
            f"ROI latitude bounds are inconsistent with ROI_SHAPE: "
            f"({ROI_LAT_MAX} - {ROI_LAT_MIN}) / {ROI_RES} = {expected}, "
            f"expected {n_rows}"
        )
    return ROI_LAT_MIN + np.arange(n_rows, dtype=np.float64) * ROI_RES


def roi_lon_array() -> np.ndarray:
    """Longitude centres, shape ``[361]`` (float64), -10.125 .. 79.875."""
    n_cols = ROI_SHAPE[1]
    expected = round((ROI_LON_MAX - ROI_LON_MIN) / ROI_RES)
    if expected != n_cols:
        raise ValueError(
            f"ROI longitude bounds are inconsistent with ROI_SHAPE: "
            f"({ROI_LON_MAX} - {ROI_LON_MIN}) / {ROI_RES} = {expected}, "
            f"expected {n_cols}"
        )
    return ROI_LON_MIN + np.arange(n_cols, dtype=np.float64) * ROI_RES


def roi_lat_lon_meshgrid() -> tuple[np.ndarray, np.ndarray]:
    """``(lat2d, lon2d)``, both of shape ``[101, 361]`` (``indexing='ij'``)."""
    lat = roi_lat_array()
    lon = roi_lon_array()
    return np.meshgrid(lat, lon, indexing="ij")


def roi_bounds() -> tuple[float, float, float, float]:
    """Cell-edge bounding box ``(west, south, east, north)`` in degrees.

    Centres plus half a cell in every direction, so the box covers the full
    footprint of the grid rather than just the outermost centres.
    """
    lat = roi_lat_array()
    lon = roi_lon_array()
    half = ROI_RES / 2.0
    return (
        float(lon[0] - half),
        float(lat[0] - half),
        float(lon[-1] + half),
        float(lat[-1] + half),
    )


def route_lat_array() -> np.ndarray:
    """Route-grid latitude centres, shape ``[185]`` (float64), -81.0 .. -25.8."""
    n_rows = ROUTE_SHAPE[0]
    expected = round((ROUTE_ROI_LAT_MAX - ROUTE_ROI_LAT_MIN) / ROUTE_RES)
    if expected != n_rows:
        raise ValueError(
            f"ROUTE_SHAPE is inconsistent with the route latitude bounds: "
            f"({ROUTE_ROI_LAT_MAX} - {ROUTE_ROI_LAT_MIN}) / {ROUTE_RES} = "
            f"{expected}, expected {n_rows}"
        )
    return ROUTE_ROI_LAT_MIN + np.arange(n_rows, dtype=np.float64) * ROUTE_RES


def route_lon_array() -> np.ndarray:
    """Route-grid longitude centres, shape ``[321]`` (float64), -11.0 .. 85.0."""
    n_cols = ROUTE_SHAPE[1]
    expected = round((ROUTE_ROI_LON_MAX - ROUTE_ROI_LON_MIN) / ROUTE_RES)
    if expected != n_cols:
        raise ValueError(
            f"ROUTE_SHAPE is inconsistent with the route longitude bounds: "
            f"({ROUTE_ROI_LON_MAX} - {ROUTE_ROI_LON_MIN}) / {ROUTE_RES} = "
            f"{expected}, expected {n_cols}"
        )
    return ROUTE_ROI_LON_MIN + np.arange(n_cols, dtype=np.float64) * ROUTE_RES


def route_lat_lon_meshgrid() -> tuple[np.ndarray, np.ndarray]:
    """``(lat2d, lon2d)``, both of shape ``[185, 321]`` (``indexing='ij'``)."""
    lat = route_lat_array()
    lon = route_lon_array()
    return np.meshgrid(lat, lon, indexing="ij")


def route_bounds() -> tuple[float, float, float, float]:
    """Route cell-edge bounding box ``(west, south, east, north)`` in degrees.

    Same construction as :func:`roi_bounds`: centres plus half a cell, so the
    box is the true footprint of the canvas rather than the outer centres.
    """
    lat = route_lat_array()
    lon = route_lon_array()
    half = ROUTE_RES / 2.0
    return (
        float(lon[0] - half),
        float(lat[0] - half),
        float(lon[-1] + half),
        float(lat[-1] + half),
    )


def assert_roi_array(array: np.ndarray, name: str = "field") -> np.ndarray:
    """Raise if ``array`` is not exactly ``[101, 361]` — never pad or crop."""
    if array.shape != ROI_SHAPE:
        raise ValueError(
            f"{name} has shape {array.shape}, expected the ROI shape {ROI_SHAPE}. "
            "Regrid the source before using it; AURORA never pads or crops a "
            "field to make it fit."
        )
    return array


def cell_index(lat: float, lon: float, shape: tuple[int, int] = ROI_SHAPE) -> tuple[int, int]:
    """Nearest ROI cell centre to a decimal-degree position, clamped in-grid.

    Positions outside the grid clamp to the edge rather than raising: a ship
    just west of the ROI is still a ship, and the answer it wants is "the
    nearest cell we know about".
    """
    rows, cols = shape
    row = int(round((lat - ROI_LAT_MIN) / ROI_RES))
    col = int(round((lon - ROI_LON_MIN) / ROI_RES))
    return int(np.clip(row, 0, rows - 1)), int(np.clip(col, 0, cols - 1))


def sample_field(
    array: np.ndarray, lat: float, lon: float, channel: int = 0
) -> float | None:
    """Value of ``array`` at ``(lat, lon)``, or ``None`` when it is unknown.

    ``None`` for a non-finite value as well as a wrong shape: NaN in a field
    means "no observation here", and reporting NaN as ``0.0`` would turn a
    data void into open water. ``channel`` selects the plane of a stacked
    field (``[C, 101, 361]``), so the channel choice stays visible at the
    call site instead of being buried in a default.
    """
    values = np.asarray(array)
    if values.ndim == 3:
        if values.shape[1:] != ROI_SHAPE or not 0 <= channel < values.shape[0]:
            return None
        values = values[channel]
    elif values.ndim != 2:
        return None
    if values.shape != ROI_SHAPE:
        return None
    row, col = cell_index(lat, lon)
    try:
        raw = float(values[row, col])
    except (IndexError, TypeError, ValueError):
        return None
    return raw if math.isfinite(raw) else None


# ---------------------------------------------------------------------------
# SIC grid -> route grid (the display canvas)
# ---------------------------------------------------------------------------
#: A route cell is inside the SIC region when its nearest SIC centre is at
#: most one SIC cell away. The two grids are both 0.25° but their centres are
#: offset by half a cell, so an inside cell sits 0.125° from its neighbour in
#: each axis (~0.177° diagonal) while the first outside cell sits 0.375°
#: away — 0.25° cleanly separates the two populations.
ROUTE_CELL_MATCH_RADIUS_DEG = 0.25


def place_sic_in_route_grid_nan(sic: np.ndarray) -> np.ndarray:
    """Place a ``[101, 361]`` SIC field on the ``[185, 321]`` route canvas.

    The two grids do not line up: the SIC grid is wider (361 cells vs 321),
    starts 15° further west, and its centres sit half a cell off the route
    grid's. There is no 1:1 index mapping to slice — each route cell is
    matched to its **nearest SIC cell centre** with a KD-tree, and a route
    cell whose nearest centre is further than
    :data:`ROUTE_CELL_MATCH_RADIUS_DEG` gets **NaN**, because that cell lies
    outside the SIC grid's footprint and AURORA never invents ice the
    product did not predict.

    NaN is what makes the canvas swap work: the renderer draws NaN fully
    transparent, so the ice fades into the ocean instead of ending on the
    rectangle a fill of ``0`` would draw (``0`` is the low end of the ramp,
    i.e. open water).
    """
    from scipy.spatial import cKDTree

    assert_roi_array(sic, "SIC")

    sic_lat2d, sic_lon2d = np.meshgrid(roi_lat_array(), roi_lon_array(), indexing="ij")
    route_lat2d, route_lon2d = np.meshgrid(route_lat_array(), route_lon_array(), indexing="ij")

    tree = cKDTree(np.column_stack([sic_lat2d.ravel(), sic_lon2d.ravel()]))

    # Missing data is NaN everywhere in AURORA; folding ±inf in here means the
    # renderer only ever has to understand one kind of "no value".
    values = np.where(np.isfinite(sic), sic, np.nan).astype(np.float32).ravel()

    dist, nearest = tree.query(
        np.column_stack([route_lat2d.ravel(), route_lon2d.ravel()]), k=1
    )

    canvas = values[nearest].reshape(ROUTE_SHAPE)
    canvas[dist.reshape(ROUTE_SHAPE) > ROUTE_CELL_MATCH_RADIUS_DEG] = np.nan
    return canvas


def place_sic_in_route_grid_zeroed(sic: np.ndarray) -> np.ndarray:
    """Same placement, but every no-data cell reads ``0.0``.

    The two fills answer two different questions:

    * **display (NaN)** — "is there an observation here?" An absent one must
      be transparent, not open water;
    * **route optimizer (0)** — "how much ice is this cell holding?" A cell
      outside the SIC product's coverage holds no scored ice, so the cost
      grid never inherits a NaN from a region the vessel cannot reach anyway.

    Never pass the zeroed variant to the renderer: ``0`` and "no data" have
    to stay distinguishable all the way to the PNG.
    """
    out = place_sic_in_route_grid_nan(sic)
    return np.where(np.isnan(out), 0.0, out).astype(np.float32)
