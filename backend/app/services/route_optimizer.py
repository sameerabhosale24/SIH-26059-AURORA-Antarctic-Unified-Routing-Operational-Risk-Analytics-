"""A* route optimiser for Antarctic logistics.

Runs every six hours per active vessel. It reads the same fields the
forecaster consumes, plus static bathymetry and live iceberg positions, and
produces one recommended route with up to three Pareto alternatives — or an
honest ``infeasible``.

Three rules govern everything below:

1. **All inputs or nothing.** A missing field is a missing route, reported
   by name. Partial inputs would produce a route that looks plausible and
   is quietly wrong somewhere the operator cannot see.
2. **No zeros for unknown.** A cell whose safety inputs are not finite is
   blocked, not assumed clear.
3. **The plan explains itself.** Every run records the exact ``data_version``
   numbers it saw, so a route can be re-derived months later.

Grid geometry
-------------
The ROI is ``[101, 361]`` at 0.25 degrees with row 0 at ``ROI_LAT_MIN``
(the *southern* edge). Cape Town sits about 17 degrees north of the ROI's
northern edge, so the origin is clamped to the nearest in-ROI cell on the
Cape Town meridian and the open-water approach leg is prepended as a
separate segment. Both station destinations fall inside the ROI.
"""

from __future__ import annotations

import argparse
import heapq
import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import numpy as np

from app.config import get_settings
from app.models import Route, RouteRun, Vessel, Waypoint
from app.services import display_pipeline, field_storage, iceberg_proximity, version_service
from app.services.iceberg_proximity import Iceberg
from app.utils.constants import ROI_LAT_MIN, ROI_LON_MIN, ROI_RES, ROI_SHAPE
from app.utils.geo import KT_TO_MS, NM_TO_M, haversine_nm, haversine_scalar_nm
from app.utils.grid import cell_index, roi_lat_array, roi_lon_array

logger = logging.getLogger("aurora.route")

#: MIZ bounds. Match the forecaster's MIZ_THRESHOLD at the lower end and
#: the alarm rule's "this is ice, not drift ice" at the upper end.
MIZ_THRESHOLD = 0.15
FULL_ICE_SIC = 0.85
#: Below this thickness there is no meaningful resistance to pay for.
MIN_ICE_THICKNESS_M = 0.5
#: Cells checked when the exact origin or destination is impassable.
NEAREST_PASSABLE_RADIUS = 8
#: An 8-connected path longer than this is not a voyage, it is a search bug.
MAX_PATH_CELLS = 20_000

#: 8-connected neighbour offsets, in (row, col) order.
DIRECTIONS: tuple[tuple[int, int], ...] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
)

#: Component weights used for each candidate route. Values come from
#: settings; the multipliers here are the PART 2 specification.
VARIANT_SPECS: dict[str, dict[str, float]] = {
    "balanced": {},
    "alt-fastest": {"fuel": 0.5},
    "alt-safest": {"ice": 1.5, "thickness": 1.5, "iceberg": 1.5},
    "alt-fuel": {"ice": 0.7, "thickness": 0.7, "iceberg": 0.7, "fuel": 1.5},
}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass
class RouteInputs:
    """Everything the cost grid is built from, already on the ROI grid."""

    sic: np.ndarray                 # [101, 361] D+1 forecast
    thickness: np.ndarray           # [101, 361]
    uo: np.ndarray                  # [101, 361] eastward current, m/s
    vo: np.ndarray                  # [101, 361] northward current, m/s
    wind: np.ndarray                # [101, 361] 10 m wind speed, m/s
    bathy: np.ndarray               # [101, 361] depth, positive down
    distance_to_iceberg: np.ndarray  # [101, 361] nm, +inf where none
    cone_blocked: np.ndarray        # [101, 361] bool
    icebergs: list[Iceberg]
    vessel: Vessel
    source_dates: dict[str, str] = field(default_factory=dict)


def _latest_field(source: str) -> tuple[np.ndarray | None, date | None]:
    """Newest stored field for ``source``, or ``(None, None)``."""
    dates = field_storage.list_available_dates(source)
    if not dates:
        return None, None
    day = dates[-1]
    array = field_storage.read_field(source, day)
    if array is None:
        return None, None
    return np.asarray(array, dtype=np.float32), day


def _as_plane(array: np.ndarray, label: str) -> np.ndarray:
    """Reduce a stored field to ``[101, 361]`` without inventing a slice."""
    if array.shape == ROI_SHAPE:
        return array
    if array.ndim == 3 and array.shape[1:] == ROI_SHAPE:
        return array[0]
    raise ValueError(
        f"{label} has shape {array.shape}, expected {ROI_SHAPE} or (C, {ROI_SHAPE})"
    )


def _load_sic_forecast(target: date) -> tuple[np.ndarray | None, date | None]:
    """The stored forecast whose horizon is closest to ``target + 1 day``.

    Only ``data/sic_arrays`` is read. Forecasts never come back in as
    observations, and the raw arrays (not the PNGs) are the only thing with
    numbers in them.
    """
    root = display_pipeline.arrays_root()
    if not root.is_dir():
        return None, None

    wanted = target + timedelta(days=1)
    best: tuple[np.ndarray | None, date | None, float] = (None, None, math.inf)
    for entry in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            day = date.fromisoformat(entry.name)
        except ValueError:
            continue
        path = entry / "median.npy"
        if not path.exists():
            continue
        try:
            median = np.load(path)
        except Exception:  # noqa: BLE001 — a corrupt file is "no forecast"
            logger.warning("unreadable forecast %s; skipping", path)
            continue
        if median.shape != (3, *ROI_SHAPE):
            logger.warning("forecast %s has shape %s; skipping", path, median.shape)
            continue
        horizon_dates = [day + timedelta(days=offset) for offset in (1, 2, 3)]
        gap = min(abs((h - wanted).days) for h in horizon_dates)
        if gap < best[2]:
            index = int(np.argmin([abs((h - wanted).days) for h in horizon_dates]))
            best = (np.asarray(median[index], dtype=np.float32), day, float(gap))
    return best[0], best[1]


