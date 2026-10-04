"""Operational alarm rules — seven of them, over six alarm types.

Every rule follows the same contract:

* **No data, no alarm.** A missing bathymetry file, an empty iceberg table,
  a vessel blueprint without a draft — each rule skips rather than assuming
  the safe answer. A rule that cannot be evaluated is not a passing rule.
* **Deduplicated against what is already active.** An unacknowledged alarm
  of the same key suppresses a repeat, and so does one acknowledged within
  ``ALARM_REARM_HOURS``: acknowledging a persistent condition must not
  re-arm it on the very next pass, or the operator's acknowledgement means
  nothing.
* **One type can carry two rules.** ``ice`` covers both concentration and
  hull thickness, which are different problems with different severities, so
  the dedup key for that type includes the rule name. For the other five
  types the key is the type itself.

Nothing here computes a value the system does not hold. Where a measurement
is absent the rule says so by staying silent, which is why a fresh
deployment with no credentials raises no alarms at all.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select, text

from app.config import get_settings
from app.models import Vessel, VesselState
from app.services import (
    alarm_service,
    ais_service,
    field_storage,
    iceberg_proximity,
    route_service,
    version_service,
    vessel_service,
)
from app.utils.geo import haversine_scalar_nm, local_en_offset_nm
from app.utils.grid import sample_field

logger = logging.getLogger("aurora.alarm.engine")

#: Sources whose age is judged against ``ALARM_STALENESS_HOURS``. ``thickness``
#: is deliberately absent — CS2SMOS is ingested weekly by design, so a 36-hour
#: threshold would alarm every single week between runs. ``bathymetry`` and
#: ``enc`` are static products with no ingest cadence at all.
STALENESS_KEYS = ("sic", "currents", "weather", "icebergs")

#: How recent own-ship telemetry must be before any position rule runs. An
#: hour-old fix is a position; a day-old one is a guess.
OWN_SHIP_MAX_AGE_H = 24.0


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass
class Fields:
    """Field inputs, loaded once per pass and shared by every rule."""

    sic: np.ndarray | None = None
    sic_label: str | None = None
    thickness: np.ndarray | None = None
    bathy: np.ndarray | None = None
    icebergs: list = field(default_factory=list)


@dataclass
class Context:
    """Everything one pass needs about one vessel."""

    vessel_id: int
    now: datetime
    vessel: Vessel | None = None
    state: VesselState | None = None
    fields: Fields = field(default_factory=Fields)
    route_coords: list[tuple[float, float]] | None = None
    ais_targets: list[dict] = field(default_factory=list)
    @property
    def lat(self) -> float | None:
        if self.state is None or self.state.lat is None:
            return None
        value = float(self.state.lat)
        return value if math.isfinite(value) else None

    @property
    def lon(self) -> float | None:
        if self.state is None or self.state.lon is None:
            return None
        value = float(self.state.lon)
        return value if math.isfinite(value) else None

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None


def _newest_field(source: str) -> np.ndarray | None:
    dates = field_storage.list_available_dates(source)
    if not dates:
        return None
    array = field_storage.read_field(source, dates[-1])
    if array is None:
        return None
    values = np.asarray(array, dtype=np.float32)
    return values if values.shape == (101, 361) else None


def _newest_sic(now: datetime) -> tuple[np.ndarray | None, str | None]:
    """Observed SIC when one exists, otherwise the stored forecast.

    The observation is preferred because it is what actually happened. The
    forecast is the honest fallback when the observation store is empty —
    a modelled field, labelled as such in ``sic_label`` rather than passed
    off as a measurement.
    """
    observations = field_storage.list_available_dates("sic")
    today = now.date()
    usable = [day for day in observations if day <= today]
    if usable:
        array = field_storage.read_field("sic", usable[-1])
        if array is not None:
            values = np.asarray(array, dtype=np.float32)
            if values.shape == (101, 361):
                return values, f"observation {usable[-1].isoformat()}"

    from app.services.route_optimizer import load_sic_forecast

    forecast, day = load_sic_forecast(today)
    if forecast is None:
        return None, None
    return forecast, f"forecast {day.isoformat()}" if day else "forecast"


def _bathymetry() -> np.ndarray | None:
    path = field_storage.bathymetry_path()
    if not path.exists():
        return None
    try:
        values = np.asarray(np.load(path), dtype=np.float32)
    except Exception:  # noqa: BLE001 — an unreadable field is a missing one
        logger.warning("bathymetry file could not be read", exc_info=True)
        return None
    return values if values.shape == (101, 361) else None


def load_fields(now: datetime | None = None) -> Fields:
    """Read every field the rules sample from. Missing files stay ``None``."""
    sic, sic_label = _newest_sic(now or datetime.now(timezone.utc))
    return Fields(
        sic=sic,
        sic_label=sic_label,
        thickness=_newest_field("ice_thickness"),
        bathy=_bathymetry(),
        icebergs=iceberg_proximity.latest_positions(),
    )


def _load_vessel(vessel_id: int) -> Vessel | None:
    with version_service.open_session() as session:
        return session.get(Vessel, vessel_id)


def load_context(vessel_id: int, now: datetime, fields: Fields | None = None) -> Context:
    """Assemble one vessel's context; a missing vessel or fix is not fatal."""
    return Context(
        vessel_id=vessel_id,
        now=now,
        vessel=_load_vessel(vessel_id),
        state=vessel_service.latest_state(vessel_id),
        fields=fields if fields is not None else load_fields(now),
        route_coords=route_service.recommended_coordinates(vessel_id),
        # The same enriched list GET /api/ais/latest serves, so the alarm the
        # operator is warned about is computed from exactly the CPA the AIS
        # panel is already showing them.
        ais_targets=ais_service.latest_targets(limit=200),
    )


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    severity: str
    type: str
    rule: str
    message: str
    payload: dict
    lat: float | None = None
    lon: float | None = None
    vessel_id: int | None = None


