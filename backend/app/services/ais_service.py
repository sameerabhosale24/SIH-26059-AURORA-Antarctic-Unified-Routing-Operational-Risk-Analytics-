"""AIS targets: reading, CPA enrichment and publication.

One function produces the ``AisTarget`` list for every consumer — the relay
that pushes it, ``GET /api/ais/latest`` and the collision rule. CPA is
computed backend-side exactly once per read; the frontend is explicitly not
allowed to recompute it, so two implementations would be two answers.

Rows older than ``AIS_FRESHNESS_MINUTES`` are history, not traffic: they
stay in the hypertable for the track view but never enter CPA, because a
ten-minute-old position for a ship doing twenty knots is a five-mile error
hiding behind a confident number.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.config import get_settings
from app.models import AisTrack
from app.services import cpa_engine, version_service, vessel_service

logger = logging.getLogger("aurora.ais")

#: AIS messages the endpoint will return in one snapshot.
MAX_TARGETS = 500


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


def _finite(value) -> float | None:
    import math

    parsed = _float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return parsed


def risk_band(cpa_nm: float | None, threshold_nm: float) -> str | None:
    """``none``/``low``/``medium``/``high``, or ``None`` when uncomputable.

    Bands are multiples of the operator's own CPA threshold rather than
    hard-coded distances, so tightening ``ALARM_CPA_NM`` tightens the
    colouring with it instead of leaving the two out of step.
    """
    if cpa_nm is None:
        return None
    if cpa_nm <= threshold_nm:
        return "high"
    if cpa_nm <= 2.0 * threshold_nm:
        return "medium"
    if cpa_nm <= 4.0 * threshold_nm:
        return "low"
    return "none"


#: Columns every consumer of an AIS row needs.
_ROW_FIELDS = (
    "ts", "mmsi", "lat", "lon", "sog", "cog", "heading",
    "name", "ship_type", "destination",
)


def _as_dict(row) -> dict:
    """Normalise a result row — SQLAlchemy ``Row``, ``RowMapping`` or an ORM
    object — into a plain dict of the fields this module reads.

    ``text()`` results and ORM instances expose columns differently, and a
    target list is built from both (the relay writes ORM rows, the API reads
    raw SQL). One accessor here means one place to add a column later.
    """
    if isinstance(row, dict):
        return row
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return {key: mapping.get(key) for key in _ROW_FIELDS if key in mapping}
    return {key: getattr(row, key, None) for key in _ROW_FIELDS}


def serialize_target(
    row,
    *,
    own_lat: float | None,
    own_lon: float | None,
    own_sog: float | None,
    own_cog: float | None,
) -> dict | None:
    """One ``AisTarget``, or ``None`` when the row has no usable position."""
    data = _as_dict(row)
    lat = _finite(data.get("lat"))
    lon = _finite(data.get("lon"))
    if lat is None or lon is None or data.get("mmsi") is None:
        return None

    sog = _float(data.get("sog"))
    cog = _float(data.get("cog"))

    cpa_nm: float | None = None
    tcpa_min: float | None = None
    if own_lat is not None and own_lon is not None:
        cpa_nm, tcpa_h = cpa_engine.cpa_tcpa(
            own_lat,
            own_lon,
            _finite(own_sog) if own_sog is not None else 0.0,
            _finite(own_cog) if own_cog is not None else 0.0,
            lat,
            lon,
            sog if sog is not None else 0.0,
            cog if cog is not None else 0.0,
        )
        if cpa_nm == float("inf"):
            cpa_nm = None
            tcpa_min = None
        else:
            tcpa_min = round(float(tcpa_h) * 60.0, 1)

    return {
        "mmsi": int(data["mmsi"]),
        "name": data.get("name"),
        "ship_type": data.get("ship_type"),
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "heading": _float(data.get("heading")),
        "destination": data.get("destination"),
        "ts": _iso(data.get("ts")),
        "cpa_nm": None if cpa_nm is None else round(float(cpa_nm), 3),
        "tcpa_min": tcpa_min,
        "risk": risk_band(cpa_nm, get_settings().ALARM_CPA_NM),
    }


def recent_targets(limit: int = MAX_TARGETS, minutes: int | None = None) -> list:
    """Newest row per MMSI inside the freshness window.

    ``DISTINCT ON (mmsi)`` rather than an application-side group-by: the
    hypertable already has ``ts`` in its index, so the database answers this
    in one pass and the relay does not have to hold a day of sightings.
    """
    settings = get_settings()
    minutes = settings.AIS_FRESHNESS_MINUTES if minutes is None else int(minutes)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with version_service.open_session() as session:
        return list(session.execute(
            text(
                """
                SELECT DISTINCT ON (mmsi)
                       ts, mmsi, lat, lon, sog, cog, heading, name, ship_type, destination
                FROM ais_track
                WHERE ts >= :cutoff
                ORDER BY mmsi, ts DESC
                LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "limit": int(limit)},
        ).all())


def build_targets(rows, own=None) -> list[dict]:
    """Enrich raw rows into the frontend's ``AisTarget`` list."""
    if own is None:
        own = vessel_service.latest_state()
    own_lat = _finite(own.lat) if own is not None else None
    own_lon = _finite(own.lon) if own is not None else None
    own_sog = _finite(own.sog) if own is not None else None
    own_cog = _finite(own.cog) if own is not None else None

    targets: list[dict] = []
    for row in rows:
        target = serialize_target(
            row, own_lat=own_lat, own_lon=own_lon, own_sog=own_sog, own_cog=own_cog
        )
        if target is not None:
            targets.append(target)
    return targets


def latest_targets(limit: int = MAX_TARGETS) -> list[dict]:
    """Current live target list: recent sightings, CPA-enriched."""
    return build_targets(recent_targets(limit=limit))


def publish_targets() -> bool:
    """Push the whole list on ``ais.updated`` (one frame replaces the last)."""
    from app.redis.pubsub import CHANNEL_AIS, publish_cached_sync

    return publish_cached_sync(CHANNEL_AIS, {"targets": latest_targets()})


def write_target(
    *,
    mmsi: int,
    lat: float | None,
    lon: float | None,
    sog: float | None = None,
    cog: float | None = None,
    heading: float | None = None,
    name: str | None = None,
    ship_type: str | None = None,
    destination: str | None = None,
    ts: datetime | None = None,
) -> bool:
    """Persist one AIS report. Returns False when the write failed.

    A duplicate ``(ts, mmsi)`` is a re-broadcast of the same report and is
    dropped rather than raising: AIS repeats itself by design.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    ts = ts or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    try:
        with version_service.open_session() as session:
            session.execute(
                pg_insert(AisTrack)
                .values(
                    ts=ts,
                    mmsi=int(mmsi),
                    lat=lat,
                    lon=lon,
                    sog=sog,
                    cog=cog,
                    heading=heading,
                    name=name,
                    ship_type=ship_type,
                    destination=destination,
                )
                .on_conflict_do_nothing(index_elements=["ts", "mmsi"])
            )
            session.commit()
        return True
    except Exception:  # noqa: BLE001 — one bad row must not kill the socket
        logger.exception("could not persist an AIS report for mmsi %s", mmsi)
        return False
