"""CMEMS GLORYS12V1 ocean state: uo, vo, thetao, so, zos.

Source grid is 1/12 degree regular lat/lon — roughly five times finer than
the ROI — so the crop is a linear interpolation rather than a sample. That
is the one place in AURORA where interpolation is the right answer: at
1/12 degree the neighbours genuinely constrain the value between them.

Only the shallowest level (~0.494 m) is used. The forecaster predicts
surface sea ice; a deep current tells it nothing and would only add a
channel the model was never trained to read.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.config import get_settings
from app.utils.grid import roi_bounds, roi_lat_array, roi_lon_array
from app.utils.rasters import stack_channels, validate_roi

DEPTH_NAMES = ("depth", "lev", "level")
TIME_NAMES = ("time", "valid_time")
VARIABLES = ("uo", "vo", "thetao", "so", "zos")
CHANNEL_LABELS = VARIABLES

# Global ocean physics analysis + forecast (CMEMS 2.x catalogue id).
DATASET_ID = "cmems_mod_glo_phy_anfc_0.083deg_P1D-m"


def _find_dim(dataset, names: tuple[str, ...]) -> str | None:
    for candidate in names:
        if candidate in dataset.dims:
            return candidate
    return None


def _crop_and_interp(field):
    """Bounding crop, then linear interpolation onto the ROI axes."""
    import xarray as xr

    west, south, east, north = roi_bounds()
    lat = field["latitude"] if "latitude" in field.coords else field["lat"]
    lon = field["longitude"] if "longitude" in field.coords else field["lon"]

    lat_first, lat_last = float(lat[0]), float(lat[-1])
    lon_first, lon_last = float(lon[0]), float(lon[-1])
    lat_slice = slice(lat_first, lat_last) if lat_first > lat_last else slice(lat_last, lat_first)
    lon_slice = slice(lon_first, lon_last) if lon_first < lon_last else slice(lon_last, lon_first)

    lat_name = "latitude" if "latitude" in field.coords else "lat"
    lon_name = "longitude" if "longitude" in field.coords else "lon"
    cropped = field.sel({lat_name: lat_slice, lon_name: lon_slice})

    return cropped.interp(
        {lat_name: xr.DataArray(roi_lat_array(), dims=lat_name),
         lon_name: xr.DataArray(roi_lon_array(), dims=lon_name)},
        method="linear",
    )


def _shallowest(dataset):
    depth_name = _find_dim(dataset, DEPTH_NAMES)
    if depth_name is None:
        return dataset
    depth = dataset[depth_name]
    shallowest = float(np.min(np.asarray(depth.values)))
    return dataset.sel({depth_name: shallowest})


def _reduce_time(dataset):
    time_name = _find_dim(dataset, TIME_NAMES)
    if time_name is not None and dataset.sizes[time_name] > 1:
        return dataset.mean(dim=time_name, skipna=True)
    return dataset


class CMEMSAdapter(DataSource):
    name = "cmems"
    label = "CMEMS GLORYS12V1 (ocean)"

    def version_key(self) -> str:
        return "currents"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.CMEMS_USERNAME and settings.CMEMS_PASSWORD)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        settings = get_settings()
        west, south, east, north = roi_bounds()

        try:
            import copernicusmarine
        except ImportError as exc:
            raise RuntimeError(
                "the Copernicus Marine client is not installed; run "
                "`pip install copernicusmarine` to enable the CMEMS adapter"
            ) from exc

        self.logger.info("opening CMEMS %s for %s", DATASET_ID, day.isoformat())
        try:
            dataset = copernicusmarine.open_dataset(
                dataset_id=DATASET_ID,
                username=settings.CMEMS_USERNAME,
                password=settings.CMEMS_PASSWORD,
                minimum_longitude=west - 0.5,
                maximum_longitude=east + 0.5,
                minimum_latitude=south - 0.5,
                maximum_latitude=north + 0.5,
                minimum_depth=0.0,
                maximum_depth=5.0,
                start_datetime=datetime_utc(day),
                end_datetime=datetime_utc(day, end=True),
                variables=list(VARIABLES),
            )
        except TypeError as exc:  # pragma: no cover — client API drift
            raise RuntimeError(
                "copernicusmarine.open_dataset rejected the requested keyword "
                f"arguments ({exc}); the installed client may use a different "
                "API — see https://github.com/copernicusmarine/copernicusmarine-py"
            ) from exc
        return dataset

    def regrid(self, raw: Any) -> np.ndarray:
        import xarray as xr

        if not isinstance(raw, xr.Dataset):
            raise TypeError(f"cmems regrid expects an xarray.Dataset, got {type(raw)!r}")

        dataset = _reduce_time(_shallowest(raw))
        missing = [v for v in VARIABLES if v not in dataset.variables]
        if missing:
            raise KeyError(f"CMEMS dataset is missing {missing}; have {list(dataset.data_vars)}")

        frames = []
        for name in VARIABLES:
            field = dataset[name]
            if field.ndim > 2:
                field = field.squeeze(drop=True)
            sampled = _crop_and_interp(field)
            array = np.asarray(sampled.values, dtype=np.float32)
            if array.shape != (101, 361):
                raise ValueError(
                    f"cmems channel {name} interpolated to {array.shape}, "
                    "expected (101, 361)"
                )
            if name == "thetao":
                # The model consumes absolute temperature; GLORYS reports
                # Celsius and forgetting this one conversion produces a
                # physically absurd forecast that still looks plausible.
                array = array + 273.15
                self.logger.info("thetao converted to Kelvin (%.2f K median)",
                                 float(np.nanmedian(array)))
            frames.append(validate_roi(array, f"cmems.{name}"))
        return stack_channels(frames, "cmems")


def datetime_utc(day: date, end: bool = False):
    """datetime for the start (00:00) or end (23:59:59) of ``day``."""
    from datetime import datetime, time, timezone

    if end:
        return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
    return datetime.combine(day, time(0, 0, 0), tzinfo=timezone.utc)
