"""AISStream.io WebSocket relay — stubbed for PART 2.

The schema (``ais_track``) already exists and the adapter contract is
fixed now, so PART 2 only has to fill in the socket loop. Until then the
source reports itself honestly: configured if there is a key, unconfigured
if there is not, and no data either way.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.config import get_settings

STREAM_URL = "wss://stream.aisstream.io/v0/stream"


class AISStreamAdapter(DataSource):
    name = "aisstream"
    label = "AISStream.io (real-time AIS)"

    def is_configured(self) -> bool:
        return bool(get_settings().AISSTREAM_API_KEY)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        raise NotImplementedError(
            "the AISStream relay is implemented in PART 2; messages land in "
            "the ais_track table as they arrive rather than being fetched "
            "per-day"
        )

    def regrid(self, raw: Any) -> np.ndarray:
        raise NotImplementedError(
            "AIS messages are points written to ais_track; they are not "
            "regridded"
        )