def load_sic_forecast(
    target: date | None = None,
) -> tuple[np.ndarray | None, date | None]:
    """Public wrapper around :func:`_load_sic_forecast` for other layers.

    The alarm engine asks the same question the router asks — "what does the
    newest stored forecast say about this date" — and must get the same
    array, from the same directory, with the same fallback rules.
    """
    return _load_sic_forecast(target or datetime.now(timezone.utc).date())


def load_inputs(vessel_id: int, target: date) -> RouteInputs | list[str]:
    """Read every field and the vessel blueprint, or return what is missing.

    Returning a list of human-readable problems rather than raising keeps
    the caller's contract simple: either the grid can be built, or the
    reason it cannot is already formatted for ``RouteRun.notes``.
    """
    vessel = _load_vessel(vessel_id)
    if vessel is None:
        return [f"vessel {vessel_id}: not found"]

    problems: list[str] = []

    sic, sic_date = _load_sic_forecast(target)
    if sic is None:
        problems.append("sic forecast: no stored forecast in data/sic_arrays")

    thickness, thickness_date = _latest_field("ice_thickness")
    if thickness is None:
        problems.append("ice thickness: no stored field")
    else:
        thickness = _as_plane(thickness, "ice thickness")

    currents, currents_date = _latest_field("currents")
    if currents is None:
        problems.append("currents: no stored field")
    elif currents.shape != (5, *ROI_SHAPE):
        problems.append(f"currents: expected 5 channels, got {currents.shape}")
        currents = None

    weather, weather_date = _latest_field("weather")
    if weather is None:
        problems.append("weather: no stored field")
    elif weather.shape != (3, *ROI_SHAPE):
        problems.append(f"weather: expected 3 channels, got {weather.shape}")
        weather = None

    bathy_path = field_storage.bathymetry_path()
    bathy = None
    if not bathy_path.exists():
        problems.append(
            f"bathymetry: {bathy_path} missing — run scripts/download_ibcso.py"
        )
    else:
        try:
            bathy = np.asarray(np.load(bathy_path), dtype=np.float32)
            if bathy.shape != ROI_SHAPE:
                problems.append(f"bathymetry: shape {bathy.shape}, expected {ROI_SHAPE}")
                bathy = None
        except Exception as exc:  # noqa: BLE001
            problems.append(f"bathymetry: unreadable ({exc})")

    if problems:
        return problems

    icebergs = iceberg_proximity.latest_positions()
    cone = iceberg_proximity.drift_cone_mask()
    distances = iceberg_proximity.distance_grid(icebergs)

    assert sic is not None and thickness is not None and currents is not None
    assert weather is not None and bathy is not None

    return RouteInputs(
        sic=sic,
        thickness=thickness,
        uo=currents[0],
        vo=currents[1],
        wind=np.hypot(weather[0], weather[1]),
        bathy=bathy,
        distance_to_iceberg=distances,
        cone_blocked=cone,
        icebergs=icebergs,
        vessel=vessel,
        source_dates={
            "sic": sic_date.isoformat() if sic_date else None,
            "ice_thickness": thickness_date.isoformat() if thickness_date else None,
            "currents": currents_date.isoformat() if currents_date else None,
            "weather": weather_date.isoformat() if weather_date else None,
            "bathymetry": "static",
        },
    )


def _load_vessel(vessel_id: int) -> Vessel | None:
    """Fetch the blueprint synchronously — every caller here is a job thread.

    The async session cannot be awaited from a synchronous job, and building
    a second engine just for this would duplicate PART 1's setup. The sync
    engine already exists in :mod:`version_service`, so use it.
    """
    with version_service.open_session() as session:
        return session.get(Vessel, vessel_id)


# ---------------------------------------------------------------------------
# Cost components
# ---------------------------------------------------------------------------
def ice_penalty(sic: np.ndarray) -> np.ndarray:
    """0 below the MIZ threshold, rising quadratically to 1 at total cover.

    Quadratic rather than linear because the risk of an ice-covered cell is
    not twice that of a marginal cell, it is considerably more: concentration
    compounds into ridging and into the work the hull has to do.
    """
    sic = np.asarray(sic, dtype=np.float32)
    clipped = np.clip(np.where(np.isfinite(sic), sic, 0.0), 0.0, 1.0)
    span = 1.0 - MIZ_THRESHOLD
    penalty = ((clipped - MIZ_THRESHOLD) / span) ** 2
    return np.where(clipped > MIZ_THRESHOLD, penalty, 0.0).astype(np.float32)


def thickness_penalty(thickness: np.ndarray, limit_m: float | None) -> np.ndarray:
    """0 below half a metre, linear to 1 at the vessel's certified limit."""
    values = np.asarray(thickness, dtype=np.float32)
    if limit_m is None or not np.isfinite(limit_m) or limit_m <= MIN_ICE_THICKNESS_M:
        # No certified limit means no basis for a penalty; do not invent one.
        return np.zeros_like(values)
    safe = np.where(np.isfinite(values), values, 0.0)
    penalty = (safe - MIN_ICE_THICKNESS_M) / (float(limit_m) - MIN_ICE_THICKNESS_M)
    penalty = np.clip(penalty, 0.0, 1.0)
    return np.where(safe > MIN_ICE_THICKNESS_M, penalty, 0.0).astype(np.float32)


