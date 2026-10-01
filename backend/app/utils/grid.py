"""Coordinate arrays for the ROI grid.

Single source of truth: nothing in AURORA is allowed to hand-roll a latitude
or longitude vector, because a half-cell mistake here is invisible until the
forecast lands in the wrong place.
"""

from __future__ import annotations

import numpy as np

from app.utils.constants import (
    ROI_LAT_MAX,
    ROI_LAT_MIN,
    ROI_LON_MAX,
    ROI_LON_MIN,
    ROI_RES,
    ROI_SHAPE,
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


def assert_roi_array(array: np.ndarray, name: str = "field") -> np.ndarray:
    """Raise if ``array`` is not exactly ``[101, 361]`` — never pad or crop."""
    if array.shape != ROI_SHAPE:
        raise ValueError(
            f"{name} has shape {array.shape}, expected the ROI shape {ROI_SHAPE}. "
            "Regrid the source before using it; AURORA never pads or crops a "
            "field to make it fit."
        )
    return array
