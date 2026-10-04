"""Alarm listing and acknowledgement.

Scoping is two-tier, and the tiers come straight from what an alarm is
attached to. A data-quality alarm (``forecast_stale``) carries no vessel
because it is about the data, so it is visible to every operator. An
operational alarm belongs to one ship and is visible only to that ship's
operator — and a caller with no vessels sees neither it nor its id, because
"no such alarm" and "not yours" must answer identically or the endpoint
becomes a probe for other operators' voyages.

``GET /api/alarms`` returns the same serialised shape the WebSocket pushes,
so a console that loads the page and a console that has been open for an
hour end up holding identical objects.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.scope import resolve_vessel_id
from app.models import User
from app.schemas.alarm import AckRequest, AlarmOut
from app.services import alarm_service

router = APIRouter(prefix="/api", tags=["alarms"])

not_found = "Alarm not found"


@router.get("/alarms", response_model=list[AlarmOut], tags=["alarms"])
async def list_alarms(
    since: datetime | None = None,
    vessel_id: int | None = None,
    unacked: bool = False,
    limit: int = Query(default=alarm_service.DEFAULT_LIMIT, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Alarms newest first.

    ``since`` is an ISO timestamp; ``vessel_id`` scopes to one ship, and is
    resolved through the shared ownership rules before it is used.
    """
    scoped = await resolve_vessel_id(vessel_id, user, db)
    return await asyncio.to_thread(
        alarm_service.list_alarms,
        since=since,
        vessel_id=scoped,
        unacked_only=unacked,
        limit=limit,
    )


@router.post("/alarms/{alarm_id}/ack", response_model=AlarmOut, tags=["alarms"])
async def ack_alarm(
    alarm_id: int,
    payload: AckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Acknowledge one alarm and return its new state.

    Re-acking an already-acknowledged alarm returns it unchanged rather
    than moving the timestamp: when the operator first saw it is the more
    useful number, and a double-click must not rewrite history.

    The updated alarm is pushed back out on the alarms channel so every
    open console sees the acknowledgement, not only the one that made it.
    """
    scoped = await resolve_vessel_id(None, user, db)
    if not await asyncio.to_thread(alarm_service.alarm_is_visible, alarm_id, scoped):
        # Unknown and not-yours are the same answer; see the module docstring.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)

    updated = await asyncio.to_thread(alarm_service.ack_alarm, alarm_id, payload.acked_by)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)

    await asyncio.to_thread(alarm_service.publish_alarm, updated)
    return updated