def iceberg_penalty(distance_nm: np.ndarray) -> np.ndarray:
    """``1/(1+d)`` inside 50 nm, exactly zero outside it."""
    distance = np.asarray(distance_nm, dtype=np.float32)
    inside = np.isfinite(distance) & (distance <= iceberg_proximity.ICEBERG_INFLUENCE_NM)
    penalty = np.where(inside, 1.0 / (1.0 + np.where(inside, distance, 0.0)), 0.0)
    return penalty.astype(np.float32)


def weather_penalty(wind_ms: np.ndarray, wave_m: np.ndarray | None, vessel: Vessel) -> np.ndarray:
    """Wind relative to the vessel's limit, clipped to [0, 1].

    AURORA has no wave source — the ERA5 store carries ``u10, v10, t2m``
    only — so ``wave_m`` is always ``None`` here. Passing it rather than
    silently dropping the argument keeps the specification's signature and
    makes the gap obvious to the next reader instead of hiding it.
    """
    limit_kt = vessel.max_wind_speed_kt
    if limit_kt is None or not np.isfinite(limit_kt) or limit_kt <= 0:
        return np.zeros(np.shape(wind_ms), dtype=np.float32)

    limit_ms = float(limit_kt) * KT_TO_MS
    speed = np.asarray(wind_ms, dtype=np.float32)
    safe = np.where(np.isfinite(speed), speed, 0.0)
    penalty = np.clip(safe / limit_ms, 0.0, 1.0).astype(np.float32)

    if wave_m is not None:
        wave_limit = vessel.max_wave_height_m
        if wave_limit and np.isfinite(wave_limit) and wave_limit > 0:
            wave = np.where(np.isfinite(wave_m), wave_m, 0.0)
            penalty = np.maximum(penalty, np.clip(wave / float(wave_limit), 0.0, 1.0))
    return penalty


def fuel_component(sic: np.ndarray, vessel: Vessel) -> np.ndarray:
    """Tonnes per nautical mile, normalised so open water reads 1.0.

    ``distance / speed * burn_rate`` divided by the same expression at the
    economical speed, which cancels the burn rate and leaves ``econ/speed``:
    a cell you cross at half speed costs twice the fuel per mile.
    """
    econ = vessel.economical_speed_kt
    ice_speed = vessel.speed_in_ice_kt
    if econ is None or not np.isfinite(econ) or econ <= 0:
        return np.zeros(np.shape(sic), dtype=np.float32)
    if ice_speed is None or not np.isfinite(ice_speed) or ice_speed <= 0:
        ice_speed = econ

    concentration = np.asarray(sic, dtype=np.float32)
    safe = np.where(np.isfinite(concentration), concentration, 0.0)
    speed = np.where(
        safe < MIZ_THRESHOLD, econ,
        np.where(safe <= FULL_ICE_SIC, ice_speed, ice_speed * 0.5),
    )
    return (econ / speed).astype(np.float32)


def current_component(
    uo: np.ndarray, vo: np.ndarray, destination: tuple[float, float]
) -> np.ndarray:
    """Along-track current support towards ``destination``, in ``[-1, 1]``.

    Positive means the flow helps. The bearing is taken cell-to-destination
    rather than cell-to-cell so the term is a property of the cell, which is
    what makes it combinable with the other components before A* runs.
    """
    lat = roi_lat_array()
    lon = roi_lon_array()
    lon2d, lat2d = np.meshgrid(lon, lat)

    dest_lat, dest_lon = destination
    theta = np.deg2rad(haversine_bearing_grid(lat2d, lon2d, dest_lat, dest_lon))
    east = np.asarray(uo, dtype=np.float32)
    north = np.asarray(vo, dtype=np.float32)
    along = east * np.sin(theta) + north * np.cos(theta)
    along = np.where(np.isfinite(along), along, 0.0)
    # 1 m/s of following current is a full-strength assist; anything more
    # is clamped so a single fast current cannot dominate the grid.
    return np.clip(along / 1.0, -1.0, 1.0).astype(np.float32)


def haversine_bearing_grid(lat2d: np.ndarray, lon2d: np.ndarray, dest_lat: float, dest_lon: float):
    """Vectorised bearing from every cell to one destination."""
    phi1 = np.radians(lat2d)
    phi2 = np.radians(dest_lat)
    dlon = np.radians(dest_lon - lon2d)
    y = np.sin(dlon) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlon)
    return np.degrees(np.arctan2(y, x)) % 360.0


# ---------------------------------------------------------------------------
# Hard blocks
# ---------------------------------------------------------------------------
@dataclass
class BlockReport:
    mask: np.ndarray
    reasons: dict[str, int]

    @property
    def total(self) -> int:
        return int(self.mask.sum())