# ---------------------------------------------------------------------------
# Geometry helper
# ---------------------------------------------------------------------------
def cross_track_nm(lat: float, lon: float, coords: list[tuple[float, float]]) -> float:
    """Shortest distance from a point to a polyline, in nautical miles.

    Worked in the local east/north frame of the query point: over the few
    miles an off-course alarm is meaningful, the flat approximation is exact
    to a fraction of a mile and avoids a spherical solve per segment.
    """
    if not coords:
        return float("inf")
    if len(coords) == 1:
        return haversine_scalar_nm(lat, lon, coords[0][0], coords[0][1])

    plat, plon = local_en_offset_nm(lat, lon, [c[0] for c in coords], [c[1] for c in coords])
    east = np.asarray(plat, dtype=np.float64)
    north = np.asarray(plon, dtype=np.float64)

    best = float(np.hypot(east, north).min())
    for index in range(len(coords) - 1):
        ax, ay = float(east[index]), float(north[index])
        bx, by = float(east[index + 1]), float(north[index + 1])
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 <= 0.0:
            continue
        # Project the origin onto the segment, then clamp. The clamp has to
        # come after the division: `max(0.0, min(1.0, dot) / length2)`
        # divides an already-clamped numerator, which collapses t to almost
        # zero on any long segment and reduces the answer to "distance to
        # the nearest waypoint". That over-reports cross-track distance by
        # tens of miles for a ship sailing straight down the middle of a
        # long leg — a guaranteed false off-course alarm.
        t = ((0.0 - ax) * dx + (0.0 - ay) * dy) / length2
        t = max(0.0, min(1.0, t))
        best = min(best, math.hypot(0.0 - (ax + t * dx), 0.0 - (ay + t * dy)))
    return float(best)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def _draft(ctx: Context) -> tuple[float | None, str | None]:
    """``(draught, origin)``: reported, else the blueprint's loaded draught.

    The live value wins because it is a measurement; the blueprint value is
    a configuration. Either is better than no draught at all, and the one
    actually used is named in the payload.
    """
    for value, origin in (
        (ctx.state.draft if ctx.state else None, "reported"),
        (ctx.vessel.draft_loaded_m if ctx.vessel else None, "blueprint"),
    ):
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed) and parsed > 0:
            return parsed, origin
    return None, None


