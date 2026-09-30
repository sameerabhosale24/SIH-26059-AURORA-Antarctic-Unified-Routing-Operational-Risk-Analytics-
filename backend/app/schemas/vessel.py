"""
Vessel request/response models.

Every field except the vessel's name is optional on input: the reference
`POST /api/vessels` payload carries only the fields it cares about, and the
form sends all 27. Both must be accepted by the same endpoint, so the schema
does not invent requirements the database does not have — `name` is the one
column `NOT NULL`.

Empty columns are `null`, never absent, because the frontend renders
`undefined` as a missing key.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VesselBase(BaseModel):
    # identity
    name: str
    imo: str | None = None
    mmsi: str | None = None
    call_sign: str | None = None
    flag: str | None = None
    vessel_type: str | None = None
    operator: str | None = None

    # ice regime
    max_ice_thickness_m: float | None = None
    max_sic: float | None = None
    iacs_polar_class: str | None = None
    polar_code_category: str | None = None

    # under-keel clearance
    draft_loaded_m: float | None = None
    draft_ballast_m: float | None = None

    # weather tolerance
    max_wind_speed_kt: float | None = None
    max_wave_height_m: float | None = None

    # speed
    economical_speed_kt: float | None = None
    max_speed_kt: float | None = None
    speed_in_ice_kt: float | None = None

    # fuel & range
    fuel_capacity_t: float | None = None
    fuel_burn_economical_tpd: float | None = None
    endurance_days: float | None = None

    # station reachability
    crane_outreach_m: float | None = None
    has_helideck: bool = False
    has_hangar: bool = False
    has_rov: bool = False

    # ice maneuverability
    shaft_power_kw: float | None = None
    bow_shape: str | None = None


class VesselCreate(VesselBase):
    pass


class VesselUpdate(VesselBase):
    name: str | None = None


class VesselResponse(VesselBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
