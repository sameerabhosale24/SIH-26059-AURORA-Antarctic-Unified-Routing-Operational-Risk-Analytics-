"""Electronic navigational charts — not a per-day fetch.

ENC cells are static local files under ``data/enc/``: no daily fetch and
no grid, because the display pipeline composites them as vector geometry.
``GET /api/enc/manifest`` already serves whatever is there; S-57 parsing
into that manifest is not implemented, so an empty ``data/enc/`` currently
produces an empty cell list.
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
            "ENC cells are static files served by GET /api/enc/manifest; "
            "they are not fetched per-day"
        )

    def regrid(self, raw: Any) -> np.ndarray:
        raise NotImplementedError("ENC cells are vector charts, not a raster field")