def rule_ukc(ctx: Context) -> Candidate | None:
    if not ctx.has_position or ctx.fields.bathy is None:
        return None
    draft, origin = _draft(ctx)
    if draft is None:
        return None
    depth = sample_field(ctx.fields.bathy, ctx.lat, ctx.lon)
    if depth is None:
        return None

    margin = get_settings().ROUTE_UKC_MARGIN_M
    clearance = depth - draft
    if clearance >= margin:
        return None

    severity = "critical" if clearance < 0 else "warning"
    if clearance < 0:
        message = (
            f"Under-keel clearance {clearance:.1f} m — keel is below the sea bed "
            f"({depth:.1f} m depth, {draft:.1f} m {origin} draught)"
        )
    else:
        message = (
            f"Under-keel clearance {clearance:.1f} m is below the required "
            f"{margin:.1f} m ({depth:.1f} m depth, {draft:.1f} m {origin} draught)"
        )
    return Candidate(
        severity=severity,
        type="ukc",
        rule="ukc",
        message=message,
        payload={
            "rule": "ukc",
            "depth_m": round(depth, 2),
            "draft_m": round(draft, 2),
            "draft_source": origin,
            "clearance_m": round(clearance, 2),
            "margin_m": margin,
        },
        lat=ctx.lat,
        lon=ctx.lon,
        vessel_id=ctx.vessel_id,
    )


def rule_collision(ctx: Context) -> Candidate | None:
    """Worst CPA inside the operator's threshold, if any target breaches it.

    CPA is read from the enriched target list rather than recomputed, so the
    number in the alarm is the same number the AIS panel is showing. A target
    with no CPA has no own-ship fix to measure from and is skipped.
    """
    if not ctx.has_position or not ctx.ais_targets:
        return None

    threshold = get_settings().ALARM_CPA_NM
    worst = None
    for target in ctx.ais_targets:
        cpa_nm = target.get("cpa_nm")
        if cpa_nm is None or not math.isfinite(float(cpa_nm)) or float(cpa_nm) > threshold:
            continue
        if worst is None or float(cpa_nm) < float(worst.get("cpa_nm")):
            worst = target

    if worst is None:
        return None

    cpa_nm = float(worst["cpa_nm"])
    tcpa_min = worst.get("tcpa_min")
    tcpa_min = round(float(tcpa_min), 1) if tcpa_min is not None else None
    name = worst.get("name") or "unnamed"
    when = f" in {tcpa_min:.0f} min" if tcpa_min is not None else ""
    return Candidate(
        severity="critical",
        type="collision",
        rule="collision",
        message=(
            f"CPA {cpa_nm:.2f} nm with {name} (MMSI {worst['mmsi']}){when} — "
            f"inside the {threshold:.1f} nm limit"
        ),
        payload={
            "rule": "collision",
            "mmsi": int(worst["mmsi"]),
            "name": worst.get("name"),
            "cpa_nm": round(cpa_nm, 3),
            "tcpa_min": tcpa_min,
            "threshold_nm": threshold,
        },
        lat=ctx.lat,
        lon=ctx.lon,
        vessel_id=ctx.vessel_id,
    )


