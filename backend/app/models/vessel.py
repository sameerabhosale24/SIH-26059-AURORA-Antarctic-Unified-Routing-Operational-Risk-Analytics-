"""
The 27-field vessel blueprint.

Column names are identical to the frontend's `types/ship.ts` so the API is a
pass-through: a rename has exactly one place to land. `user_id` scopes every
row to its owner — there is no shared fleet.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Vessel(Base):
    __tablename__ = "vessel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    imo: Mapped[Optional[str]] = mapped_column(String(16), unique=True, nullable=True)
    mmsi: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    call_sign: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    flag: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    vessel_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    operator: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # ice regime
    max_ice_thickness_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_sic: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iacs_polar_class: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    polar_code_category: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    # under-keel clearance
    draft_loaded_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    draft_ballast_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # weather tolerance
    max_wind_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_wave_height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # speed
    economical_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_in_ice_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # fuel & range
    fuel_capacity_t: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fuel_burn_economical_tpd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    endurance_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # station reachability
    crane_outreach_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    has_helideck: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    has_hangar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    has_rov: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # ice maneuverability
    shaft_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bow_shape: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
