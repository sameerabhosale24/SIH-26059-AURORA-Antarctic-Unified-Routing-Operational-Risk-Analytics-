"""Alarm persistence reads, acknowledgements and publication.

The engine decides *that* something is wrong; this module owns everything
about how it is stored, shaped and pushed. Splitting it out keeps the rule
definitions in :mod:`app.services.alarm_engine` free of serialisation, and
gives ``POST /api/alarms/{id}/ack`` the same write path as the engine so an
acknowledgement behaves identically however it arrives.

One rule governs the geometry: a location is reported when there is one and
``null`` when there is not. A data-quality alarm with a coordinate would
invite the operator to click on a map pin that means nothing.

Geometry is always read through the typed ``Alarm.geom`` column — never by
binding a ``WKBElement`` as a raw parameter, because that bypasses
GeoAlchemy2's bind processor and PostGIS rejects the value.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from app.models import Alarm
from app.services import version_service

logger = logging.getLogger("aurora.alarms")

#: Severity order used for the API listing, most urgent first.
SEVERITY_RANK = {"critical": 0, "warning": 1, "caution": 2}
DEFAULT_LIMIT = 200


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _payload(row, lat: float | None, lon: float | None) -> dict:
    return {
        "id": int(row.id),
        "ts": _iso(row.ts),
        "vessel_id": str(row.vessel_id) if row.vessel_id is not None else "",
        "severity": row.severity,
        "type": row.type,
        "message": row.message or "",
        "lat": lat,
        "lon": lon,
        "payload": dict(row.payload) if isinstance(row.payload, dict) else {},
        "acked_at": _iso(row.acked_at),
        "acked_by": row.acked_by,
    }


def _decode(lat, lon) -> tuple[float | None, float | None]:
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def serialize_alarm(row, *, session=None) -> dict:
    """One alarm in the frontend's ``Alarm`` shape.

    Pass ``session`` when the caller already holds one; otherwise a
    short-lived session is opened for the geometry lookup alone.
    """
    if row.geom is None:
        return _payload(row, None, None)

    owned = session is None
    session = session or version_service.open_session()
    try:
        lat, lon = session.execute(
            select(func.ST_Y(Alarm.geom), func.ST_X(Alarm.geom)).where(Alarm.id == row.id)
        ).first()
    except Exception:  # noqa: BLE001 — a bad geometry must not hide the alarm
        logger.exception("could not read alarm %s geometry", row.id)
        lat = lon = None
    finally:
        if owned:
            session.close()
    return _payload(row, *_decode(lat, lon))


def serialize_by_id(alarm_id: int) -> dict | None:
    with version_service.open_session() as session:
        row = session.get(Alarm, alarm_id)
        return serialize_alarm(row, session=session) if row is not None else None


def list_alarms(
    *,
    since: datetime | None = None,
    vessel_id: int | None = None,
    unacked_only: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Alarms newest first, filtered by caller-supplied criteria.

    Geometry comes back in the same query as the rows — one request for a
    page of alarms, not one per alarm.

    Scoping has two tiers and neither is optional. An explicit
    ``vessel_id`` selects that ship's alarms *plus* the data-quality
    alarms, which carry no vessel because they are about the data rather
    than about anyone's voyage. No ``vessel_id`` means the caller owns no
    ship, so only the global tier is returned — never "every alarm in the
    table".
    """
    limit = max(1, min(int(limit), 1000))
    with version_service.open_session() as session:
        statement = select(
            Alarm, func.ST_Y(Alarm.geom), func.ST_X(Alarm.geom)
        )
        if since is not None:
            statement = statement.where(Alarm.ts >= since)
        if vessel_id is not None:
            statement = statement.where(
                or_(
                    Alarm.vessel_id == int(vessel_id),
                    Alarm.vessel_id.is_(None),
                )
            )
        else:
            statement = statement.where(Alarm.vessel_id.is_(None))
        if unacked_only:
            statement = statement.where(Alarm.acked_at.is_(None))
        statement = statement.order_by(Alarm.ts.desc(), Alarm.id.desc()).limit(limit)
        rows = session.execute(statement).all()
        return [_payload(row[0], *_decode(row[1], row[2])) for row in rows]


def alarm_is_visible(alarm_id: int, vessel_id: int | None) -> bool:
    """Whether ``alarm_id`` may be read or acknowledged under this scope.

    A data-quality alarm belongs to nobody and is visible to everybody. An
    alarm attached to a ship is visible only to that ship's operator, and a
    caller with no vessels therefore sees neither it nor its id — an
    unknown id and somebody else's id answer identically, so the endpoint
    cannot be used to probe for them.
    """
    with version_service.open_session() as session:
        row = session.get(Alarm, alarm_id)
        if row is None:
            return False
        if row.vessel_id is None:
            return True
        return vessel_id is not None and int(row.vessel_id) == int(vessel_id)


def ack_alarm(alarm_id: int, acked_by: str | None) -> dict | None:
    """Acknowledge one alarm and return its new state.

    Re-acking an already-acknowledged alarm returns it unchanged rather than
    moving the timestamp: the record of *when* an operator first saw it is
    the more useful number, and a double-click must not rewrite history.
    """
    with version_service.open_session() as session:
        row = session.get(Alarm, alarm_id)
        if row is None:
            return None
        if row.acked_at is None:
            row.acked_at = datetime.now(timezone.utc)
            row.acked_by = (acked_by or "").strip() or None
            session.commit()
            logger.info("alarm %s acknowledged by %s", alarm_id, row.acked_by)
        payload = serialize_alarm(row, session=session)
    return payload


def publish_alarm(payload: dict) -> bool:
    """Push one alarm on ``alarm.created`` (a state change, not a delta)."""
    from app.redis.pubsub import CHANNEL_ALARM, publish_cached_sync

    return publish_cached_sync(CHANNEL_ALARM, payload)
