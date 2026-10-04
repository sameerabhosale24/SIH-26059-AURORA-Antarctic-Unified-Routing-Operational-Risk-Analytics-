"""Route runs: what the optimiser produced, and which one is recommended.

The three endpoints are scoped to a single vessel, resolved through
:mod:`app.api.scope`. That matters most for ``accept``: the route and run
ids arrive in the request body, so without an ownership check an operator
could accept a route into somebody else's voyage simply by guessing an
integer. The run's owning vessel is therefore read back before anything is
written, and a wrong id is a 404.

An empty answer is always an absence rather than a placeholder: no run yet
means 204 for ``current`` and ``[]`` for ``history``.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.scope import resolve_vessel_id
from app.models import User
from app.schemas.route import AcceptRouteRequest, RouteRunOut
from app.services import route_service

router = APIRouter(prefix="/api/route", tags=["route"])

not_found = "Route not found"


async def _call(func, *args, **kwargs):
    """Run the synchronous route service off the event loop."""
    return await asyncio.to_thread(lambda: func(*args, **kwargs))


@router.get("/current", response_model=RouteRunOut, tags=["route"])
async def route_current(
    vessel_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RouteRunOut | Response:
    """The newest run for this operator's ship, or 204 when there is none.

    Without ``vessel_id`` the own-ship vessel is used, which is what the
    console means by "the current route"; an operator with no vessels has
    no current route and is told so with 204 rather than with a run
    belonging to someone else.
    """
    scoped = await resolve_vessel_id(vessel_id, user, db)
    if scoped is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    run = await _call(route_service.latest_run, scoped)
    if run is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return run


@router.get("/history", response_model=list[RouteRunOut], tags=["route"])
async def route_history(
    limit: int = 10,
    vessel_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Newest-first runs for this operator's ship.

    Scoped by the same rule as ``current``: without an explicit id the
    history is the own-ship history, because the console's history panel
    sits next to the current route and is about the same voyage.
    """
    scoped = await resolve_vessel_id(vessel_id, user, db)
    if scoped is None:
        return []
    return await _call(route_service.run_history, limit, scoped)


@router.post("/accept", response_model=RouteRunOut, tags=["route"])
async def route_accept(
    payload: AcceptRouteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RouteRunOut:
    """Make one candidate of ``route_run_id`` the recommended route.

    Ownership is checked against the run before anything is written: the
    two ids are caller-supplied, and "not yours" and "does not exist" are
    deliberately the same 404 so the endpoint cannot be used to probe for
    other operators' voyages.
    """
    run_vessel = await _call(route_service.run_vessel_id, payload.route_run_id)
    if run_vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)

    scoped = await resolve_vessel_id(run_vessel, user, db)
    if scoped != run_vessel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)

    accepted = await _call(
        route_service.accept_route,
        payload.route_run_id,
        payload.route_id,
        payload.accepted_by,
    )
    if accepted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)

    # The recommendation changed, so every open console must hear about it;
    # the publish is a re-read of the stored run, not the dict built here.
    await asyncio.to_thread(route_service.publish_run, payload.route_run_id)
    return accepted
