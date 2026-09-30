"""
Fleet CRUD, scoped to the signed-in operator.

Every query filters on `user_id`, so one operator's vessel is invisible to
another: a wrong id and someone else's id are both a 404.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, Vessel
from app.schemas.vessel import VesselCreate, VesselResponse, VesselUpdate

router = APIRouter(prefix="/api/vessels", tags=["vessels"])

_not_found = "Vessel not found"


async def _commit(db: AsyncSession, payload: VesselCreate | VesselUpdate) -> None:
    """
    Flush and commit, translating the one constraint that is not a bug.

    `imo` is unique across the whole fleet — an IMO number identifies a hull,
    not an owner — so a repeat is a real business conflict, not a 500.
    """
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if payload.imo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A vessel with IMO {payload.imo} already exists",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vessel with these details already exists",
        ) from None


async def _owned_vessel(vessel_id: int, user: User, db: AsyncSession) -> Vessel:
    vessel = await db.get(Vessel, vessel_id)
    if vessel is None or vessel.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_not_found)
    return vessel


@router.get("", response_model=list[VesselResponse])
async def list_vessels(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VesselResponse]:
    rows = await db.scalars(
        select(Vessel).where(Vessel.user_id == user.id).order_by(Vessel.id)
    )
    return [VesselResponse.model_validate(row) for row in rows]


@router.post("", response_model=VesselResponse, status_code=status.HTTP_201_CREATED)
async def create_vessel(
    payload: VesselCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VesselResponse:
    vessel = Vessel(**payload.model_dump(), user_id=user.id)
    db.add(vessel)
    await _commit(db, payload)
    await db.refresh(vessel)
    return VesselResponse.model_validate(vessel)


@router.get("/{vessel_id}", response_model=VesselResponse)
async def get_vessel(
    vessel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VesselResponse:
    return VesselResponse.model_validate(await _owned_vessel(vessel_id, user, db))


@router.patch("/{vessel_id}", response_model=VesselResponse)
async def update_vessel(
    vessel_id: int,
    payload: VesselUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VesselResponse:
    vessel = await _owned_vessel(vessel_id, user, db)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(vessel, key, value)

    await _commit(db, payload)
    await db.refresh(vessel)
    return VesselResponse.model_validate(vessel)


@router.delete("/{vessel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vessel(
    vessel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    vessel = await _owned_vessel(vessel_id, user, db)
    await db.delete(vessel)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