def build_blocks(
    inputs: RouteInputs, *, ukc_margin_m: float
) -> BlockReport:
    """Mark every cell a ship may not enter, with a per-reason count."""
    vessel = inputs.vessel
    reasons: dict[str, int] = {}

    sic = inputs.sic
    thickness = inputs.thickness
    bathy = inputs.bathy

    # Unknown inputs. IEEE 754 makes `nan > x` False, so a literal reading
    # of the block rules would wave a ship straight through a data void.
    # Depth and concentration are never assumed; thickness only matters
    # where ice is actually reported, otherwise the CS2SMOS footprint would
    # close the whole Southern Ocean.
    unknown = ~np.isfinite(bathy) | ~np.isfinite(sic) | (~np.isfinite(thickness) & (sic > MIZ_THRESHOLD))
    mask = unknown.copy()
    reasons["unknown input"] = int(mask.sum())

    if vessel.max_ice_thickness_m is not None and np.isfinite(vessel.max_ice_thickness_m):
        hit = np.isfinite(thickness) & (thickness > vessel.max_ice_thickness_m)
        reasons["thickness over limit"] = int(hit.sum())
        mask |= hit

    if vessel.max_sic is not None and np.isfinite(vessel.max_sic):
        hit = np.isfinite(sic) & (sic > vessel.max_sic)
        reasons["sic over limit"] = int(hit.sum())
        mask |= hit

    if vessel.draft_loaded_m is not None and np.isfinite(vessel.draft_loaded_m):
        # bathy is depth, positive down: depth - draft is the clearance left.
        hit = np.isfinite(bathy) & ((bathy - float(vessel.draft_loaded_m)) < ukc_margin_m)
        reasons["under-keel clearance"] = int(hit.sum())
        mask |= hit
    else:
        logger.warning(
            "vessel %s has no draft_loaded_m; the UKC rule was not applied",
            vessel.id,
        )

    # bathy is depth, positive down, floored at zero on land (see
    # scripts/download_ibcso.py): a cell with no water column reads exactly
    # 0, so "> 0" is water and "<= 0" is land. Reading the sign the other way
    # round marks the whole ocean impassable.
    land = np.isfinite(bathy) & (bathy <= 0.0)
    reasons["land"] = int(land.sum())
    mask |= land

    cone = np.asarray(inputs.cone_blocked, dtype=bool)
    reasons["drift cone"] = int(cone.sum())
    mask |= cone

    logger.info(
        "hard blocks: %d/%d cells impassable (%s)",
        int(mask.sum()), mask.size,
        ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())),
    )
    return BlockReport(mask=mask, reasons=reasons)


def combine(
    inputs: RouteInputs,
    *,
    weights: dict[str, float],
    destination: tuple[float, float],
    blocks: BlockReport,
) -> np.ndarray:
    """Linear combination of the component grids, ``inf`` where blocked.

    Under-keel clearance is not a term here: it is a hard block already
    applied by :func:`build_blocks`, so adding it to the cost would make a
    ship pay a penalty for a cell it may not enter at all.
    """
    settings = get_settings()
    w_ice = weights.get("ice", settings.ROUTE_WEIGHT_ICE)
    w_thick = weights.get("thickness", settings.ROUTE_WEIGHT_THICKNESS)
    w_iceberg = weights.get("iceberg", settings.ROUTE_WEIGHT_ICEBERG)
    w_weather = weights.get("weather", settings.ROUTE_WEIGHT_WEATHER)
    w_fuel = weights.get("fuel", settings.ROUTE_WEIGHT_FUEL)
    w_current = weights.get("current", settings.ROUTE_WEIGHT_CURRENT)

    cost = (
        w_ice * ice_penalty(inputs.sic)
        + w_thick * thickness_penalty(inputs.thickness, inputs.vessel.max_ice_thickness_m)
        + w_iceberg * iceberg_penalty(inputs.distance_to_iceberg)
        + w_weather * weather_penalty(inputs.wind, None, inputs.vessel)
        + w_fuel * fuel_component(inputs.sic, inputs.vessel)
        - w_current * current_component(inputs.uo, inputs.vo, destination)
    )
    cost = np.where(np.isfinite(cost), cost, np.inf)
    cost = np.maximum(cost, 0.0)
    cost[blocks.mask] = np.inf
    return cost.astype(np.float32)


# ---------------------------------------------------------------------------
# A*
# ---------------------------------------------------------------------------
def _cell_latlon(index: tuple[int, int], lats: np.ndarray, lons: np.ndarray) -> tuple[float, float]:
    return float(lats[index[0]]), float(lons[index[1]])


