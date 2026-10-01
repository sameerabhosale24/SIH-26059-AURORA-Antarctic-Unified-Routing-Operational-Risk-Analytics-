"""Operator-facing alarms.

Alarms are the only place AURORA is allowed to say something is wrong with
its own data. ``forecast_stale`` in particular is raised when a source falls
outside the staleness threshold and the daily cycle refuses to publish.
"""

from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

POINT_4326 = Geometry(geometry_type="POINT", srid=4326, spatial_index=False)

SEVERITIES = ("critical", "warning", "caution")
TYPES = ("ukc", "collision", "ice", "iceberg", "off_course", "forecast_stale")


class Alarm(Base):
    __tablename__ = "alarm"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    vessel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    # 'critical' | 'warning' | 'caution'
    severity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 'ukc' | 'collision' | 'ice' | 'iceberg' | 'off_course' | 'forecast_stale'
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    geom = mapped_column(POINT_4326, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
