"""``GET /api/icebergs/current`` — the newest sighting per iceberg.

Reference data in the sense the map cares about: icebergs are where they
are regardless of who is asking, so this endpoint is open and unscoped,
exactly like the coastline it is drawn next to.

The drift cone travels with the sighting it belongs to. A cone that has
not been computed comes back ``null`` rather than as an empty polygon —
an empty polygon would draw as "this iceberg is not going to move", which
is the opposite of "no forecast exists".
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.iceberg import IcebergOut
from app.services import iceberg_proximity

router = APIRouter(prefix="/api", tags=["icebergs"])


@router.get("/icebergs/current", response_model=list[IcebergOut], tags=["icebergs"])
def icebergs_current() -> list[dict]:
    """Every tracked iceberg's latest position, with its newest cone.

    Read as a synchronous endpoint so FastAPI runs it in the threadpool:
    both queries go through the same synchronous session the scheduler
    uses, and blocking a worker thread is exactly what it is there for.
    """
    positions = iceberg_proximity.latest_positions()
    if not positions:
        return []

    cones = iceberg_proximity.latest_cones()
    return [
        {
            "id": berg.iceberg_id,
            # ``ts`` is part of the primary key, so a sighting without one
            # cannot exist; the empty string is only for a corrupt row.
            "ts": iceberg_proximity.iso_ts(berg.ts),
            "lat": berg.lat,
            "lon": berg.lon,
            "length_km": berg.length_km,
            "drift_bearing": berg.drift_bearing,
            "drift_speed_kt": berg.drift_speed_kt,
            "source": berg.source or "",
            "drift_cone": cones.get(berg.iceberg_id, (None, None))[0],
            "drift_cone_probability": cones.get(berg.iceberg_id, (None, None))[1],
        }
        for berg in positions
    ]