def rule_ice_concentration(ctx: Context) -> Candidate | None:
    if not ctx.has_position or ctx.fields.sic is None or ctx.vessel is None:
        return None
    if ctx.vessel.max_sic is None or not math.isfinite(float(ctx.vessel.max_sic)):
        return None
    limit = float(ctx.vessel.max_sic)
    value = sample_field(ctx.fields.sic, ctx.lat, ctx.lon)
    if value is None or value <= limit:
        return None
    return Candidate(
        severity="warning",
        type="ice",
        rule="ice_concentration",
        message=(
            f"Sea-ice concentration {value:.2f} at own position exceeds the "
            f"vessel limit {limit:.2f}"
        ),
        payload={
            "rule": "ice_concentration",
            "sic": round(float(value), 3),
            "limit": limit,
            "field": ctx.fields.sic_label,
        },
        lat=ctx.lat,
        lon=ctx.lon,
        vessel_id=ctx.vessel_id,
    )


def rule_ice_thickness(ctx: Context) -> Candidate | None:
    if not ctx.has_position or ctx.fields.thickness is None or ctx.vessel is None:
        return None
    if ctx.vessel.max_ice_thickness_m is None:
        return None
    limit = float(ctx.vessel.max_ice_thickness_m)
    if not math.isfinite(limit):
        return None
    value = sample_field(ctx.fields.thickness, ctx.lat, ctx.lon)
    if value is None or value <= limit:
        return None
    return Candidate(
        severity="critical",
        type="ice",
        rule="ice_thickness",
        message=(
            f"Ice thickness {value:.2f} m exceeds the certified hull limit "
            f"{limit:.2f} m"
        ),
        payload={
            "rule": "ice_thickness",
            "thickness_m": round(float(value), 3),
            "limit_m": limit,
        },
        lat=ctx.lat,
        lon=ctx.lon,
        vessel_id=ctx.vessel_id,
    )


def rule_iceberg(ctx: Context) -> Candidate | None:
    if not ctx.has_position or not ctx.fields.icebergs:
        return None

    threshold = get_settings().ALARM_ICEBERG_NM
    nearest = None
    for berg in ctx.fields.icebergs:
        distance = haversine_scalar_nm(ctx.lat, ctx.lon, berg.lat, berg.lon)
        if nearest is None or distance < nearest[0]:
            nearest = (distance, berg)
    if nearest is None:
        return None
    distance, berg = nearest
    if not math.isfinite(distance) or distance >= threshold:
        return None

    severity = "critical" if distance <= threshold / 2.0 else "warning"
    return Candidate(
        severity=severity,
        type="iceberg",
        rule="iceberg_proximity",
        message=(
            f"Iceberg {berg.iceberg_id} {distance:.1f} nm away, inside the "
            f"{threshold:.0f} nm limit"
        ),
        payload={
            "rule": "iceberg_proximity",
            "iceberg_id": berg.iceberg_id,
            "distance_nm": round(float(distance), 2),
            "threshold_nm": threshold,
            "length_km": berg.length_km,
        },
        lat=ctx.lat,
        lon=ctx.lon,
        vessel_id=ctx.vessel_id,
    )


def rule_off_course(ctx: Context) -> Candidate | None:
    if not ctx.has_position or not ctx.route_coords:
        return None
    threshold = get_settings().ALARM_OFF_COURSE_NM
    distance = cross_track_nm(ctx.lat, ctx.lon, ctx.route_coords)
    if not math.isfinite(distance) or distance <= threshold:
        return None
    return Candidate(
        severity="caution",
        type="off_course",
        rule="off_course",
        message=(
            f"Own ship {distance:.1f} nm off the planned track "
            f"(limit {threshold:.1f} nm)"
        ),
        payload={
            "rule": "off_course",
            "cross_track_nm": round(float(distance), 2),
            "threshold_nm": threshold,
        },
        lat=ctx.lat,
        lon=ctx.lon,
        vessel_id=ctx.vessel_id,
    )


