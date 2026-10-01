"""Version and staleness bookkeeping for every ingested source.

One row per source. ``version`` starts at 0 and is bumped only after a
successful ingest — it never moves for a failed run, so the frontend can
treat an unchanged version as "nothing new" without diffing payloads.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The seven tracked sources. Keep in sync with adapters.SOURCE_KEYS.
VERSION_KEYS = (
    "sic",
    "currents",
    "weather",
    "icebergs",
    "enc",
    "ice_thickness",
    "bathymetry",
)


class DataVersion(Base):
    __tablename__ = "data_version"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Time of the newest observation folded into this version; None until the
    # first successful fetch, so health can report "never fetched" honestly.
    source_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    staleness: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
