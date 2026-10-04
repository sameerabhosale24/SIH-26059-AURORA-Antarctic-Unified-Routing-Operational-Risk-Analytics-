"""Iceberg distance and drift-cone fields for the routing cost grid.

Two different questions, answered here once:

* "how far is the nearest iceberg from this cell" — a continuous falloff
  that steers a route around a field without forbidding it outright;
* "does the 48-hour p90 drift cone cover this cell" — a hard block, because
  a ship that is inside the cone when it arrives is inside a forecast it
  cannot act on.

Both read straight from the hypertable and the cone table. When there are
no observations the distance grid is ``+inf`` (harmless: the penalty is
already zero past 50 nm) and the cone mask is all ``False`` — an absent
source must never invent a hazard, and must never block a voyage either.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from app.services import version_service
from app.utils.constants import ROI_LAT_MIN, ROI_LON_MIN, ROI_RES, ROI_SHAPE
from app.utils.geo import haversine_nm

logger = logging.getLogger("aurora.icebergs")

#: Icebergs beyond this range contribute no penalty at all.
ICEBERG_INFLUENCE_NM = 50.0
#: The horizon a drift cone is treated as a hard block over.
DEFAULT_CONE_HORIZON_H = 48
#: The p90 contour — everything inside it is "likely enough to avoid".
DEFAULT_CONE_PROBABILITY = 0.9


@dataclass(frozen=True)
class Iceberg:
    iceberg_id: str
    lat: float
    lon: float
    length_km: float | None = None
    drift_bearing: float | None = None
    drift_speed_kt: float | None = None
    ts: datetime | None = None
    #: Catalogue that reported the sighting, or ``None`` when unlabelled.
    source: str | None = None


def iso_ts(value: datetime | None) -> str:
    """ISO 8601, or ``""`` for a corrupt row with no timestamp.

    ``iceberg_position.ts`` is part of the primary key, so a sighting
    without one cannot be written; the empty string exists only so a
    damaged row degrades to "unstamped" instead of to a 500.
    """
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def latest_positions(session=None) -> list[Iceberg]:
    """The newest observation for every iceberg, oldest-free and de-duplicated.

    ``DISTINCT ON (iceberg_id) ORDER BY iceberg_id, ts DESC`` — one row per
    iceberg, which is all a proximity field needs. A tracking history would
    double the cost of the distance grid without changing the answer.
    """
    from sqlalchemy import text

    owned = session is None
    session = session or version_service.open_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (iceberg_id)
                       iceberg_id, ts, ST_Y(geom::geometry) AS lat,
                       ST_X(geom::geometry) AS lon,
                       length_km, drift_bearing, drift_speed_kt, source
                FROM iceberg_position
                WHERE geom IS NOT NULL
                ORDER BY iceberg_id, ts DESC
                """
            )
        ).mappings().all()
        return [
            Iceberg(
                iceberg_id=str(row["iceberg_id"]),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                length_km=row["length_km"],
                drift_bearing=row["drift_bearing"],
                drift_speed_kt=row["drift_speed_kt"],
                ts=row["ts"],
                source=row["source"],
            )
            for row in rows
        ]
    except Exception:  # noqa: BLE001 — an empty table is the normal case
        logger.exception("could not read iceberg positions")
        return []
    finally:
        if owned:
            session.close()