#: Position rules, evaluated in severity order: the highest-consequence
#: condition is checked first so a vessel in several kinds of trouble at once
#: still reports its critical alarm first in the log.
VESSEL_RULES = (
    rule_ukc,
    rule_collision,
    rule_ice_thickness,
    rule_ice_concentration,
    rule_iceberg,
    rule_off_course,
)


def staleness_candidate(now: datetime, fields: Fields | None = None) -> Candidate | None:
    """The single ``forecast_stale`` rule: operational feeds older than the limit.

    Sources that have never been fetched are skipped — a fresh deployment
    with no credentials must not alarm on every pass about data nobody
    asked it to go and get. Sources on a deliberately slower cadence
    (weekly thickness, static bathymetry) are excluded by
    :data:`STALENESS_KEYS` for the same reason.
    """
    settings = get_settings()
    threshold = float(settings.ALARM_STALENESS_HOURS)

    stale: dict[str, float] = {}
    rows = version_service.get_all()
    for key in STALENESS_KEYS:
        row = rows.get(key)
        if row is None or row.version <= 0:
            continue
        updated = row.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_h = (now - updated).total_seconds() / 3600.0
        if age_h > threshold:
            stale[key] = round(age_h, 1)

    if not stale:
        return None

    worst_source = max(stale, key=stale.get)
    return Candidate(
        severity="warning",
        type="forecast_stale",
        rule="operational_staleness",
        message=(
            f"Operational data source {worst_source!r} is {stale[worst_source]:.1f} h "
            f"old, past the {threshold:.0f} h limit"
        ),
        payload={
            "rule": "operational_staleness",
            "sources": stale,
            "threshold_hours": threshold,
        },
        lat=None,
        lon=None,
        vessel_id=None,
    )


# ---------------------------------------------------------------------------
# Deduplication and persistence
# ---------------------------------------------------------------------------
def _suppressed(session, candidate: Candidate, now: datetime) -> bool:
    """True when this rule already has a live alarm, or was acked too recently."""
    settings = get_settings()

    def _statement(acked: bool):
        statement = select(Alarm.ts).where(Alarm.type == candidate.type)
        if candidate.type != "forecast_stale":
            # Data-quality alarms are global; every other type belongs to a
            # ship, and one ship's alarm must not mute another's.
            statement = statement.where(Alarm.vessel_id == candidate.vessel_id)
        if candidate.type == "ice":
            statement = statement.where(
                Alarm.payload["rule"].astext == candidate.rule
            )
        if acked:
            cutoff = now - timedelta(hours=float(settings.ALARM_REARM_HOURS))
            return statement.where(Alarm.acked_at.is_not(None)).where(
                Alarm.acked_at >= cutoff
            )
        return statement.where(Alarm.acked_at.is_(None))

    for acked in (False, True):
        if session.execute(_statement(acked).limit(1)).first() is not None:
            return True
    return False


def _persist(candidate: Candidate, now: datetime) -> dict | None:
    """Write the alarm and push it, or ``None`` when it could not be written."""
    from app.services.sic_scheduler import create_alarm

    geom_wkt = (
        f"POINT({candidate.lon:.6f} {candidate.lat:.6f})"
        if candidate.lat is not None and candidate.lon is not None
        else None
    )
    result = create_alarm(
        severity=candidate.severity,
        type=candidate.type,
        message=candidate.message,
        payload={**candidate.payload, "rule": candidate.rule},
        vessel_id=candidate.vessel_id,
        geom_wkt=geom_wkt,
        ts=now,
    )
    if result.get("id") is None:
        return None

    payload = alarm_service.serialize_by_id(int(result["id"]))
    if payload is None:
        return None
    alarm_service.publish_alarm(payload)
    return payload


