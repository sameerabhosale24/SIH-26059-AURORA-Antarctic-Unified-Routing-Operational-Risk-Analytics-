"""Weather and ocean current at the vessel's position.

AURORA stores gridded fields, not point observations, so "weather at the
ship" is a nearest-cell read of the newest stored ``weather`` and
``currents`` fields. The same function backs both the 5-minute relay push
and ``GET /api/weather/vessel``, so the two can never disagree.

Deliberate gaps, stated rather than filled:

* ``wave_height`` and ``wave_dir`` are always ``null``. The ERA5 store
  carries ``u10, v10, t2m`` and CMEMS carries ``uo, vo, thetao, so, zos`` —
  there is no wave source. Emitting a number here would be an invention, and
  the UI already renders an em dash.
* ``current_dir`` is the direction the water flows *toward* (the standard
  for currents); ``wind_dir`` is the direction the wind comes *from* (the
  standard for winds). Both are documented on the frontend type.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

import numpy as np

from app.config import get_settings
from app.services import field_storage, vessel_service
from app.utils.constants import ROI_SHAPE
from app.utils.grid import sample_field

logger = logging.getLogger("aurora.weather")

#: Channel indices in the stored stacks.
CH_U10, CH_V10, CH_T2M = 0, 1, 2
CH_UO, CH_VO = 0, 1
WEATHER_SHAPE = (3, *ROI_SHAPE)
CURRENTS_SHAPE = (5, *ROI_SHAPE)

#: Kelvin to Celsius.
_KELVIN_OFFSET = 273.15


def _deg2rad(value: float) -> float:
    return value * math.pi / 180.0


def wind_direction_from(u: float, v: float) -> float:
    """Direction the wind blows *from*, degrees true (meteorological)."""
    return (math.degrees(math.atan2(-u, -v)) + 360.0) % 360.0


def current_direction_to(u: float, v: float) -> float:
    """Direction the water flows *toward*, degrees true (oceanographic)."""
    return math.degrees(math.atan2(u, v)) % 360.0


def _latest(source: str, expected_shape: tuple[int, ...]):
    """Newest correctly-shaped field for ``source``, or ``(None, None)``.

    A file on the wrong grid is reported as absent rather than sampled: the
    channels would silently line up against the wrong rows, and a weather
    reading from the wrong cell is worse than no reading.
    """
    dates = field_storage.list_available_dates(source)
    if not dates:
        return None, None
    array = field_storage.read_field(source, dates[-1])
    if array is None:
        return None, None
    if np.asarray(array).shape != expected_shape:
        logger.warning(
            "%s/%s has shape %s, expected %s; not sampling it",
            source, dates[-1].isoformat(), np.asarray(array).shape, expected_shape,
        )
        return None, None
    return array, dates[-1]


def sample_at(lat: float, lon: float) -> dict | None:
    """Weather point at ``(lat, lon)``, or ``None when neither field exists.

    A missing currents field does not discard a perfectly good wind reading:
    the missing channels come back ``null`` and ``source`` says which field
    was used. Both missing is the only case that returns ``None``, because a
    payload with every measurement null carries no information at all.
    """
    weather, weather_date = _latest("weather", WEATHER_SHAPE)
    currents, currents_date = _latest("currents", CURRENTS_SHAPE)

    if weather is None and currents is None:
        return None

    wind_speed = wind_dir = air_temp = None
    if weather is not None:
        u = sample_field(weather, lat, lon, CH_U10)
        v = sample_field(weather, lat, lon, CH_V10)
        if u is not None and v is not None:
            wind_speed = round(math.hypot(u, v), 3)
            wind_dir = round(wind_direction_from(u, v), 1)
        temp_k = sample_field(weather, lat, lon, CH_T2M)
        if temp_k is not None:
            air_temp = round(temp_k - _KELVIN_OFFSET, 2)

    current_speed = current_dir = None
    if currents is not None:
        u = sample_field(currents, lat, lon, CH_UO)
        v = sample_field(currents, lat, lon, CH_VO)
        if u is not None and v is not None:
            current_speed = round(math.hypot(u, v), 4)
            current_dir = round(current_direction_to(u, v), 1)

    sources = [
        f"era5@{weather_date.isoformat()}" if weather_date else None,
        f"cmems@{currents_date.isoformat()}" if currents_date else None,
    ]

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lat": float(lat),
        "lon": float(lon),
        "wind_speed": wind_speed,
        "wind_dir": wind_dir,
        "wave_height": None,  # no wave source in AURORA
        "wave_dir": None,
        "current_speed": current_speed,
        "current_dir": current_dir,
        "air_temp": air_temp,
        "source": ", ".join(s for s in sources if s) or "unknown",
    }


def sample_at_vessel(vessel_id: int) -> dict | None:
    """Weather at the newest fix of *this* vessel, or ``None``.

    The id is required rather than defaulted. ``latest_state(None)`` means
    "no filter", which would answer with whichever ship reported last
    across every operator — a weather panel that silently moved to
    somebody else's position. An unknown vessel is a ``None``, never a
    substitute location.
    """
    state = vessel_service.latest_state(vessel_id)
    if state is None or state.lat is None or state.lon is None:
        return None
    return sample_at(float(state.lat), float(state.lon))


def publish_sample(payload: dict | None) -> bool:
    """Push one sample on ``weather.updated``; ``None`` is never published.

    "No data" must not overwrite the last real reading in the cache — a
    channel that connects afterwards should see the newest measurement that
    existed, not an empty frame that made the panel go blank.
    """
    if payload is None:
        return False
    from app.redis.pubsub import CHANNEL_WEATHER, publish_cached_sync

    return publish_cached_sync(CHANNEL_WEATHER, payload)


async def run_weather_poller() -> None:
    """Sample at the vessel every ``WEATHER_POLL_SECONDS`` until cancelled."""
    settings = get_settings()
    interval = max(int(settings.WEATHER_POLL_SECONDS), 30)
    logger.info("weather poller started (every %ss)", interval)

    while True:
        try:
            payload = await asyncio.to_thread(
                sample_at_vessel, get_settings().OWN_SHIP_VESSEL_ID
            )
            if payload is None:
                logger.debug("weather poller: no own-ship fix or no stored fields")
            else:
                await asyncio.to_thread(publish_sample, payload)
        except asyncio.CancelledError:
            logger.info("weather poller stopped")
            raise
        except Exception:  # noqa: BLE001 — a bad read must not stop the loop
            logger.exception("weather poller pass failed")
        await asyncio.sleep(interval)
