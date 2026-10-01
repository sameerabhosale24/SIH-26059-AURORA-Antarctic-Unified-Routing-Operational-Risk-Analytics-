"""Automatic Identification System sightings for target ships.

Hypertable on ``ts``. There is no surrogate key: an AIS report is identified
by ``(mmsi, ts)`` at the application level, and TimescaleDB needs no more
than the time column to partition.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Double, REAL, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AisTrack(Base):
    __tablename__ = "ais_track"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    mmsi: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    lat: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Double, nullable=True)

    sog: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    cog: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)
    heading: Mapped[Optional[float]] = mapped_column(REAL, nullable=True)

    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ship_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    destination: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