def _step_distances(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Great-circle length of each of the 8 moves, indexed ``[dir, row]``.

    A step's length depends only on the row it starts from and the column
    offset, never on the column itself, so 8 x 101 evaluations replace the
    ~288,000 the search would otherwise perform.
    """
    rows = lats.size
    table = np.full((len(DIRECTIONS), rows), np.inf, dtype=np.float64)
    for d, (drow, dcol) in enumerate(DIRECTIONS):
        for row in range(rows):
            target = row + drow
            if 0 <= target < rows:
                table[d, row] = haversine_scalar_nm(
                    float(lats[row]), float(lons[0]),
                    float(lats[target]), float(lons[dcol] if dcol else lons[0]),
                )
    return table


def _nearest_passable(
    blocked: np.ndarray, origin: tuple[int, int], radius: int = NEAREST_PASSABLE_RADIUS
) -> tuple[int, int] | None:
    """Ring search outward from ``origin`` for a cell we may actually enter."""
    rows, cols = blocked.shape
    row0, col0 = origin
    if not blocked[row0, col0]:
        return origin
    for ring in range(1, radius + 1):
        best: tuple[int, int] | None = None
        best_distance = math.inf
        for row in range(row0 - ring, row0 + ring + 1):
            for col in range(col0 - ring, col0 + ring + 1):
                if not (0 <= row < rows and 0 <= col < cols):
                    continue
                if max(abs(row - row0), abs(col - col0)) != ring:
                    continue
                if blocked[row, col]:
                    continue
                distance = abs(row - row0) + abs(col - col0)
                if distance < best_distance:
                    best_distance = distance
                    best = (row, col)
        if best is not None:
            return best
    return None


def astar(
    cost: np.ndarray,
    blocked: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    lats: np.ndarray,
    lons: np.ndarray,
    max_expansions: int,
) -> list[tuple[int, int]] | None:
    """Least-cost path over ``cost``, or ``None`` when there is none.

    Edge weight is ``cost[destination_cell] * great_circle_distance``, so a
    route pays for the cell it enters rather than the one it leaves. The
    heuristic is ``min(cost) * great_circle_distance_to_goal``, a tight
    lower bound that stays admissible without knowing the path ahead.
    """
    rows, cols = cost.shape
    if blocked[start] or blocked[goal]:
        return None

    finite = cost[np.isfinite(cost)]
    min_cost = float(finite.min()) if finite.size else 0.0
    lower_bound = max(min_cost, 0.0)

    steps = _step_distances(lats, lons)

    def heuristic(cell: tuple[int, int]) -> float:
        return lower_bound * haversine_scalar_nm(
            float(lats[cell[0]]), float(lons[cell[1]]),
            float(lats[goal[0]]), float(lons[goal[1]]),
        )

    start_h = heuristic(start)
    frontier: list[tuple[float, float, int, tuple[int, int]]] = [
        (start_h, 0.0, 0, start)
    ]
    best_cost: dict[tuple[int, int], float] = {start: 0.0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    counter = 0
    expansions = 0

    while frontier:
        _, g, _, node = heapq.heappop(frontier)
        if g > best_cost.get(node, math.inf) + 1e-12:
            continue
        if node == goal:
            path = [node]
            while node in parent:
                node = parent[node]
                path.append(node)
            path.reverse()
            return path

        expansions += 1
        if expansions > max_expansions:
            logger.warning(
                "A* stopped after %d expansions without reaching the goal",
                max_expansions,
            )
            return None

        row, col = node
        for d, (drow, dcol) in enumerate(DIRECTIONS):
            nrow, ncol = row + drow, col + dcol
            if not (0 <= nrow < rows and 0 <= ncol < cols):
                continue
            if blocked[nrow, ncol]:
                continue
            step = steps[d, row]
            if not np.isfinite(step):
                continue
            g_next = g + float(cost[nrow, ncol]) * step
            neighbour = (nrow, ncol)
            if g_next >= best_cost.get(neighbour, math.inf) - 1e-12:
                continue
            best_cost[neighbour] = g_next
            parent[neighbour] = node
            counter += 1
            heapq.heappush(
                frontier, (g_next + heuristic(neighbour), g_next, counter, neighbour)
            )

    return None


# ---------------------------------------------------------------------------
# Path metrics
# ---------------------------------------------------------------------------
@dataclass
class RouteMetrics:
    distance_nm: float
    eta: datetime | None
    fuel_estimate_t: float | None
    risk_score: float
    notes: list[str] = field(default_factory=list)


def _segment_speed(sic_value: float, vessel: Vessel) -> float | None:
    """Knots for a segment, by the ice concentration it crosses."""
    econ = vessel.economical_speed_kt
    ice = vessel.speed_in_ice_kt
    if econ is None or not np.isfinite(econ) or econ <= 0:
        return None
    concentration = float(sic_value) if np.isfinite(sic_value) else 0.0
    if concentration < MIZ_THRESHOLD:
        return float(econ)
    if ice is None or not np.isfinite(ice) or ice <= 0:
        return None
    if concentration > FULL_ICE_SIC:
        return float(ice) * 0.5
    return float(ice)


def path_metrics(
    cells: list[tuple[int, int]],
    inputs: RouteInputs,
    departure: tuple[float, float],
    run_ts: datetime,
) -> tuple[np.ndarray, RouteMetrics]:
    """Coordinates, and the distance/ETA/fuel/risk of sailing them.

    The open-water approach from the real departure point to the ROI edge
    is carried as a separate leading segment: Cape Town is outside the
    modelled domain, and pretending the model covers it would be the same
    fabrication the rest of this module refuses.
    """
    lats = roi_lat_array()
    lons = roi_lon_array()
    vessel = inputs.vessel
    notes: list[str] = []

    cell_points = [_cell_latlon(cell, lats, lons) for cell in cells]
    coordinates = [departure] + cell_points

    # SIC along the path: the approach leg is outside the ROI and carries
    # no forecast, so it contributes no risk rather than a made-up one.
    concentrations = np.array([inputs.sic[r, c] for r, c in cells], dtype=np.float32)
    thicknesses = np.array([inputs.thickness[r, c] for r, c in cells], dtype=np.float32)
    iceberg_distances = np.array(
        [inputs.distance_to_iceberg[r, c] for r, c in cells], dtype=np.float32
    )
    ice_p = ice_penalty(concentrations)
    thick_p = thickness_penalty(thicknesses, vessel.max_ice_thickness_m)
    iceb_p = iceberg_penalty(iceberg_distances)
    risk_score = float(np.mean((ice_p + thick_p + iceb_p) / 3.0)) if cells else 0.0
    risk_score = float(np.clip(risk_score, 0.0, 1.0))

    # Distances: approach leg first, then cell-to-cell.
    leg_distances = [
        haversine_scalar_nm(coordinates[i][0], coordinates[i][1],
                            coordinates[i + 1][0], coordinates[i + 1][1])
        for i in range(len(coordinates) - 1)
    ]
    distance_nm = float(sum(leg_distances))

    # Time and fuel. The approach leg is open water by geography.
    speed_values = [vessel.economical_speed_kt] + [
        _segment_speed(concentrations[i], vessel) for i in range(len(cells))
    ]

    eta: datetime | None = run_ts
    fuel_t: float | None = 0.0
    burn = vessel.fuel_burn_economical_tpd
    if burn is None or not np.isfinite(burn) or burn <= 0:
        burn = None
        notes.append("vessel has no fuel_burn_economical_tpd; fuel not estimated")

    total_hours = 0.0
    computable = True
    for index, leg in enumerate(leg_distances):
        speed = speed_values[index]
        if speed is None or not np.isfinite(speed) or speed <= 0:
            computable = False
            notes.append("vessel speed profile incomplete; ETA not estimated")
            break
        if burn is None:
            continue
        hours = leg / float(speed)
        total_hours += hours
        fuel_t = (fuel_t or 0.0) + hours * (float(burn) / 24.0)

    if not computable:
        eta = None
        fuel_t = None
    else:
        eta = run_ts + timedelta(hours=total_hours)

    metrics = RouteMetrics(
        distance_nm=distance_nm,
        eta=eta,
        fuel_estimate_t=fuel_t,
        risk_score=risk_score,
        notes=notes,
    )
    return np.asarray(coordinates, dtype=np.float64), metrics


def shelf_reachability(
    last_point: tuple[float, float],
    inputs: RouteInputs,
    notes: list[str],
) -> str | None:
    """``None`` (all good), a note to append, or ``'infeasible'``.

    The ice-shelf edge is approximated as the nearest land cell — the same
    coastline the bathymetry encodes, and the only shelf geometry AURORA
    carries. With no crane reach specified the rule cannot be evaluated at
    all, so it is skipped rather than assumed to pass or fail.
    """
    vessel = inputs.vessel
    if vessel.crane_outreach_m is None or not np.isfinite(vessel.crane_outreach_m):
        notes.append("vessel has no crane_outreach_m; shelf reachability not evaluated")
        return None

    bathy = inputs.bathy
    land = np.isfinite(bathy) & (bathy <= 0.0)
    if not land.any():
        notes.append("bathymetry contains no land cells; shelf reachability not evaluated")
        return None

    lats = roi_lat_array()
    lons = roi_lon_array()
    rows, cols = np.nonzero(land)
    land_lat = lats[rows]
    land_lon = lons[cols]
    distance = haversine_nm(last_point[0], last_point[1], land_lat, land_lon)
    distance_to_shelf_nm = float(np.min(distance))

    reach_nm = float(vessel.crane_outreach_m) / NM_TO_M
    if distance_to_shelf_nm <= reach_nm:
        notes.append(
            f"shelf within crane reach: {distance_to_shelf_nm:.1f} nm <= {reach_nm:.1f} nm"
        )
        return None

    if vessel.has_helideck:
        notes.append(
            f"Terminate at standoff: helo resupply required "
            f"({distance_to_shelf_nm:.1f} nm from shelf, reach {reach_nm:.1f} nm)."
        )
        return None

    notes.append(
        f"Cannot reach shelf, no helideck "
        f"({distance_to_shelf_nm:.1f} nm from shelf, reach {reach_nm:.1f} nm)."
    )
    return "infeasible"


# ---------------------------------------------------------------------------
# Alternatives
# ---------------------------------------------------------------------------
def jaccard_cells(a: set[tuple[int, int]], b: set[tuple[int, int]]) -> float:
    """Overlap of two cell sets. Empty sets are identical by convention."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def combined_score(metrics: RouteMetrics, vessel: Vessel) -> float:
    """Risk plus fuel, the scalar the recommendation is chosen by."""
    fuel = metrics.fuel_estimate_t
    capacity = vessel.fuel_capacity_t
    fuel_fraction = 0.0
    if fuel is not None and capacity is not None and np.isfinite(capacity) and capacity > 0:
        fuel_fraction = float(fuel) / float(capacity)
    return float(metrics.risk_score) + fuel_fraction


def resolve_weights(spec: dict[str, float]) -> dict[str, float]:
    """Apply a variant's multipliers on top of the configured defaults."""
    settings = get_settings()
    weights = {
        "ice": settings.ROUTE_WEIGHT_ICE,
        "thickness": settings.ROUTE_WEIGHT_THICKNESS,
        "iceberg": settings.ROUTE_WEIGHT_ICEBERG,
        "weather": settings.ROUTE_WEIGHT_WEATHER,
        "fuel": settings.ROUTE_WEIGHT_FUEL,
        "current": settings.ROUTE_WEIGHT_CURRENT,
    }
    for key, multiplier in spec.items():
        weights[key] = weights.get(key, 1.0) * multiplier
    return weights


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _input_versions() -> dict[str, int]:
    rows = version_service.get_all()
    return {
        "sic": int(rows["sic"].version) if "sic" in rows else 0,
        "currents": int(rows["currents"].version) if "currents" in rows else 0,
        "weather": int(rows["weather"].version) if "weather" in rows else 0,
        "thickness": int(rows["ice_thickness"].version) if "ice_thickness" in rows else 0,
        "icebergs": int(rows["icebergs"].version) if "icebergs" in rows else 0,
    }


def _latest_vessel_state_id(vessel_id: int) -> int | None:
    from sqlalchemy import text

    with version_service.open_session() as session:
        row = session.execute(
            text("SELECT id FROM vessel_state WHERE vessel_id = :v ORDER BY ts DESC LIMIT 1"),
            {"v": int(vessel_id)},
        ).first()
    return int(row[0]) if row else None


def _persist(
    run: RouteRun,
    candidates: list[tuple[str, np.ndarray, RouteMetrics, bool]],
) -> RouteRun:
    """Write the run, its routes and their waypoints. Returns the run.

    One session, one transaction: a run without its routes is worse than no
    run at all, because the API would answer with a plan nobody can read.
    """
    with version_service.open_session() as session:
        run_id = _insert_run(session, run)
        written = _insert_routes(session, run_id, candidates)
        session.commit()

    run.id = int(run_id)
    logger.info(
        "route run %s persisted: status=%s routes=%d", run.id, run.status, written
    )
    return run


def _insert_run(session, run: RouteRun) -> int:
    from sqlalchemy import insert

    return int(session.execute(
        insert(RouteRun).values(
            vessel_id=run.vessel_id,
            run_ts=run.run_ts,
            input_version=run.input_version,
            vessel_state_id=run.vessel_state_id,
            status=run.status,
            notes=run.notes,
        ).returning(RouteRun.id)
    ).scalar_one())


def _insert_routes(session, run_id: int, candidates: list) -> int:
    from geoalchemy2.elements import WKTElement
    from sqlalchemy import insert

    count = 0
    for label, coordinates, metrics, recommended in candidates:
        if coordinates.shape[0] < 2:
            logger.warning("route %s has fewer than 2 points; not stored", label)
            continue
        wkt = "LINESTRING(" + ", ".join(
            f"{lon:.6f} {lat:.6f}" for lat, lon in coordinates
        ) + ")"
        route_id = int(session.execute(
            insert(Route).values(
                route_run_id=run_id,
                label=label,
                geom=WKTElement(wkt, srid=4326),
                distance_nm=float(metrics.distance_nm),
                eta=metrics.eta,
                fuel_estimate_t=metrics.fuel_estimate_t,
                risk_score=float(metrics.risk_score),
                is_recommended=bool(recommended),
            ).returning(Route.id)
        ).scalar_one())

        for seq, (lat, lon) in enumerate(coordinates):
            session.execute(insert(Waypoint).values(
                route_id=route_id,
                seq=seq,
                geom=WKTElement(f"POINT({lon:.6f} {lat:.6f})", srid=4326),
            ))
        count += 1
    return count


def publish_run(run: RouteRun) -> None:
    """Push the persisted run on ``route.updated``.

    The payload is re-read from the database by
    :func:`app.services.route_service.publish_run`, so the socket and the
    REST endpoint return the same object. An unpersisted run has nothing to
    read back and is deliberately not published.
    """
    if run.id is None:
        logger.warning("route run for vessel %s is not persisted; not published", run.vessel_id)
        return
    from app.services import route_service

    route_service.publish_run(int(run.id))


# ---------------------------------------------------------------------------
# The optimizer
# ---------------------------------------------------------------------------
def optimize(
    vessel_id: int,
    run_ts: datetime,
    *,
    dry_run: bool = False,
    persist: bool = True,
) -> RouteRun:
    """One planning pass for one vessel.

    Always returns a ``RouteRun``. A missing input, a blocked origin and an
    exhausted search all come back as ``status='infeasible'`` with a note
    that names the cause — never as a route that was guessed.
    """
    settings = get_settings()
    started = time.perf_counter()
    run_ts = run_ts if run_ts.tzinfo else run_ts.replace(tzinfo=timezone.utc)
    target = run_ts.date()
    ukc_margin = settings.ROUTE_UKC_MARGIN_M

    departure = (settings.DEFAULT_DEPARTURE_LAT, settings.DEFAULT_DEPARTURE_LON)
    destinations = settings.default_destinations
    logger.info(
        "route optimization starting for vessel %s at %s (dry_run=%s)",
        vessel_id, run_ts.isoformat(), dry_run,
    )

    loaded = load_inputs(vessel_id, target)
    if not isinstance(loaded, RouteInputs):
        note = "Missing inputs; no route computed: " + "; ".join(loaded)
        for problem in loaded:
            logger.warning("route input unavailable: %s", problem)
        return _finish(vessel_id, run_ts, None, "infeasible", note, [], dry_run, persist)

    inputs = loaded
    vessel = inputs.vessel
    lats = roi_lat_array()
    lons = roi_lon_array()

    blocks = build_blocks(inputs, ukc_margin_m=ukc_margin)

    origin_cell = cell_index(departure[0], departure[1])
    origin_cell = _nearest_passable(blocks.mask, origin_cell)
    if origin_cell is None:
        return _finish(
            vessel_id, run_ts, None, "infeasible",
            "Origin is inside an impassable region; no route can start.",
            [], dry_run, persist,
        )

    # Choose the destination first, with default weights, then build the
    # alternatives only for the one that won — three extra A* runs per
    # destination would triple the work for an answer nobody keeps.
    destination: tuple[float, float] | None = None
    goal_cell: tuple[int, int] | None = None
    base_path: list[tuple[int, int]] | None = None
    chosen_score = math.inf
    destination_notes: list[str] = []

    for candidate_dest in destinations:
        wanted = cell_index(candidate_dest[0], candidate_dest[1])
        adjusted = _nearest_passable(blocks.mask, wanted)
        if adjusted is None:
            destination_notes.append(
                f"destination {candidate_dest[0]:.3f},{candidate_dest[1]:.3f} "
                "has no passable cell within search radius"
            )
            continue
        if adjusted != wanted:
            delta = haversine_scalar_nm(
                candidate_dest[0], candidate_dest[1],
                float(lats[adjusted[0]]), float(lons[adjusted[1]]),
            )
            destination_notes.append(
                f"destination cell impassable; routed to nearest passable cell "
                f"{delta:.1f} nm away"
            )

        cost = combine(
            inputs, weights=resolve_weights({}), destination=candidate_dest,
            blocks=blocks,
        )
        path = astar(
            cost, blocks.mask, origin_cell, adjusted, lats, lons,
            settings.ROUTE_MAX_EXPANSIONS,
        )
        if path is None:
            destination_notes.append(
                f"no path to {candidate_dest[0]:.3f},{candidate_dest[1]:.3f}"
            )
            continue

        _, metrics = path_metrics(path, inputs, departure, run_ts)
        score = combined_score(metrics, vessel)
        logger.info(
            "destination %s: %d cells, %.0f nm, risk %.3f, score %.3f",
            candidate_dest, len(path), metrics.distance_nm, metrics.risk_score, score,
        )
        if score < chosen_score:
            chosen_score = score
            destination, goal_cell, base_path = candidate_dest, adjusted, path

    if base_path is None or destination is None or goal_cell is None:
        note = "No traversable path exists given current constraints."
        if destination_notes:
            note += " " + "; ".join(destination_notes)
        return _finish(vessel_id, run_ts, None, "infeasible", note, [], dry_run, persist)

    # --- candidates -------------------------------------------------------
    # Each candidate carries its coordinates from the moment it is built,
    # so a variant is scored and stored from the same numbers.
    candidates: list[tuple[str, np.ndarray, RouteMetrics]] = []
    kept_cells: list[set[tuple[int, int]]] = []

    for label, spec in VARIANT_SPECS.items():
        if label == "balanced":
            path = base_path
        else:
            cost = combine(
                inputs, weights=resolve_weights(spec), destination=destination,
                blocks=blocks,
            )
            path = astar(
                cost, blocks.mask, origin_cell, goal_cell,
                lats, lons, settings.ROUTE_MAX_EXPANSIONS,
            )
            if path is None:
                logger.info("variant %s produced no path; omitted", label)
                continue

        cells = set(path)
        overlap = max((jaccard_cells(cells, kept) for kept in kept_cells), default=0.0)
        if kept_cells and overlap >= settings.ROUTE_ALT_MAX_OVERLAP:
            logger.info(
                "variant %s dropped: %.2f overlap with an already-kept route "
                "(limit %.2f)", label, overlap, settings.ROUTE_ALT_MAX_OVERLAP,
            )
            continue

        coordinates, metrics = path_metrics(path, inputs, departure, run_ts)
        kept_cells.append(cells)
        candidates.append((label, coordinates, metrics))

    if not candidates:
        note = "No traversable path exists given current constraints."
        return _finish(vessel_id, run_ts, None, "infeasible", note, [], dry_run, persist)

    # --- pick the recommendation ------------------------------------------
    scores = [combined_score(metrics, vessel) for _, _, metrics in candidates]
    primary_index = int(np.argmin(scores))
    overall_notes = list(destination_notes)
    for _, _, metrics in candidates:
        for note in metrics.notes:
            if note not in overall_notes:
                overall_notes.append(note)

    shelf_notes: list[str] = []
    best_coords, best_metrics = candidates[primary_index][1], candidates[primary_index][2]
    shelf_status = shelf_reachability(
        (float(best_coords[-1][0]), float(best_coords[-1][1])), inputs, shelf_notes
    )
    overall_notes.extend(shelf_notes)

    status = "infeasible" if shelf_status == "infeasible" else (
        "degraded" if any("not evaluated" in n or "not estimated" in n for n in overall_notes)
        else "optimal"
    )

    final_candidates: list[tuple[str, np.ndarray, RouteMetrics, bool]] = []
    for index, (label, coordinates, metrics) in enumerate(candidates):
        recommended = index == primary_index
        display_label = "primary" if recommended else (
            "alt-balanced" if label == "balanced" else label
        )
        final_candidates.append((display_label, coordinates, metrics, recommended))

    note = "; ".join(overall_notes) if overall_notes else None
    if status == "infeasible" and not note:
        note = "No traversable path exists given current constraints."

    logger.info(
        "route optimization finished for vessel %s in %.2fs: status=%s",
        vessel_id, time.perf_counter() - started, status,
    )
    return _finish(
        vessel_id, run_ts, _latest_vessel_state_id(vessel_id),
        status, note, final_candidates, dry_run, persist,
    )


def _finish(
    vessel_id: int,
    run_ts: datetime,
    vessel_state_id: int | None,
    status: str,
    notes: str | None,
    candidates: list[tuple[str, np.ndarray, RouteMetrics, bool]],
    dry_run: bool,
    persist: bool,
) -> RouteRun:
    run = RouteRun(
        vessel_id=vessel_id,
        run_ts=run_ts,
        input_version=_input_versions(),
        vessel_state_id=vessel_state_id,
        status=status,
        notes=notes,
    )

    if status == "infeasible" or not candidates:
        logger.warning("route run for vessel %s: %s — %s", vessel_id, status, notes)
        if persist and not dry_run:
            run = _persist_plain(run)
        if not dry_run:
            publish_run(run)
        return run

    if persist and not dry_run:
        run = _persist(run, candidates)
    else:
        logger.info("dry run: %d candidate route(s) not written", len(candidates))

    if not dry_run:
        publish_run(run)
    return run


def _persist_plain(run: RouteRun) -> RouteRun:
    """Persist a run that has no routes to go with it."""
    with version_service.open_session() as session:
        run.id = _insert_run(session, run)
        session.commit()
    return run


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="python -m app.services.route_optimizer",
        description="Run one AURORA route optimization pass.",
    )
    parser.add_argument("--vessel-id", type=int, required=True)
    parser.add_argument("--date", type=lambda s: date.fromisoformat(s), default=None,
                        help="target date, YYYY-MM-DD (default: today, UTC)")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and score the routes without writing anything")
    parser.add_argument("--no-publish", action="store_true",
                        help="do not publish to the route.updated channel")
    args = parser.parse_args(argv)

    run_ts = datetime.combine(
        args.date or datetime.now(timezone.utc).date(),
        datetime.min.time(), tzinfo=timezone.utc,
    )
    run = optimize(args.vessel_id, run_ts, dry_run=args.dry_run, persist=not args.dry_run)

    summary = {
        "id": getattr(run, "id", None),
        "vessel_id": run.vessel_id,
        "run_ts": run.run_ts.isoformat() if run.run_ts else None,
        "status": run.status,
        "notes": run.notes,
        "input_version": run.input_version,
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if run.status != "error" else 1


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    raise SystemExit(main())
