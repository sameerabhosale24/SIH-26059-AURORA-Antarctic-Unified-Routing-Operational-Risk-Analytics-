"""Data source adapters.

``ADAPTERS`` is the registry the health endpoint and the schedulers walk.
Order matters only for log readability — nothing here depends on it.
"""

from __future__ import annotations

from app.adapters.aisstream import AISStreamAdapter
from app.adapters.base import DataSource
from app.adapters.byu_scp import BYUSCPAdapter
from app.adapters.cmems import CMEMSAdapter
from app.adapters.cs2smos import CS2SMOSAdapter
from app.adapters.era5 import ERA5Adapter
from app.adapters.enc import ENCAdapter
from app.adapters.gps_nmea import GPSNMEAAdapter
from app.adapters.ibcso import IBCSOAdapter
from app.adapters.nsidc import NSIDCAdapter

ADAPTERS: dict[str, DataSource] = {
    adapter.name: adapter
    for adapter in (
        NSIDCAdapter(),
        ERA5Adapter(),
        CMEMSAdapter(),
        CS2SMOSAdapter(),
        IBCSOAdapter(),
        BYUSCPAdapter(),
        AISStreamAdapter(),
        GPSNMEAAdapter(),
        ENCAdapter(),
    )
}

#: Adapters that produce a regridded field for the forecaster input window.
GRID_SOURCES = ("nsidc", "era5", "cmems", "cs2smos", "ibcso")

#: Adapters surfaced on GET /api/health (PART 2 sources are listed too, but
#: they are report-only until their relays land).
HEALTH_SOURCES = ("nsidc", "era5", "cmems", "cs2smos", "ibcso", "byu_scp")


def get_adapter(name: str) -> DataSource:
    try:
        return ADAPTERS[name]
    except KeyError:
        raise KeyError(f"unknown data source {name!r}; known: {sorted(ADAPTERS)}") from None


def health_snapshot() -> dict[str, dict]:
    """``{name: {"configured": bool, "last_fetch": ts|null}}`` for health.

    Synchronous and single-query: the FastAPI endpoint wraps it in
    ``asyncio.to_thread`` so a slow database read never stalls the loop.
    """
    from app.services.version_service import last_fetch_map

    adapters = [ADAPTERS[name] for name in HEALTH_SOURCES]
    fetches = last_fetch_map([adapter.version_key() for adapter in adapters])
    return {
        adapter.name: {
            "configured": adapter.is_configured(),
            "last_fetch": fetches.get(adapter.version_key()),
        }
        for adapter in adapters
    }


__all__ = [
    "ADAPTERS",
    "AISStreamAdapter",
    "BYUSCPAdapter",
    "CMEMSAdapter",
    "CS2SMOSAdapter",
    "DataSource",
    "ENCAdapter",
    "ERA5Adapter",
    "GPSNMEAAdapter",
    "GRID_SOURCES",
    "HEALTH_SOURCES",
    "IBCSOAdapter",
    "NSIDCAdapter",
    "get_adapter",
    "health_snapshot",
]
