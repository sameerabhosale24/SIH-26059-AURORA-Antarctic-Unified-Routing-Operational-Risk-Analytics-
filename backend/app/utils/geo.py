"""Spherical helpers shared by routing, CPA and alarm evaluation.

One implementation of "how far apart are these two points" for the whole
backend. A half-percent error in a great-circle distance is invisible in a
log line and consequential in an ETA, so nothing here is hand-rolled a
second time.

Distances are nautical miles, bearings are degrees clockwise from true
north, and every coordinate is ``(lat, lon)`` in decimal degrees on WGS84.
"""

from __future__ import annotations

import numpy as np

#: IUGG mean Earth radius in nautical miles.
EARTH_RADIUS_NM = 3440.065
#: One nautical mile in metres.
NM_TO_M = 1852.0
#: One knot in metres per second.
KT_TO_MS = 0.514444
#: Metres per degree of latitude, for local flat approximations.
NM_PER_DEG_LAT = 60.0

_DEG2RAD = np.pi / 180.0


def haversine_nm(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in nautical miles.

    Scalars or broadcastable arrays; always returns an array so callers can
    rely on ``.min()`` without special-casing a scalar result.
    """
    phi1 = np.asarray(lat1, dtype=np.float64) * _DEG2RAD
    phi2 = np.asarray(lat2, dtype=np.float64) * _DEG2RAD
    dphi = (np.asarray(lat2, dtype=np.float64) - np.asarray(lat1, dtype=np.float64)) * _DEG2RAD
    dlam = (np.asarray(lon2, dtype=np.float64) - np.asarray(lon1, dtype=np.float64)) * _DEG2RAD

    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_NM * np.arcsin(np.sqrt(a))


def haversine_scalar_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """``haversine_nm`` reduced to a Python float, for the scalar call sites."""
    value = haversine_nm(lat1, lon1, lat2, lon2)
    return float(value) if np.ndim(value) == 0 else float(np.asarray(value).item())


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, 0-360 clockwise."""
    phi1 = lat1 * _DEG2RAD
    phi2 = lat2 * _DEG2RAD
    dlon = (lon2 - lon1) * _DEG2RAD
    y = np.sin(dlon) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlon)
    return float(np.degrees(np.arctan2(y, x)) % 360.0)


def destination_point(lat: float, lon: float, bearing: float, distance_nm: float) -> tuple[float, float]:
    """Point ``distance_nm`` away along ``bearing`` (the direct formula)."""
    delta = distance_nm / EARTH_RADIUS_NM
    theta = bearing * _DEG2RAD
    phi1 = lat * _DEG2RAD
    lambda1 = lon * _DEG2RAD

    phi2 = np.arcsin(np.sin(phi1) * np.cos(delta) + np.cos(phi1) * np.sin(delta) * np.cos(theta))
    lambda2 = lambda1 + np.arctan2(
        np.sin(theta) * np.sin(delta) * np.cos(phi1),
        np.cos(delta) - np.sin(phi1) * np.sin(phi2),
    )
    return float(np.degrees(phi2)), float((np.degrees(lambda2) + 540.0) % 360.0 - 180.0)


def local_en_offset_nm(lat_ref: float, lon_ref: float, lat, lon) -> tuple[np.ndarray, np.ndarray]:
    """East/north offsets from ``lat_ref, lon_ref`` in nautical miles.

    Flat-earth approximation. Valid to a fraction of a mile inside the
    <50 nm envelope CPA is defined over, and orders of magnitude cheaper
    than a great-circle solve per candidate target.
    """
    mean_lat = (np.asarray(lat, dtype=np.float64) + lat_ref) * 0.5
    east = (np.asarray(lon, dtype=np.float64) - lon_ref) * np.cos(mean_lat * _DEG2RAD) * NM_PER_DEG_LAT
    north = (np.asarray(lat, dtype=np.float64) - lat_ref) * NM_PER_DEG_LAT
    return east, north


def unit_vector_from_bearing(bearing_degrees) -> tuple[np.ndarray, np.ndarray]:
    """``(east, north)`` components of a bearing measured clockwise from north."""
    theta = np.asarray(bearing_degrees, dtype=np.float64) * _DEG2RAD
    return np.sin(theta), np.cos(theta)
