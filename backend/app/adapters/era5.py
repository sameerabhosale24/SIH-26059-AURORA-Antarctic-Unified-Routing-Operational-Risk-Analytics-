"""ERA5 / ERA5T surface fields: u10, v10, t2m.

Source grid is already 0.25 degree regular lat/lon, but the ROI cell centres
sit half a cell off the ERA5 grid, so "crop to ROI" is a bounding-box crop
followed by a nearest-sample onto the ROI axes. Nearest rather than linear:
the model was trained on fields assembled the same way, and mixing
interpolation schemes between training and inference is how a forecast
drifts without ever looking wrong.

Hourly files are reduced to a daily mean before sampling — the forecaster
consumes one field per day.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.config import get_settings
from app.utils.grid import roi_bounds, roi_lat_array, roi_lon_array
from app.utils.rasters import stack_channels, validate_roi

# Variable names as they appear in the downloaded NetCDF (short names, then
# the long names CDS sometimes substitutes).
U10_NAMES = ("u10", "10m_u_component_of_wind", "u10m")
V10_NAMES = ("v10", "10m_v_component_of_wind", "v10m")
T2M_NAMES = ("t2m", "2m_temperature", "t2m_temperature")

CHANNEL_ORDER = (U10_NAMES, V10_NAMES, T2M_NAMES)
CHANNEL_LABELS = ("u10", "v10", "t2m")

CDS_DATASET = "reanalysis-era5-single-levels"
CDS_VARIABLES = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_temperature",
]

TEMP_WORKDIR = Path("./data/cache")


def _pick(dataset, names: tuple[str, ...]):
    for candidate in names:
        if candidate in dataset.variables:
            return dataset[candidate]
    raise KeyError(f"none of {names} present in ERA5 dataset; have {list(dataset.data_vars)}")


def _sample_to_roi(field):
    """Bounding-box crop, then nearest-sample onto the ROI axes."""
    import xarray as xr

    lat = field["lat"]
    lon = field["lon"]
    west, south, east, north = roi_bounds()

    lat_first, lat_last = float(lat[0]), float(lat[-1])
    lon_first, lon_last = float(lon[0]), float(lon[-1])
    lat_slice = slice(lat_first, lat_last) if lat_first > lat_last else slice(lat_last, lat_first)
    lon_slice = slice(lon_first, lon_last) if lon_first < lon_last else slice(lon_last, lon_first)
    cropped = field.sel(lat=lat_slice, lon=lon_slice)

    return cropped.interp(
        lat=xr.DataArray(roi_lat_array(), dims="lat"),
        lon=xr.DataArray(roi_lon_array(), dims="lon"),
        method="nearest",
    )


def _reduce_time(dataset):
    """Hourly -> daily mean when a time axis with more than one step exists."""
    for candidate in ("time", "valid_time", "forecast_hour"):
        if candidate in dataset.dims and dataset.sizes[candidate] > 1:
            return dataset.mean(dim=candidate, skipna=True)
    return dataset


class ERA5Adapter(DataSource):
    name = "era5"
    label = "ERA5 (u10, v10, t2m)"

    def version_key(self) -> str:
        return "weather"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.CDSAPI_URL and settings.CDSAPI_KEY)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        settings = get_settings()
        try:
            import cdsapi
        except ImportError as exc:
            raise RuntimeError(
                "the CDS API client is not installed; run "
                "`pip install cdsapi` to enable the ERA5 adapter"
            ) from exc

        west, south, east, north = roi_bounds()
        target = TEMP_WORKDIR / f"era5_{day:%Y-%m-%d}.nc"
        target.parent.mkdir(parents=True, exist_ok=True)

        request = {
            "product_type": ["reanalysis"],
            "variable": list(CDS_VARIABLES),
            "year": [f"{day:%Y}"],
            "month": [f"{day:%m}"],
            "day": [f"{day:%d}"],
            "time": [f"{h:02d}:00" for h in range(24)],
            "format": "netcdf",
            # north, west, south, east — one cell of slack around the ROI so
            # the edge sample never falls outside the download.
            "area": [round(north + 0.25, 4), round(west - 0.25, 4),
                     round(south - 0.25, 4), round(east + 0.25, 4)],
        }
        client = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY)
        self.logger.info("requesting ERA5 for %s", day.isoformat())
        await _to_thread(client.retrieve, CDS_DATASET, request, str(target))

        import xarray as xr

        return xr.open_dataset(target, decode_cf=True)

    def regrid(self, raw: Any) -> np.ndarray:
        import xarray as xr

        if not isinstance(raw, xr.Dataset):
            raise TypeError(f"era5 regrid expects an xarray.Dataset, got {type(raw)!r}")

        dataset = _reduce_time(raw)
        frames = []
        for names, label in zip(CHANNEL_ORDER, CHANNEL_LABELS):
            field = _pick(dataset, names)
            if field.ndim > 2:
                field = field.squeeze(drop=True)
            sampled = _sample_to_roi(field)
            array = np.asarray(sampled.values, dtype=np.float32)
            if array.shape != (101, 361):
                raise ValueError(
                    f"era5 channel {label} sampled to {array.shape}, expected (101, 361)"
                )
            frames.append(validate_roi(array, f"era5.{label}"))
        return stack_channels(frames, "era5")


async def _to_thread(func, *args, **kwargs):
    """Run a blocking CDS call off the event loop."""
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)


def _utc_now() -> datetime:  # pragma: no cover — helper for callers
    return datetime.now(timezone.utc)
