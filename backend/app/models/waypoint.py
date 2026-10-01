"""Waypoints along a planned route."""

from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

POINT_4326 = Geometry(geometry_type="POINT", srid=4326, spatial_index=False)


class Waypoint(Base):
    __tablename__ = "waypoint"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    route_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    seq: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    geom = mapped_column(POINT_4326, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
