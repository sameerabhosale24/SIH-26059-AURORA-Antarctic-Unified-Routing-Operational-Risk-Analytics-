"""Route runs, candidate routes and the accept request.

``RouteRun`` is the one payload the console cannot fake its way through:
it carries the input data versions the run was computed against, so an
operator can tell a route planned against current ice from one planned
against a week-old field. Those versions are therefore never defaulted —
an absent key means "not used by this run".
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WaypointOut(BaseModel):
    id: int
    seq: int = 0
    lat: float | None = None
    lon: float | None = None
    name: str | None = None
    eta: str | None = None


class RouteOut(BaseModel):
    """One candidate route.

    ``geometry`` is a WGS84 GeoJSON LineString. The numeric fields are
    nullable because an infeasible run stores what it knows and no more —
    the console shows an em dash rather than a fabricated zero.
    """

    id: int
    route_run_id: int
    label: str = "route"
    geometry: dict | None = None
    distance_nm: float | None = None
    eta: str | None = None
    fuel_estimate_t: float | None = None
    risk_score: float | None = None
    is_recommended: bool = False
    waypoints: list[WaypointOut] = Field(default_factory=list)


class RouteRunOut(BaseModel):
    id: int
    vessel_id: str = "0"
    run_ts: str | None = None
    input_version: dict[str, int] = Field(default_factory=dict)
    status: str = "optimal"
    notes: str | None = None
    routes: list[RouteOut] = Field(default_factory=list)


class AcceptRouteRequest(BaseModel):
    """``POST /api/route/accept`` — make one candidate the recommended one."""

    route_id: int
    route_run_id: int
    accepted_by: str | None = None
