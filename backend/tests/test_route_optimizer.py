"""Route optimiser: hard blocks, A*, infeasibility, variant separation.

Everything here runs without PostgreSQL, Redis or a field file — the grids
are built in the test, so a green run says the planner itself is correct
rather than that a particular deployment happened to have data.

The four things worth protecting:

* **hard blocks are hard.** Land, shallows, ice over the hull limit and
  data voids must all appear in the mask, and a void must never read as
  open water.
* **A-star returns a path, and only through passable cells.** A search that
  reports success by walking through a block is worse than one that fails.
* **no path is reported as no path.** A walled-off destination must come
  back ``None``, not a truncated route dressed up as a plan.
* **the planner variants are actually different.** If every candidate is
  the same route, the Pareto front is theatre.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.config import get_settings
from app.models import Vessel
from app.services import route_optimizer as ro
from app.utils.constants import ROI_SHAPE
from app.utils.grid import roi_lat_array, roi_lon_array


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def make_vessel(**overrides) -> Vessel:
    """A fully specified blueprint — every rule has something to read."""
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
        fuel_capacity_t=1000.0,
        fuel_burn_economical_tpd=20.0,
        crane_outreach_m=5000.0,
    )
    values.update(overrides)
    return Vessel(**values)


def make_inputs(**overrides) -> ro.RouteInputs:
    """Open-water inputs: deep, ice-free, no bergs, no cones."""
    shape = ROI_SHAPE
    values = dict(
        sic=np.zeros(shape, np.float32),
        thickness=np.zeros(shape, np.float32),
        uo=np.zeros(shape, np.float32),
        vo=np.zeros(shape, np.float32),
        wind=np.full(shape, 5.0, np.float32),
        bathy=np.full(shape, 2000.0, np.float32),
        distance_to_iceberg=np.full(shape, np.inf, np.float32),
        cone_blocked=np.zeros(shape, dtype=bool),
        icebergs=[],
        vessel=make_vessel(),
    )
    values.update(overrides)
    return ro.RouteInputs(**values)


def block_report(inputs: ro.RouteInputs) -> ro.BlockReport:
    return ro.build_blocks(inputs, ukc_margin_m=get_settings().ROUTE_UKC_MARGIN_M)


def run_astar(cost: np.ndarray, blocked: np.ndarray, start, goal, limit=None):
    return ro.astar(
        cost, blocked, start, goal,
        roi_lat_array(), roi_lon_array(),
        limit if limit is not None else ro.MAX_PATH_CELLS,
    )


# ---------------------------------------------------------------------------
# Hard blocks
# ---------------------------------------------------------------------------
def test_open_water_is_fully_traversable():
    report = block_report(make_inputs())
    assert report.total == 0
    assert report.reasons["land"] == 0
    assert report.reasons["under-keel clearance"] == 0


def test_land_is_blocked_by_sign_not_by_magnitude():
    """bathy is depth positive down with land floored at 0: ``<= 0`` is land."""
    inputs = make_inputs(bathy=np.zeros(ROI_SHAPE, np.float32))
    report = block_report(inputs)
    assert report.reasons["land"] == report.mask.size

    inputs = make_inputs(bathy=np.full(ROI_SHAPE, 0.5, np.float32))
    report = block_report(inputs)
    assert report.reasons["land"] == 0


def test_every_hard_rule_lands_in_the_mask():
    """Land, shallows, hull limits, a void and a cone — each blocks its own cells."""
    inputs = make_inputs()

    # 5x5 stamps, all disjoint.
    land = np.s_[0:5, 0:5]
    shallow = np.s_[10:15, 10:15]          # 5 m under a 9 m draft
    void = np.s_[20:25, 20:25]             # NaN depth: no data, not open water
    sic_over = np.s_[30:35, 30:35]         # 0.9 over the 0.7 limit
    thick_over = np.s_[40:45, 40:45]       # 2.0 m over the 1.0 m hull limit
    cone = np.s_[50:55, 50:55]
    void_thickness = np.s_[60:65, 60:65]   # NaN thickness where SIC says ice

    inputs.bathy[land] = 0.0
    inputs.bathy[shallow] = 5.0
    inputs.bathy[void] = np.nan
    inputs.sic[sic_over] = 0.9
    inputs.thickness[thick_over] = 2.0
    inputs.cone_blocked[cone] = True
    inputs.sic[void_thickness] = 0.5
    inputs.thickness[void_thickness] = np.nan

    report = block_report(inputs)

    assert report.reasons["land"] == 25
    # Shallow water, plus the land stamp — a cell with no water column is
    # also the cell with the least clearance. Both are blocked either way.
    assert report.reasons["under-keel clearance"] == 50
    assert report.reasons["sic over limit"] == 25
    assert report.reasons["thickness over limit"] == 25
    assert report.reasons["drift cone"] == 25
    # Two voids: the NaN depth stamp, and the NaN thickness stamp where SIC
    # is above the MIZ threshold. A void is never counted as open water.
    assert report.reasons["unknown input"] == 50

    for region in (land, shallow, void, sic_over, thick_over, cone, void_thickness):
        assert report.mask[region].all()


def test_data_void_is_blocked_not_assumed_safe():
    inputs = make_inputs(bathy=np.full(ROI_SHAPE, np.nan, np.float32))
    report = block_report(inputs)
    assert report.mask.all()
    assert report.reasons["unknown input"] == report.mask.size
    assert report.reasons["land"] == 0  # NaN is not land either


def test_ukc_margin_is_configurable():
    inputs = make_inputs(bathy=np.full(ROI_SHAPE, 10.5, np.float32))  # 10.5 - 9 = 1.5 m left
    assert block_report(inputs).reasons["under-keel clearance"] == ROI_SHAPE[0] * ROI_SHAPE[1]

    satisfied = ro.build_blocks(inputs, ukc_margin_m=0.0)
    assert satisfied.reasons["under-keel clearance"] == 0
    assert satisfied.total == 0


# ---------------------------------------------------------------------------
# A*
# ---------------------------------------------------------------------------
def test_astar_returns_a_connected_path_through_open_water():
    start, goal = (50, 10), (50, 200)
    cost = np.ones(ROI_SHAPE, np.float32)
    path = run_astar(cost, np.zeros(ROI_SHAPE, bool), start, goal)

    assert path is not None
    assert path[0] == start and path[-1] == goal
    assert len(path) > 1
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        assert max(abs(r1 - r0), abs(c1 - c0)) == 1, "steps must be 8-connected"


def test_astar_returns_none_when_the_goal_is_walled_off():
    cost = np.ones(ROI_SHAPE, np.float32)
    blocked = np.zeros(ROI_SHAPE, bool)
    blocked[:, 180:183] = True  # full-height wall, no gap

    assert run_astar(cost, blocked, (50, 50), (50, 300)) is None


def test_astar_refuses_start_or_goal_inside_a_block():
    cost = np.ones(ROI_SHAPE, np.float32)
    blocked = np.zeros(ROI_SHAPE, bool)
    blocked[50, 50] = True

    assert run_astar(cost, blocked, (50, 50), (50, 300)) is None
    assert run_astar(cost, blocked, (10, 10), (50, 50)) is None


def test_astar_never_steps_into_a_blocked_cell():
    cost = np.ones(ROI_SHAPE, np.float32)
    blocked = np.zeros(ROI_SHAPE, bool)
    blocked[:, 180:183] = True
    blocked[25:30, 180:183] = False  # a single gap to aim for

    path = run_astar(cost, blocked, (50, 50), (50, 300))
    assert path is not None
    for cell in path:
        assert not blocked[cell], f"A* walked into a blocked cell {cell}"


def test_astar_gives_up_rather_than_searching_forever():
    cost = np.ones(ROI_SHAPE, np.float32)
    blocked = np.zeros(ROI_SHAPE, bool)
    blocked[:, 180:183] = True

    assert run_astar(cost, blocked, (50, 50), (50, 300), limit=50) is None


# ---------------------------------------------------------------------------
# Cost sensitivity — the mechanism behind distinct planner variants
# ---------------------------------------------------------------------------
GAP_A = range(25, 30)   # near gap — the short way through the wall
GAP_B = range(75, 80)   # far gap — the long way round


def _two_corridor_cost(expensive: bool) -> tuple[np.ndarray, np.ndarray]:
    """A wall with a short gap near the start and a longer gap far from it.

    With a flat cost the search must take the near gap. Raising the cost of
    the near gap's approach makes the long way round cheaper — the same
    trade the ice weights in :data:`VARIANT_SPECS` make in production.
    """
    cost = np.ones(ROI_SHAPE, np.float32)
    blocked = np.zeros(ROI_SHAPE, bool)
    blocked[:, 180:183] = True
    blocked[25:30, 180:183] = False   # gap A — close to the start
    blocked[75:80, 180:183] = False   # gap B — far from the start

    if expensive:
        cost[20:36, 150:210] = 100.0  # the ice that makes gap A the slow way
    return cost, blocked


def _gap_used(path, col=181) -> int | None:
    """The row at which ``path`` crosses ``col``, or None if it never does."""
    for row, c in path:
        if c == col:
            return row
    return None


def test_astar_follows_the_cheaper_of_two_gaps():
    cost, blocked = _two_corridor_cost(expensive=False)
    path = run_astar(cost, blocked, (50, 50), (50, 300))
    assert path is not None
    assert _gap_used(path) in GAP_A, "flat cost must take the short gap"


def test_astar_takes_the_long_gap_when_the_short_one_is_expensive():
    cost, blocked = _two_corridor_cost(expensive=True)
    path = run_astar(cost, blocked, (50, 50), (50, 300))
    assert path is not None
    assert _gap_used(path) in GAP_B, "expensive short gap must be avoided"


def test_weighting_the_short_gap_differently_produces_a_different_route():
    """The property the four planner variants depend on.

    If a change in the component weights never changes the chosen path,
    every candidate route is the same route and the alternatives panel is
    showing one plan four times.
    """
    cheap, blocked = _two_corridor_cost(expensive=False)
    dear, _ = _two_corridor_cost(expensive=True)

    short_route = run_astar(cheap, blocked, (50, 50), (50, 300))
    safe_route = run_astar(dear, blocked, (50, 50), (50, 300))

    assert short_route is not None and safe_route is not None
    assert set(short_route) != set(safe_route)
    assert ro.jaccard_cells(set(short_route), set(safe_route)) < 1.0


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------
def test_every_variant_resolves_to_a_distinct_weight_vector():
    resolved = {name: ro.resolve_weights(spec) for name, spec in ro.VARIANT_SPECS.items()}
    serialised = {name: tuple(sorted(w.items())) for name, w in resolved.items()}

    assert len(set(serialised.values())) == len(serialised), (
        "two planner variants share a weight vector, so they cannot differ"
    )

    balanced = resolved["balanced"]
    assert balanced["fuel"] == get_settings().ROUTE_WEIGHT_FUEL
    assert resolved["alt-fastest"]["fuel"] == balanced["fuel"] * 0.5
    for key in ("ice", "thickness", "iceberg"):
        assert resolved["alt-safest"][key] == balanced[key] * 1.5
    assert resolved["alt-fuel"]["fuel"] == balanced["fuel"] * 1.5


def test_blocked_cells_cost_infinity_and_never_a_number():
    inputs = make_inputs()
    inputs.cone_blocked[40:60, 40:60] = True
    report = block_report(inputs)
    cost = ro.combine(
        inputs,
        weights=ro.resolve_weights(ro.VARIANT_SPECS["balanced"]),
        destination=(-70.0, 40.0),
        blocks=report,
    )

    assert np.isinf(cost[50, 50])
    assert np.isfinite(cost[0, 0]).all()
    assert (cost >= 0).all(), "a cost grid must not go negative"


def test_combined_score_prefers_lower_risk_for_the_same_fuel():
    vessel = make_vessel()
    risky = ro.RouteMetrics(distance_nm=100.0, eta=None, fuel_estimate_t=10.0, risk_score=0.9)
    calm = ro.RouteMetrics(distance_nm=100.0, eta=None, fuel_estimate_t=10.0, risk_score=0.1)

    assert ro.combined_score(calm, vessel) < ro.combined_score(risky, vessel)


def test_combined_score_normalises_fuel_by_capacity():
    vessel = make_vessel(fuel_capacity_t=100.0)
    metrics = ro.RouteMetrics(distance_nm=10.0, eta=None, fuel_estimate_t=25.0, risk_score=0.0)
    assert ro.combined_score(metrics, vessel) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Path metrics
# ---------------------------------------------------------------------------
def test_path_metrics_measure_a_real_voyage():
    cells = [(50, col) for col in range(10, 40)]
    departure = (-33.925, 18.4238)  # Cape Town, outside the ROI

    coordinates, metrics = ro.path_metrics(
        cells, make_inputs(), departure, datetime(2026, 10, 1, tzinfo=timezone.utc)
    )

    assert coordinates.shape == (len(cells) + 1, 2)
    assert np.allclose(coordinates[0], departure)
    assert metrics.distance_nm > 0
    assert metrics.fuel_estimate_t is not None and metrics.fuel_estimate_t > 0
    assert metrics.eta is not None
    assert 0.0 <= metrics.risk_score <= 1.0


def test_path_metrics_refuse_to_estimate_without_a_speed_profile():
    cells = [(50, col) for col in range(10, 40)]
    inputs = make_inputs(vessel=make_vessel(economical_speed_kt=None))

    _, metrics = ro.path_metrics(
        cells, inputs, (-33.925, 18.4238), datetime(2026, 10, 1, tzinfo=timezone.utc)
    )

    assert metrics.eta is None
    assert metrics.fuel_estimate_t is None
    assert any("speed profile" in note for note in metrics.notes)


# ---------------------------------------------------------------------------
# Shelf reachability
# ---------------------------------------------------------------------------
def test_shelf_reachability_is_skipped_rather_than_guessed_without_data():
    inputs = make_inputs(vessel=make_vessel(crane_outreach_m=None))
    notes: list[str] = []
    assert ro.shelf_reachability((-70.0, 40.0), inputs, notes) is None
    assert any("not evaluated" in note for note in notes)

    inputs = make_inputs()  # reach given, but no land anywhere to reach
    notes = []
    assert ro.shelf_reachability((-70.0, 40.0), inputs, notes) is None
    assert any("no land cells" in note for note in notes)


def test_shelf_reachability_infeasible_without_a_helideck():
    bathy = np.full(ROI_SHAPE, 2000.0, np.float32)
    bathy[0, 0] = 0.0  # one land cell, thousands of nm away
    inputs = make_inputs(bathy=bathy, vessel=make_vessel(has_helideck=False))

    notes: list[str] = []
    assert ro.shelf_reachability((-50.0, 79.0), inputs, notes) == "infeasible"
    assert any("no helideck" in note for note in notes)


def test_shelf_reachability_accepts_a_standoff_when_helideck_is_available():
    bathy = np.full(ROI_SHAPE, 2000.0, np.float32)
    bathy[0, 0] = 0.0
    inputs = make_inputs(bathy=bathy, vessel=make_vessel(has_helideck=True))

    notes: list[str] = []
    assert ro.shelf_reachability((-50.0, 79.0), inputs, notes) is None
    assert any("helo resupply" in note for note in notes)
