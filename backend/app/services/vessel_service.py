"""Own-ship telemetry: one read path, one serialiser, one publisher.

Both the relay that writes a fix and the endpoint that serves one go
through here, so ``GET /api/vessel/latest`` and ``WS /ws/vessel`` can never
disagree about the shape of the ship's state.

The serialised shape is the frontend's ``VesselState``: ``vessel_id`` as a
string (it is an id rendered in a URL, not a measurement), ``ts``/``lat``/
``lon`` always present, everything else ``null`` rather than zero. A
missing measurement is unknown; zero is a reading.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import VesselState
from app.services import version_service

logger = logging.getLogger("aurora.vessel")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_state(row: VesselState) -> dict:
    """The frontend's ``VesselState`` object from one ``vessel_state`` row."""
    return {
        "vessel_id": str(row.vessel_id) if row.vessel_id is not None else "0",
        "ts": _iso(row.ts),
        "lat": _float(row.lat),
        "lon": _float(row.lon),
        "sog": _float(row.sog),
        "cog": _float(row.cog),
        "heading": _float(row.heading),
        "rot": _float(row.rot),
        "draft": _float(row.draft),
        "ukc": _float(row.ukc),
        "fuel_remaining": _float(row.fuel_remaining),
        "engine_load": _float(row.engine_load),
        "wind_speed": _float(row.wind_speed),
        "wind_dir": _float(row.wind_dir),
        "source": row.source or "estimated",
    }


def latest_state(vessel_id: int | None = None) -> VesselState | None:
    """Newest telemetry row, or ``None`` when the feed has never reported."""
    with version_service.open_session() as session:
        statement = select(VesselState).order_by(VesselState.ts.desc()).limit(1)
        if vessel_id is not None:
            statement = statement.where(VesselState.vessel_id == int(vessel_id))
        return session.execute(statement).scalars().first()


def latest_payload(vessel_id: int | None = None) -> dict | None:
    row = latest_state(vessel_id)
    return serialize_state(row) if row is not None else None


def publish_state(row: VesselState) -> bool:
    """Cache and publish one fix on ``vessel.updated``."""
    from app.redis.pubsub import CHANNEL_VESSEL, publish_cached_sync

    return publish_cached_sync(CHANNEL_VESSEL, serialize_state(row))


def write_state(
    *,
    vessel_id: int | None,
    lat: float,
    lon: float,
    sog: float | None = None,
    cog: float | None = None,
    heading: float | None = None,
    rot: float | None = None,
    draft: float | None = None,
    ukc: float | None = None,
    fuel_remaining: float | None = None,
    engine_load: float | None = None,
    wind_speed: float | None = None,
    wind_dir: float | None = None,
    source: str = "gps",
    ts: datetime | None = None,
) -> VesselState | None:
    """Insert one telemetry row and publish it.

    Returns the stored row, or ``None`` when the insert failed. A relay must
    survive a transient write error: the next fix arrives in a second and
    carries the same information, while a crashed relay carries nothing.
    """
    from sqlalchemy import insert

    ts = ts or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    try:
        with version_service.open_session() as session:
            session.execute(insert(VesselState).values(
                ts=ts,
                vessel_id=int(vessel_id) if vessel_id is not None else None,
                lat=float(lat),
                lon=float(lon),
                sog=sog,
                cog=cog,
                heading=heading,
                rot=rot,
                draft=draft,
                ukc=ukc,
                fuel_remaining=fuel_remaining,
                engine_load=engine_load,
                wind_speed=wind_speed,
                wind_dir=wind_dir,
                source=source,
            ))
            session.commit()
            row = latest_state(vessel_id)
    except Exception:  # noqa: BLE001 — a write failure must not kill the relay
        logger.exception("could not persist a vessel_state row")
        return None

    if row is not None:
        publish_state(row)
    return row
