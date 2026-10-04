"""Vessel scope for the vessel-scoped endpoints.

Every operational endpoint in PART 2 answers about *a* ship. Which one is a
question with three answers, resolved here once so no route invents its own:

1. ``?vessel_id=N`` — that ship, but only if the signed-in operator owns it.
   A wrong id and someone else's id are both a 404, exactly as the fleet
   CRUD behaves, so probing for other operators' vessels learns nothing.
2. No parameter, and the operator owns the own-ship vessel — the own ship.
   This is the console case: the relay feeds one hull and the panels are
   about that hull.
3. No parameter, and the operator does not own it — their newest vessel.

``None`` (no data, 204) is what an operator with no vessels at all gets.
It is never replaced by a fabricated default, because "which ship am I
looking at" is not a detail to guess.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, Vessel

not_found = "Vessel not found"


async def _owned(vessel_id: int, user: User, db: AsyncSession) -> Vessel:
    vessel = await db.get(Vessel, vessel_id)
    if vessel is None or vessel.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)
    return vessel


async def resolve_vessel_id(
    requested: int | None, user: User, db: AsyncSession
) -> int | None:
    """The vessel this request is about, or ``None`` when there is no such ship."""
    if requested is not None:
        return (await _owned(requested, user, db)).id

    own_ship = get_settings().OWN_SHIP_VESSEL_ID
    if await db.get(Vessel, own_ship) is not None:
        # Ownership still matters: an operator must not inherit another's
        # telemetry just because a deployment-wide default names it.
        owned = await db.scalar(
            select(Vessel.id).where(Vessel.id == own_ship, Vessel.user_id == user.id)
        )
        if owned is not None:
            return int(owned)

    newest = await db.scalar(
        select(Vessel.id)
        .where(Vessel.user_id == user.id)
        .order_by(Vessel.id.desc())
        .limit(1)
    )
    return int(newest) if newest is not None else None


async def assert_owned(vessel_id: int, user: User, db: AsyncSession) -> int:
    """Ownership check for paths where the id is part of the URL."""
    return (await _owned(vessel_id, user, db)).id
