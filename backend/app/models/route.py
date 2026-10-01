"""Planned routes and the optimizer runs that produced them.

Written by the route optimizer in PART 2; the schema lands now so the
display pipeline and the frontend have something stable to read against.
"""

from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, REAL, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LINESTRING_4326 = Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=False)


class RouteRun(Base):
    """One optimizer invocation, with the exact inputs it saw."""

    __tablename__ = "route_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vessel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    run_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # The full input window (source versions + staleness) that produced the
    # run, so a route can always be explained after the fact.
    input_version: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    vessel_state_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # 'optimal' | 'infeasible' | 'degraded'
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Route(Base):
    __tablename__ = "route"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    route_run_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    geom = mapped_column(LINESTRING_4326, nullable=True)

    distance_nm: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    eta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fuel_estimate_t: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    is_recommended: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