def latest_cones(session=None) -> dict[str, tuple[dict | None, float | None]]:
    """Newest drift cone per iceberg: ``(GeoJSON polygon, probability)``.

    One entry per iceberg so the console can attach a cone to the sighting
    it belongs to. A cone with no readable geometry maps to ``None`` rather
    than to an empty polygon — an empty polygon would draw as "this iceberg
    is not going to move", which is the opposite of "no forecast".
    """
    import json as _json

    from sqlalchemy import text

    owned = session is None
    session = session or version_service.open_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (iceberg_id)
                       iceberg_id, probability,
                       ST_AsGeoJSON(geom::geometry) AS geojson
                FROM iceberg_drift_cone
                WHERE geom IS NOT NULL AND iceberg_id IS NOT NULL
                ORDER BY iceberg_id, run_ts DESC NULLS LAST, id DESC
                """
            )
        ).mappings().all()
    except Exception:  # noqa: BLE001 — an empty cone table is the normal case
        logger.exception("could not read iceberg drift cones")
        return {}
    finally:
        if owned:
            session.close()

    cones: dict[str, tuple[dict | None, float | None]] = {}
    for row in rows:
        geometry = None
        try:
            parsed = _json.loads(row["geojson"]) if row["geojson"] else None
            if isinstance(parsed, dict) and parsed.get("type"):
                geometry = parsed
        except (TypeError, ValueError):
            logger.warning("drift cone for %s is not valid GeoJSON; omitting", row["iceberg_id"])
        probability = row["probability"]
        cones[str(row["iceberg_id"])] = (
            geometry,
            float(probability) if probability is not None else None,
        )
    return cones


def distance_grid(icebergs: list[Iceberg], shape: tuple[int, int] = ROI_SHAPE) -> np.ndarray:
    """Nearest-iceberg range per cell, in nautical miles.

    ``+inf`` where no iceberg is within reach of the projection, which keeps
    ``iceberg_penalty`` at exactly zero rather than at "some large number".
    """
    rows, cols = shape
    if not icebergs:
        return np.full(shape, np.inf, dtype=np.float32)

    lat = ROI_LAT_MIN + np.arange(rows, dtype=np.float64) * ROI_RES
    lon = ROI_LON_MIN + np.arange(cols, dtype=np.float64) * ROI_RES
    lon2d, lat2d = np.meshgrid(lon, lat)

    nearest = np.full(shape, np.inf, dtype=np.float64)
    for berg in icebergs:
        if not np.isfinite(berg.lat) or not np.isfinite(berg.lon):
            continue
        nearest = np.minimum(nearest, haversine_nm(berg.lat, berg.lon, lat2d, lon2d))
    return nearest.astype(np.float32)


def drift_cone_mask(
    horizon_h: int = DEFAULT_CONE_HORIZON_H,
    probability: float = DEFAULT_CONE_PROBABILITY,
    shape: tuple[int, int] = ROI_SHAPE,
    session=None,
) -> np.ndarray:
    """Cells covered by a qualifying drift cone.

    Everything at or below ``horizon_h`` hours and at or above
    ``probability`` is unioned; a cell inside any of them is ``True``.

    Rasterisation is point-in-polygon over the cell centres with
    ``shapely.contains_xy``, which is vectorised in C. A cell on a polygon
    edge counts as covered — the conservative reading for a hazard.
    """
    rows, cols = shape
    empty = np.zeros(shape, dtype=bool)

    from sqlalchemy import text

    owned = session is None
    session = session or version_service.open_session()
    try:
        polygons = session.execute(
            text(
                """
                SELECT ST_AsGeoJSON(geom::geometry) AS geojson
                FROM iceberg_drift_cone
                WHERE geom IS NOT NULL
                  AND horizon_h IS NOT NULL AND horizon_h <= :horizon
                  AND probability IS NOT NULL AND probability >= :prob
                """
            ),
            {"horizon": int(horizon_h), "prob": float(probability)},
        ).scalars().all()
    except Exception:  # noqa: BLE001 — an empty cone table is normal
        logger.exception("could not read iceberg drift cones")
        return empty
    finally:
        if owned:
            session.close()

    if not polygons:
        return empty

    try:
        from shapely import contains_xy
        from shapely.geometry import shape as shapely_shape
    except Exception:  # noqa: BLE001 — shapely is a hard requirement in practice
        logger.exception("shapely unavailable; drift cones cannot be applied")
        return empty

    lat = ROI_LAT_MIN + np.arange(rows, dtype=np.float64) * ROI_RES
    lon = ROI_LON_MIN + np.arange(cols, dtype=np.float64) * ROI_RES
    lon2d, lat2d = np.meshgrid(lon, lat)
    flat_lon = lon2d.ravel()
    flat_lat = lat2d.ravel()

    covered = np.zeros(flat_lon.size, dtype=bool)
    for raw in polygons:
        try:
            geometry = shapely_shape(json.loads(raw))
        except Exception:  # noqa: BLE001 — one bad row must not hide the rest
            logger.warning("skipping an unreadable drift cone")
            continue
        if geometry.is_empty:
            continue
        covered |= contains_xy(geometry, flat_lon, flat_lat)

    mask = covered.reshape(shape)
    logger.info(
        "drift cone mask: %d/%d cells blocked (horizon<=%dh, p>=%.2f)",
        int(mask.sum()), mask.size, horizon_h, probability,
    )
    return mask


def version_key() -> int:
    """The ``data_version`` number for icebergs, for route provenance."""
    row = version_service.get("icebergs")
    return int(row.version) if row is not None else 0


def observations_age_hours(now: datetime | None = None) -> float | None:
    """Hours since the newest iceberg observation, or ``None`` if unknown.

    Used by the alarm layer's staleness rule; never invents an age when the
    table is empty.
    """
    from sqlalchemy import text

    now = now or datetime.now(timezone.utc)
    with version_service.open_session() as session:
        row = session.execute(
            text("SELECT max(ts) AS newest FROM iceberg_position")
        ).first()
    newest = row[0] if row else None
    if newest is None:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return (now - newest).total_seconds() / 3600.0
