"""AISStream.io WebSocket relay — not a per-day fetch.

The live socket loop lives in :mod:`app.services.relays.ais_relay` and
writes straight into ``ais_track`` as messages arrive, so there is nothing
for this adapter to download. It stays in the registry as the honest
answer to "is this source configured": yes with a key, no without one, and
no per-day data either way.
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
            "the AISStream relay lives in app/services/relays/ais_relay.py; "
            "messages land in the ais_track table as they arrive rather than "
            "being fetched per-day"
        )

    def regrid(self, raw: Any) -> np.ndarray:
        raise NotImplementedError(
            "AIS messages are points written to ais_track; they are not "
            "regridded"
        )
