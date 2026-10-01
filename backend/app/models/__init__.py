"""ORM models.

Importing this package registers every table on ``Base.metadata``, which is
what ``alembic/env.py`` reads. Import order does not matter — no model
references another at class definition time.
"""

from app.models.alarm import Alarm
from app.models.ais_track import AisTrack
from app.models.data_version import DataVersion, VERSION_KEYS
from app.models.iceberg import IcebergDriftCone, IcebergPosition
from app.models.route import Route, RouteRun
from app.models.user import User
from app.models.vessel import Vessel
from app.models.vessel_state import VesselState
from app.models.waypoint import Waypoint

__all__ = [
    "AisTrack",
    "Alarm",
    "DataVersion",
    "IcebergDriftCone",
    "IcebergPosition",
    "Route",
    "RouteRun",
    "User",
    "VERSION_KEYS",
    "Vessel",
    "VesselState",
    "Waypoint",
]
