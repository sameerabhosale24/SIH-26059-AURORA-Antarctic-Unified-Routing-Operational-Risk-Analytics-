"""Static reference payloads: ROI, stations, ENC manifest.

These three are the only endpoints whose answer never depends on a sensor,
a fetch or a signed-in operator, which is exactly why the map needs them
before anything else has loaded: the canvas, the station pins and the chart
layer are all configured from here rather than from constants in the
frontend.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoiOut(BaseModel):
    """The region of interest in WGS84 degrees.

    Duplicated from :mod:`app.config` on purpose: the frontend must never
    hardcode the ROI, so this is the one place it is handed over.
    """

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float


class StationOut(BaseModel):
    """A named facility (research station, port or supply point)."""

    id: str
    name: str
    country: str = ""
    lat: float
    lon: float


class EncCellOut(BaseModel):
    """One S-57 cell the chart layer can ask for."""

    id: str
    name: str
    url: str
    bounds: list[float] = Field(default_factory=list)
    updated_at: str = ""


class EncManifestOut(BaseModel):
    """Every cell available to the client.

    An ENC-free deployment answers ``{"cells": [], "version": n}`` rather
    than an error, so the chart layer renders nothing instead of failing.
    """

    cells: list[EncCellOut] = Field(default_factory=list)
    version: int = 0
