"""Electronic navigational charts — stubbed for PART 2.

ENC cells are static local files under ``data/enc/``, loaded once at
startup and served from memory by the chart endpoint. There is no daily
fetch and no grid: the display pipeline composites them as vector geometry.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.services.field_storage import storage_root


class ENCAdapter(DataSource):
    name = "enc"
    label = "ENC charts (local cells)"

    def version_key(self) -> str:
        return "enc"

    def is_configured(self) -> bool:
        return (storage_root() / "enc").is_dir()

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        raise NotImplementedError(
            "ENC cells are loaded once at startup in PART 2; they are not "
            "fetched per-day"
        )

    def regrid(self, raw: Any) -> np.ndarray:
        raise NotImplementedError("ENC cells are vector charts, not a raster field")
