"""``GET /api/weather/vessel`` — wind, air temperature and current at the ship.

Scoped through :mod:`app.api.scope` for the same reason the route endpoints
are: without an explicit id this answers about the operator's own ship, and
an operator with no ship gets 204 rather than a sample taken from
whichever vessel happened to report last anywhere in the deployment.

204 is also the answer when there is nothing to sample. AURORA has no wave
source and, on a deployment that has not fetched ERA5 or CMEMS yet, no
wind or current either — a point made entirely of ``null`` measurements
tells the operator nothing an em dash would not, so the absence is stated
once, as a status, instead of being dressed up as a reading.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.scope import resolve_vessel_id
from app.models import User
from app.schemas.weather import WeatherPointOut
from app.services import weather_poller

router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather/vessel", response_model=WeatherPointOut, tags=["weather"])
async def weather_at_vessel(
    vessel_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WeatherPointOut | Response:
    """The sample at this ship's newest fix, or 204 when there is none."""
    scoped = await resolve_vessel_id(vessel_id, user, db)
    if scoped is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    payload = await asyncio.to_thread(weather_poller.sample_at_vessel, scoped)
    if payload is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return payload
