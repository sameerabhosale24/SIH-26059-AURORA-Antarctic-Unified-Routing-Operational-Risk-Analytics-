"""Own-ship telemetry and the AIS target list.

Two endpoints, one rule: they answer about *this operator's* ship. The
vessel is resolved through :mod:`app.api.scope`, and an operator who owns
no vessels gets 204 rather than somebody else's position — the fallback
for "no ship selected" is "no data", never "the newest row in the table".

AIS is deliberately not scoped. Contacts are what every ship in the region
can see; filtering them by owner would delete traffic from the display.
What *is* scoped is the own-ship fix used to compute CPA, so the risk bands
in this response are measured from the caller's own position.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.scope import resolve_vessel_id
from app.models import User
from app.schemas.telemetry import AisTargetOut, VesselStateOut
from app.services import ais_service, vessel_service

router = APIRouter(prefix="/api", tags=["telemetry"])


def _no_content() -> Response:
    """A fresh 204 — responses are per-request, never shared instances."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _own_state(vessel_id: int | None):
    """The caller's own ``vessel_state`` row, or ``None``.

    ``None`` *by ownership* is passed straight through: a caller with no
    vessel must not fall back to an unfiltered ``latest_state()``, which
    would return whichever ship reported last across all operators.
    """
    if vessel_id is None:
        return None
    return await asyncio.to_thread(vessel_service.latest_state, vessel_id)


@router.get("/vessel/latest", response_model=VesselStateOut, tags=["telemetry"])
async def vessel_latest(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VesselStateOut | Response:
    """Newest own-ship fix, or 204 when this operator has no ship.

    204 rather than an empty object: "no telemetry yet" and "no ship at
    all" are the same answer to the console, and both are an absence.
    """
    vessel_id = await resolve_vessel_id(None, user, db)
    row = await _own_state(vessel_id)
    if row is None:
        return _no_content()
    return vessel_service.serialize_state(row)


@router.get("/ais/latest", response_model=list[AisTargetOut], tags=["telemetry"])
async def ais_latest(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Every fresh contact, CPA-enriched against the caller's own ship.

    ``[]`` is the honest empty answer — the feed is healthy and there is
    simply nothing in range — so it needs no status code of its own.
    """
    vessel_id = await resolve_vessel_id(None, user, db)
    own = await _own_state(vessel_id)
    rows = await asyncio.to_thread(ais_service.recent_targets)
    return ais_service.build_targets(rows, own)
