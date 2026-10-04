"""Tracked icebergs and their probabilistic drift cones."""

from __future__ import annotations

from pydantic import BaseModel


class IcebergOut(BaseModel):
    """One iceberg, newest observation.

    ``drift_cone`` is a WGS84 GeoJSON Polygon or ``null`` when the backend
    has not computed one — an absent forecast is not an empty polygon,
    which would read as "the iceberg will not move".
    """

    id: str
    ts: str
    lat: float
    lon: float
    length_km: float | None = None
    drift_bearing: float | None = None
    drift_speed_kt: float | None = None
    source: str = ""
    drift_cone: dict | None = None
    drift_cone_probability: float | None = None
