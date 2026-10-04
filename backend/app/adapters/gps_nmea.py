"""Ship GPS (NMEA over TCP/UDP) — not a per-day fetch.

Own-ship telemetry lands in ``vessel_state``, which is already migrated.
The socket reader and the NMEA parser live in
:mod:`app.services.relays.gps_relay` and push continuously; this adapter
exists only so the source list can report whether an endpoint is
configured.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.config import get_settings


class GPSNMEAAdapter(DataSource):
    name = "gps_nmea"
    label = "Ship GPS (NMEA)"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.GPS_HOST and settings.GPS_PORT)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        raise NotImplementedError(
            "the GPS socket reader lives in app/services/relays/gps_relay.py; "
            "NMEA sentences are pushed continuously into vessel_state rather "
            "than fetched per-day"
        )

    def regrid(self, raw: Any) -> np.ndarray:
        raise NotImplementedError(
            "own-ship GPS is a single point written to vessel_state; it is "
            "not regridded"
        )
