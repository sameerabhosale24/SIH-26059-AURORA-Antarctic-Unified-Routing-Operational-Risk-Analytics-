"""Alarm rules: they fire when they should, and stay silent when they cannot.

No PostgreSQL, no Redis, no field files. Each test builds a
:class:`~app.services.alarm_engine.Context` by hand and calls one rule, so
a green run says the rules are right rather than that a database happened
to be populated.

Two properties matter more than any individual threshold:

* **No data, no alarm.** A missing bathymetry file, an empty AIS list, a
  void in the field — each must leave the rule silent. Returning a
  fabricated "clear" would be indistinguishable from a real all-clear on
  the operator's console, which is the failure this system exists to
  avoid.
* **The types stay inside the frontend's set.** ``Alarm.type`` is a closed
  union in ``aurora-frontend/src/types/alarm.ts``; anything outside it
  renders as an unknown chip.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.config import get_settings
from app.models import Vessel, VesselState
from app.services import alarm_engine as engine
from app.services.iceberg_proximity import Iceberg
from app.utils.constants import ROI_SHAPE
from app.utils.grid import cell_index

#: ``aurora-frontend/src/types/alarm.ts`` — ``Alarm['type']``.
ALLOWED_ALARM_TYPES = {"ukc", "collision", "ice", "iceberg", "off_course", "forecast_stale"}

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
OWN_LAT, OWN_LON = -70.0, 40.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def make_vessel(**overrides) -> Vessel:
    values = dict(
        id=1,
        user_id=1,
        name="AURORA Test",
        has_helideck=False,
        has_hangar=False,
        has_rov=False,
        draft_loaded_m=9.0,
        max_sic=0.7,
        max_ice_thickness_m=1.0,
        economical_speed_kt=12.0,
        speed_in_ice_kt=6.0,
    )
    values.update(overrides)
    return Vessel(**values)


def make_state(**overrides) -> VesselState:
    values = dict(
        ts=NOW,
        vessel_id=1,
        lat=OWN_LAT,
        lon=OWN_LON,
        draft=9.0,
        sog=11.0,
        source="gps",
    )
    values.update(overrides)
    return VesselState(**values)


def field(value: float, *, shape=ROI_SHAPE) -> np.ndarray:
    return np.full(shape, value, dtype=np.float32)


def make_context(
    *,
    vessel: Vessel | None = None,
    state: VesselState | None = None,
    fields: engine.Fields | None = None,
    route_coords: list[tuple[float, float]] | None = None,
    ais_targets: list[dict] | None = None,
) -> engine.Context:
    return engine.Context(
        vessel_id=1,
        now=NOW,
        vessel=make_vessel() if vessel is None else vessel,
        state=make_state() if state is None else state,
        fields=engine.Fields() if fields is None else fields,
        route_coords=route_coords,
        ais_targets=ais_targets or [],
    )


# ---------------------------------------------------------------------------
# Under-keel clearance
# ---------------------------------------------------------------------------
def _shallow_context(depth: float) -> engine.Context:
    bathy = field(2000.0)
    bathy[cell_index(OWN_LAT, OWN_LON)] = depth
    return make_context(fields=engine.Fields(bathy=bathy))


def test_ukc_warns_when_clearance_is_below_the_margin():
    # 10.5 m depth, 9 m draft, 2 m margin: 1.5 m left over.
    candidate = engine.rule_ukc(_shallow_context(10.5))

    assert candidate is not None
    assert candidate.type == "ukc"
    assert candidate.severity == "warning"
    assert candidate.payload["clearance_m"] == pytest.approx(1.5)
    assert candidate.payload["margin_m"] == 2.0
    assert candidate.payload["draft_source"] == "reported"
    assert (candidate.lat, candidate.lon) == (OWN_LAT, OWN_LON)


def test_ukc_is_critical_once_the_keel_is_below_the_bed():
    candidate = engine.rule_ukc(_shallow_context(5.0))

    assert candidate is not None
    assert candidate.severity == "critical"
    assert candidate.payload["clearance_m"] < 0


def test_ukc_is_silent_on_deep_water():
    assert engine.rule_ukc(_shallow_context(2000.0)) is None


def test_ukc_is_silent_when_bathymetry_is_missing():
    assert engine.rule_ukc(make_context(fields=engine.Fields(bathy=None))) is None


def test_ukc_is_silent_on_a_data_void():
    """NaN means "unknown here", not "deep enough here"."""
    assert engine.rule_ukc(make_context(fields=engine.Fields(bathy=field(np.nan)))) is None


def test_ukc_is_silent_without_a_draft():
    ctx = _shallow_context(5.0)
    ctx.state.draft = None
    ctx.vessel.draft_loaded_m = None

    assert engine.rule_ukc(ctx) is None


def test_ukc_is_silent_without_a_position():
    ctx = _shallow_context(5.0)
    ctx.state.lat = None

    assert engine.rule_ukc(ctx) is None
    assert not ctx.has_position


# ---------------------------------------------------------------------------
# Collision
# ---------------------------------------------------------------------------
def _target(cpa_nm, **overrides) -> dict:
    target = {
        "mmsi": 431001234,
        "name": "Test Tanker",
        "lat": OWN_LAT + 0.1,
        "lon": OWN_LON + 0.1,
        "cpa_nm": cpa_nm,
        "tcpa_min": 18.0,
    }
    target.update(overrides)
    return target


def test_collision_uses_the_precomputed_cpa_from_the_ais_feed():
    candidate = engine.rule_collision(make_context(ais_targets=[_target(0.42)]))

    assert candidate is not None
    assert candidate.type == "collision"
    assert candidate.severity == "critical"
    # The alarm must quote the same number the AIS panel is showing.
    assert candidate.payload["cpa_nm"] == 0.42
    assert candidate.payload["mmsi"] == 431001234
    assert candidate.payload["threshold_nm"] == 1.0


def test_collision_picks_the_worst_target_of_several():
    candidates = [_target(0.9), _target(0.3, name="Close One"), _target(0.6)]
    candidate = engine.rule_collision(make_context(ais_targets=candidates))

    assert candidate is not None
    assert candidate.payload["name"] == "Close One"
    assert candidate.payload["cpa_nm"] == 0.3


def test_collision_is_silent_when_every_target_is_outside_the_limit():
    assert engine.rule_collision(make_context(ais_targets=[_target(5.0)])) is None


def test_collision_is_silent_when_no_target_has_a_cpa():
    """No CPA means no own-ship fix to measure from — not "a wide pass"."""
    assert engine.rule_collision(make_context(ais_targets=[_target(None)])) is None
    assert engine.rule_collision(make_context(ais_targets=[_target(np.nan)])) is None


def test_collision_is_silent_without_targets_or_position():
    assert engine.rule_collision(make_context()) is None

    ctx = make_context(ais_targets=[_target(0.1)])
    ctx.state.lat = None
    assert engine.rule_collision(ctx) is None


# ---------------------------------------------------------------------------
# Ice
# ---------------------------------------------------------------------------
def test_ice_concentration_fires_only_above_the_hull_limit():
    sic = field(0.1)
    sic[cell_index(OWN_LAT, OWN_LON)] = 0.92

    candidate = engine.rule_ice_concentration(make_context(fields=engine.Fields(sic=sic)))

    assert candidate is not None
    assert candidate.type == "ice"
    assert candidate.rule == "ice_concentration"
    assert candidate.severity == "warning"
    assert candidate.payload["sic"] == pytest.approx(0.92)
    assert candidate.payload["limit"] == 0.7


def test_ice_concentration_is_silent_below_the_limit():
    sic = field(0.4)
    assert engine.rule_ice_concentration(make_context(fields=engine.Fields(sic=sic))) is None


def test_ice_thickness_fires_above_the_certified_limit():
    thickness = field(0.2)
    thickness[cell_index(OWN_LAT, OWN_LON)] = 1.8

    candidate = engine.rule_ice_thickness(make_context(fields=engine.Fields(thickness=thickness)))

    assert candidate is not None
    assert candidate.type == "ice"
    assert candidate.rule == "ice_thickness"
    assert candidate.severity == "critical"
    assert candidate.payload["thickness_m"] == pytest.approx(1.8)


def test_ice_rules_are_silent_when_the_field_is_absent():
    """Concentration and thickness are different rules sharing one type."""
    assert engine.rule_ice_concentration(make_context(fields=engine.Fields())) is None
    assert engine.rule_ice_thickness(make_context(fields=engine.Fields())) is None


# ---------------------------------------------------------------------------
# Icebergs
# ---------------------------------------------------------------------------
def test_iceberg_fires_inside_the_influence_limit():
    berg = Iceberg(iceberg_id="BERG-42", lat=OWN_LAT + 0.05, lon=OWN_LON, length_km=180.0)
    candidate = engine.rule_iceberg(make_context(fields=engine.Fields(icebergs=[berg])))

    assert candidate is not None
    assert candidate.type == "iceberg"
    assert candidate.severity == "critical"  # half the 20 nm limit or closer
    assert candidate.payload["iceberg_id"] == "BERG-42"


def test_iceberg_is_silent_outside_the_limit():
    berg = Iceberg(iceberg_id="FAR-1", lat=OWN_LAT + 2.0, lon=OWN_LON)
    assert engine.rule_iceberg(make_context(fields=engine.Fields(icebergs=[berg]))) is None


def test_iceberg_is_silent_when_the_table_is_empty():
    assert engine.rule_iceberg(make_context(fields=engine.Fields(icebergs=[]))) is None


# ---------------------------------------------------------------------------
# Off course
# ---------------------------------------------------------------------------
def test_off_course_fires_beyond_the_limit():
    limit = get_settings().ALARM_OFF_COURSE_NM
    # A track one degree of latitude north of the own ship: far enough over
    # the flat-frame approximation that the distance is unambiguous.
    coords = [(OWN_LAT + 1.0, OWN_LON - 2.0), (OWN_LAT + 1.0, OWN_LON + 2.0)]
    candidate = engine.rule_off_course(make_context(route_coords=coords))

    assert candidate is not None
    assert candidate.type == "off_course"
    assert candidate.severity == "caution"
    assert candidate.payload["cross_track_nm"] > limit
    assert candidate.payload["threshold_nm"] == limit


def test_off_course_is_silent_on_the_track():
    coords = [(OWN_LAT, OWN_LON - 1.0), (OWN_LAT, OWN_LON + 1.0)]
    assert engine.rule_off_course(make_context(route_coords=coords)) is None


def test_cross_track_is_zero_anywhere_on_a_long_leg():
    """Regression: the projection clamp ran before the division.

    The old expression evaluated ``max(0, min(1, dot) / length2)``, so on a
    long segment ``t`` collapsed to almost zero and the answer became the
    distance to the nearest waypoint. A ship sailing straight down the
    middle of a leg hundreds of miles long reported 20+ nm of cross-track
    error and raised an off-course alarm that was simply not true.
    """
    coords = [(-70.0, 20.0), (-70.0, 60.0)]

    assert engine.cross_track_nm(-70.0, 40.0, coords) == pytest.approx(0.0, abs=0.5)


def test_cross_track_measures_the_perpendicular_distance():
    coords = [(-70.0, 20.0), (-70.0, 60.0)]

    distance = engine.cross_track_nm(-69.0, 40.0, coords)

    assert 59.0 < distance < 61.0, "one degree of latitude is about 60 nm"


def test_cross_track_clamps_to_the_end_of_the_leg():
    """Beyond the first or last waypoint the answer is the distance to it."""
    coords = [(-70.0, 39.0), (-70.0, 39.5)]  # entirely west of the own ship

    distance = engine.cross_track_nm(-70.0, 40.0, coords)

    # Half a degree of longitude at 70°S is about 10.3 nm.
    assert distance == pytest.approx(10.3, rel=0.05)


def test_off_course_is_silent_without_a_route():
    assert engine.rule_off_course(make_context(route_coords=None)) is None
    assert engine.rule_off_course(make_context(route_coords=[])) is None


# ---------------------------------------------------------------------------
# Cross-cutting guarantees
# ---------------------------------------------------------------------------
def test_every_position_rule_is_silent_without_a_fix():
    ctx = make_context(state=make_state(lat=None, lon=None))

    for rule in engine.VESSEL_RULES:
        assert rule(ctx) is None, f"{rule.__name__} alarmed on a vessel with no position"


def test_every_rule_returns_a_type_the_frontend_understands():
    sic = field(0.9)
    thickness = field(1.8)
    bathy = field(3.0)
    berg = Iceberg(iceberg_id="BERG-42", lat=OWN_LAT + 0.05, lon=OWN_LON)
    ctx = make_context(
        fields=engine.Fields(sic=sic, thickness=thickness, bathy=bathy, icebergs=[berg]),
        route_coords=[(OWN_LAT, OWN_LON + 3.0), (OWN_LAT, OWN_LON + 5.0)],
        ais_targets=[_target(0.2)],
    )

    raised = [c for c in (rule(ctx) for rule in engine.VESSEL_RULES) if c is not None]
    assert len(raised) >= 4, "expected several rules to fire in this context"
    for candidate in raised:
        assert candidate.type in ALLOWED_ALARM_TYPES, candidate.type
        assert candidate.severity in {"critical", "warning", "caution"}
        assert candidate.vessel_id == 1


def test_a_vessel_with_only_open_water_raises_nothing():
    """The base case: everything known, everything safe."""
    ctx = make_context(fields=engine.Fields(sic=field(0.05), thickness=field(0.1), bathy=field(3000.0)))

    for rule in engine.VESSEL_RULES:
        assert rule(ctx) is None, f"{rule.__name__} alarmed in open water"
