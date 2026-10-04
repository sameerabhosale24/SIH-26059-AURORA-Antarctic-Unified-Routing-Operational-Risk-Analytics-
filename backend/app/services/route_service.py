"""Read and publish stored route runs.

The optimizer writes rows; this module turns them back into the payload the
frontend's ``RouteRun`` type describes — run, routes, geometry, waypoints —
and is the single publisher for the ``route.updated`` channel. Keeping the
serializer in one place is what stops the REST answer and the WebSocket push
from drifting apart: they are the same function called twice.

Every read goes through the synchronous session in :mod:`app.services.
version_service`. FastAPI callers wrap the whole thing in
``asyncio.to_thread``; scheduler threads call it directly. One engine, one
serialization path, no event-loop juggling.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.models import RouteRun
from app.services import version_service

logger = logging.getLogger("aurora.routes")

#: How many routes per run the API will serialise. A run that produced more
#: than this is a bug upstream, but a bad number must not stall the API.
MAX_ROUTES_PER_RUN = 32


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _float(value) -> float | None:
    """A number or ``None`` — never a fabricated ``0.0`` for missing data."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _geometry(raw) -> dict | None:
    if not raw:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("route geometry is not valid GeoJSON; emitting null")
        return None
    return parsed if isinstance(parsed, dict) else None


def _run_ids(session, *, vessel_id: int | None, limit: int) -> list[int]:
    clauses = ""
    params: dict = {"limit": int(limit)}
    if vessel_id is not None:
        clauses = "WHERE vessel_id = :vessel_id"
        params["vessel_id"] = int(vessel_id)
    rows = session.execute(
        text(
            f"SELECT id FROM route_run {clauses} ORDER BY run_ts DESC, id DESC "
            "LIMIT :limit"
        ),
        params,
    ).scalars().all()
    return [int(row) for row in rows]


def _load_routes(session, run_id: int) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT id, route_run_id, label, distance_nm, eta, fuel_estimate_t,
                   risk_score, is_recommended,
                   ST_AsGeoJSON(geom::geometry) AS geojson
            FROM route
            WHERE route_run_id = :run_id
            ORDER BY is_recommended DESC NULLS LAST, id
            LIMIT :limit
            """
        ),
        {"run_id": int(run_id), "limit": MAX_ROUTES_PER_RUN},
    ).mappings().all()

    if not rows:
        return []

    route_ids = [int(row["id"]) for row in rows]
    waypoint_rows = session.execute(
        text(
            """
            SELECT id, route_id, seq, name, eta,
                   ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon
            FROM waypoint
            WHERE route_id = ANY(:ids)
            ORDER BY route_id, seq
            """
        ),
        {"ids": route_ids},
    ).mappings().all()

    waypoints: dict[int, list[dict]] = {}
    for row in waypoint_rows:
        waypoints.setdefault(int(row["route_id"]), []).append({
            "id": int(row["id"]),
            "seq": int(row["seq"]) if row["seq"] is not None else 0,
            "lat": _float(row["lat"]),
            "lon": _float(row["lon"]),
            "name": row["name"],
            "eta": _iso(row["eta"]),
        })

    return [
        {
            "id": int(row["id"]),
            "route_run_id": int(row["route_run_id"]) if row["route_run_id"] is not None else int(run_id),
            "label": row["label"] or "route",
            "geometry": _geometry(row["geojson"]),
            "distance_nm": _float(row["distance_nm"]),
            "eta": _iso(row["eta"]),
            "fuel_estimate_t": _float(row["fuel_estimate_t"]),
            "risk_score": _float(row["risk_score"]),
            "is_recommended": bool(row["is_recommended"]),
            "waypoints": waypoints.get(int(row["id"]), []),
        }
        for row in rows
    ]


def load_run(run_id: int, session=None) -> dict | None:
    """One run with its routes, or ``None`` when the id does not exist."""
    owned = session is None
    session = session or version_service.open_session()
    try:
        run = session.get(RouteRun, run_id)
        if run is None:
            return None
        return serialize_run(run, _load_routes(session, run.id))
    finally:
        if owned:
            session.close()


def serialize_run(run: RouteRun, routes: list[dict]) -> dict:
    """The frontend's ``RouteRun`` shape, from an ORM row plus its routes."""
    return {
        "id": int(run.id) if run.id is not None else 0,
        "vessel_id": str(run.vessel_id) if run.vessel_id is not None else "0",
        "run_ts": _iso(run.run_ts),
        "input_version": dict(run.input_version or {}),
        "status": run.status,
        "notes": run.notes,
        "routes": routes,
    }


