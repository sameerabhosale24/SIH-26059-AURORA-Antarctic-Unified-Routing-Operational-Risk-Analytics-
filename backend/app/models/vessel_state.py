"""Telemetry for the operator's own ship.

A TimescaleDB hypertable partitioned on ``ts``. Because the partition column
must be part of the primary key, the key is composite ``(id, ts)`` — a plain
``id`` primary key is rejected by TimescaleDB.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Double, REAL, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VesselState(Base):
    __tablename__ = "vessel_state"

    # Composite primary key with `ts`: TimescaleDB refuses a hypertable whose
    # unique index does not contain the partitioning column. `autoincrement`
    # must be stated explicitly because SQLAlchemy only infers it for
    # single-column primary keys.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False, index=True
    )

    vessel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    lat: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Double, nullable=True)

    sog: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    cog: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    heading: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    rot: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)

    draft: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    ukc: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)

    fuel_remaining: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    engine_load: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    wind_speed: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    wind_dir: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)

    # 'gps' | 'manual' | 'estimated'
    source: Mapped[str] = mapped_column(Text, nullable=False)
