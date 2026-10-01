"""Iceberg observations and probabilistic drift forecasts.

``iceberg_position`` is a hypertable on ``ts`` with a PostGIS point for the
native (non-regridded) location. ``iceberg_drift_cone`` is a normal table:
a cone is a small, bounded set of polygons per run, not a time series.
"""

from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, REAL, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

POINT_4326 = Geometry(geometry_type="POINT", srid=4326, spatial_index=False)
POLYGON_4326 = Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False)


class IcebergPosition(Base):
    __tablename__ = "iceberg_position"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    iceberg_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)

    geom = mapped_column(POINT_4326, nullable=True)

    length_km: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    drift_bearing: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    drift_speed_kt: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IcebergDriftCone(Base):
    __tablename__ = "iceberg_drift_cone"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    iceberg_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    run_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    horizon_h: Mapped[Optional[int]] = mapped_column(nullable=True)

    geom = mapped_column(POLYGON_4326, nullable=True)
    probability: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