def latest_run(vessel_id: int | None = None) -> dict | None:
    """Newest run (optionally for one vessel), fully serialised."""
    with version_service.open_session() as session:
        ids = _run_ids(session, vessel_id=vessel_id, limit=1)
        if not ids:
            return None
        return load_run(ids[0], session=session)


def run_history(limit: int = 10, vessel_id: int | None = None) -> list[dict]:
    """Newest-first runs, each with its routes."""
    limit = max(1, min(int(limit), 100))
    with version_service.open_session() as session:
        runs = []
        for run_id in _run_ids(session, vessel_id=vessel_id, limit=limit):
            run = session.get(RouteRun, run_id)
            if run is None:
                continue
            runs.append(serialize_run(run, _load_routes(session, run_id)))
        return runs


def recommended_coordinates(vessel_id: int | None = None) -> list[tuple[float, float]] | None:
    """Vertices ``(lat, lon)`` of the newest recommended route, or ``None``.

    ``None`` means "no planned route to be off course from", which is a
    missing input for the off-course rule, not a pass.
    """
    with version_service.open_session() as session:
        row = session.execute(
            text(
                """
                SELECT ST_AsGeoJSON(r.geom::geometry) AS geojson
                FROM route r
                JOIN route_run rr ON rr.id = r.route_run_id
                WHERE r.is_recommended IS TRUE AND r.geom IS NOT NULL
                  AND (:vessel_id IS NULL OR rr.vessel_id = :vessel_id)
                ORDER BY rr.run_ts DESC, r.id
                LIMIT 1
                """
            ),
            {"vessel_id": int(vessel_id) if vessel_id is not None else None},
        ).first()
    if not row or not row[0]:
        return None
    geometry = _geometry(row[0])
    if not geometry or geometry.get("type") != "LineString":
        return None
    points: list[tuple[float, float]] = []
    for pair in geometry.get("coordinates") or []:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            try:
                points.append((float(pair[1]), float(pair[0])))
            except (TypeError, ValueError):
                continue
    return points or None


def run_vessel_id(run_id: int) -> int | None:
    """The vessel a run belongs to, or ``None`` when the run does not exist.

    Ownership has to be answered before any run is read or written: the id
    comes from the request body, so an operator could otherwise accept a
    route into somebody else's voyage.
    """
    with version_service.open_session() as session:
        run = session.get(RouteRun, run_id)
        if run is None:
            return None
        return int(run.vessel_id) if run.vessel_id is not None else None


def accept_route(
    route_run_id: int, route_id: int, accepted_by: str | None = None
) -> dict | None:
    """Make ``route_id`` the recommended route of its run.

    The run's other routes are cleared, so "recommended" always means exactly
    one. Returns the updated run, or ``None`` when either id is unknown — a
    caller must not be able to accept a route into a run that does not
    exist.

    ``accepted_by`` is recorded on the run's ``notes``. There is no
    acknowledgement column on ``route_run`` and adding one would be a
    migration for a single string, while ``notes`` is already free-form
    provenance that the console does not render.
    """
    stamp = datetime.now(timezone.utc).isoformat()
    note = f"accepted_by={(accepted_by or '').strip() or 'unknown'} @ {stamp}"

    with version_service.open_session() as session:
        run = session.get(RouteRun, route_run_id)
        if run is None:
            return None
        owned = session.execute(
            text("SELECT id FROM route WHERE id = :route_id AND route_run_id = :run_id"),
            {"route_id": int(route_id), "run_id": int(route_run_id)},
        ).scalars().first()
        if owned is None:
            return None
        session.execute(
            text("UPDATE route SET is_recommended = (id = :route_id) WHERE route_run_id = :run_id"),
            {"route_id": int(route_id), "run_id": int(route_run_id)},
        )
        session.execute(
            text("UPDATE route_run SET notes = :notes WHERE id = :run_id"),
            {
                "run_id": int(route_run_id),
                "notes": f"{run.notes}\n{note}" if run.notes else note,
            },
        )
        session.commit()
        logger.info("route %s accepted for run %s by %s", route_id, route_run_id, accepted_by)
        return load_run(route_run_id, session=session)


def publish_run(run_id: int) -> bool:
    """Push the full run for ``run_id`` on ``route.updated``.

    The payload is read back from the database rather than assembled from
    in-memory state: what the operator sees over the socket must be the
    bytes the API would return, or the two answers disagree the moment a
    write fails halfway.
    """
    from app.redis.pubsub import CHANNEL_ROUTE, publish_cached_sync

    payload = load_run(run_id)
    if payload is None:
        logger.warning("route run %s vanished before it could be published", run_id)
        return False
    return publish_cached_sync(CHANNEL_ROUTE, payload)