def evaluate(
    vessel_id: int,
    *,
    now: datetime | None = None,
    fields: Fields | None = None,
    persist: bool = True,
) -> list[dict]:
    """Run every position rule for one vessel. Returns the alarms created."""
    now = now or datetime.now(timezone.utc)
    ctx = load_context(vessel_id, now, fields)

    state_age_ok = False
    if ctx.state is not None and ctx.state.ts is not None:
        ts = ctx.state.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        state_age_ok = (now - ts).total_seconds() <= OWN_SHIP_MAX_AGE_H * 3600.0
    if ctx.vessel is None or ctx.state is None or not state_age_ok:
        # No blueprint, or no recent fix: every position rule would be
        # guessing. Skipping is the honest answer.
        return []

    created: list[dict] = []
    with version_service.open_session() as session:
        for rule in VESSEL_RULES:
            try:
                candidate = rule(ctx)
            except Exception:  # noqa: BLE001 — one broken rule must not stop the rest
                logger.exception("alarm rule %s failed", getattr(rule, "__name__", rule))
                continue
            if candidate is None:
                continue
            if _suppressed(session, candidate, now):
                logger.debug(
                    "alarm %s/%s suppressed: already active",
                    candidate.type, candidate.rule,
                )
                continue
            if persist:
                payload = _persist(candidate, now)
                if payload is not None:
                    created.append(payload)
            else:
                # Dry evaluation: report what *would* have been raised, with
                # no id, so a caller can inspect the rules without a write.
                created.append({
                    "id": None,
                    "ts": now.isoformat(),
                    "severity": candidate.severity,
                    "type": candidate.type,
                    "message": candidate.message,
                    "payload": candidate.payload,
                })
    return created


def evaluate_staleness(
    *, now: datetime | None = None, persist: bool = True
) -> list[dict]:
    """Run the global staleness rule. Evaluated once per pass, not per ship."""
    now = now or datetime.now(timezone.utc)
    try:
        candidate = staleness_candidate(now)
    except Exception:  # noqa: BLE001
        logger.exception("staleness rule failed")
        return []
    if candidate is None:
        return []
    with version_service.open_session() as session:
        if _suppressed(session, candidate, now):
            return []
        if not persist:
            return [{
                "id": None,
                "ts": now.isoformat(),
                "severity": candidate.severity,
                "type": candidate.type,
                "message": candidate.message,
                "payload": candidate.payload,
            }]
        payload = _persist(candidate, now)
    return [payload] if payload else []


def vessels_with_recent_telemetry(now: datetime) -> list[int]:
    """Vessel ids that reported a position inside the own-ship freshness window."""
    cutoff = now - timedelta(hours=OWN_SHIP_MAX_AGE_H)
    with version_service.open_session() as session:
        rows = session.execute(
            text(
                "SELECT DISTINCT vessel_id FROM vessel_state "
                "WHERE vessel_id IS NOT NULL AND ts >= :cutoff ORDER BY vessel_id"
            ),
            {"cutoff": cutoff},
        ).scalars().all()
    return [int(row) for row in rows]


def run_pass(*, now: datetime | None = None, persist: bool = True) -> dict:
    """One full alarm pass: every ship with a recent fix, then staleness."""
    now = now or datetime.now(timezone.utc)
    started = datetime.now(timezone.utc)

    vessels = vessels_with_recent_telemetry(now)
    fields = load_fields(now)
    created: list[dict] = []
    for vessel_id in vessels:
        created.extend(evaluate(vessel_id, now=now, fields=fields, persist=persist))
    created.extend(evaluate_staleness(now=now, persist=persist))

    report = {
        "checked_at": now.isoformat(),
        "duration_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        "vessels": vessels,
        "fields": {
            "sic": fields.sic_label,
            "thickness": fields.thickness is not None,
            "bathymetry": fields.bathy is not None,
            "icebergs": len(fields.icebergs),
        },
        "created": [payload["id"] for payload in created],
    }
    if created:
        logger.warning("alarm pass raised %d alarm(s)", len(created))
    else:
        logger.info(
            "alarm pass: no new alarms (%d vessel(s) checked)", len(vessels)
        )
    return report
