"""``GET /api/version`` — the revision counter of every data product.

A version number is how the console decides that something it is already
showing has changed. It is therefore only reported when there is one: a key
that has never been fetched stays out of the payload, so the client sees
``undefined`` ("never") instead of ``0``, which it would read as "revision
zero is current" and never refetch.

The staleness detail lives in ``GET /api/health``, not here — this endpoint
is polled every ten minutes and answers the narrow question "has anything
I am already displaying moved?".
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services import version_service

router = APIRouter(prefix="/api", tags=["version"])


@router.get("/version")
def version() -> dict[str, int]:
    """``{key: revision}`` for each product that has been fetched at least once."""
    rows = version_service.get_all()
    return {
        key: int(row.version)
        for key, row in rows.items()
        if row.version is not None and int(row.version) > 0
    }
