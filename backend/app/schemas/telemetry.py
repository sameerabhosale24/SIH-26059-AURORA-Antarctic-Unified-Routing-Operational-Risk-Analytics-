"""SIC frame manifest and the telemetry endpoints.

Split into one module because the two families share a rule rather than a
table: every field that may be unknown is ``None`` in these models and
``null`` in the payload, and the console renders an em dash. A zero in a
speed or a clearance is a measurement, so it is never substituted for a
missing one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SicFrameMeta(BaseModel):
    """One rendered PNG, addressed by issue date and horizon.

    ``frame_extent`` is already in LCC metres and is handed to OpenLayers
    verbatim — the frontend does not recompute a raster's footprint.
    """

    date: str
    horizon: int
    version: int
    frame_url: str
    frame_extent: list[float]
    interval_url: str | None = None


class SicFramesResponse(BaseModel):
    """``GET /api/sic/frames`` — newest issue first, one entry per horizon."""

    version: int = 0
    frames: list[SicFrameMeta] = Field(default_factory=list)


class VesselStateOut(BaseModel):
    """Own-ship snapshot.

    ``vessel_id`` is a string because it is an id rendered into a URL, not a
    measurement. ``ts``/``lat``/``lon`` are the payload and are always
    present; everything else may be ``null``.
    """

    vessel_id: str
    ts: str | None = None
    lat: float | None = None
    lon: float | None = None
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    rot: float | None = None
    draft: float | None = None
    ukc: float | None = None
    fuel_remaining: float | None = None
    engine_load: float | None = None
    wind_speed: float | None = None
    wind_dir: float | None = None
    source: str = "estimated"


class AisTargetOut(BaseModel):
    """One AIS contact, with backend-computed CPA/TCPA and risk band.

    The frontend is explicitly not allowed to recompute these, so the same
    numbers appear here, in the WebSocket frame and in the collision alarm.
    """

    mmsi: int
    name: str | None = None
    ship_type: str | None = None
    lat: float
    lon: float
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    destination: str | None = None
    ts: str | None = None
    cpa_nm: float | None = None
    tcpa_min: float | None = None
    risk: str | None = None
