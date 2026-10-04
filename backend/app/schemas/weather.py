"""A single weather / wave / current sample at a point.

Every measurement is nullable. ``source`` names the fields the sample was
actually taken from, so a half-populated point says which half is missing
instead of presenting itself as a complete reading.
"""

from __future__ import annotations

from pydantic import BaseModel


class WeatherPointOut(BaseModel):
    ts: str
    lat: float
    lon: float
    wind_speed: float | None = None
    #: Direction the wind is coming FROM, degrees true.
    wind_dir: float | None = None
    wave_height: float | None = None
    wave_dir: float | None = None
    current_speed: float | None = None
    #: Direction the water flows TOWARD, degrees true.
    current_dir: float | None = None
    air_temp: float | None = None
    source: str = ""
