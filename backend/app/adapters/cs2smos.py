"""CS2SMOS sea ice thickness.

Source: EASE-Grid 2.0 South, 25 km. Resampled with nearest neighbour and a
50 km radius of influence, same as NSIDC — thickness is a sparse product
with large gaps around the coast and the ice edge, and interpolating across
a gap would manufacture thickness where there is none.

Thickness is assembled and tracked for staleness but is not one of the ten
forecaster channels; it feeds the route optimizer's ice limit checks.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.config import get_settings
from app.utils.grid import roi_lat_lon_meshgrid
from app.utils.rasters import validate_roi

RADIUS_OF_INFLUENCE_M = 50_000.0
THICKNESS_VARIABLES = ("sea_ice_thickness", "sit", "thickness", "lti")
DATASET_ID = "sea_ice_thickness"


class CS2SMOSAdapter(DataSource):
    name = "cs2smos"
    label = "CS2SMOS (ice thickness)"

    def version_key(self) -> str:
        return "ice_thickness"

    def is_configured(self) -> bool:
        # Copernicus Marine credentials cover the CS2SMOS product. AWI FTP
        # is an equivalent distribution but needs its own credentials, which
        # are not part of the shipped config — see README.
        settings = get_settings()
        return bool(settings.CMEMS_USERNAME and settings.CMEMS_PASSWORD)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        settings = get_settings()

        try:
            import copernicusmarine
        except ImportError as exc:
            raise RuntimeError(
                "the Copernicus Marine client is not installed; run "
                "`pip install copernicusmarine` to enable the CS2SMOS adapter"
            ) from exc

        self.logger.info("opening CS2SMOS for %s", day.isoformat())
        try:
            return copernicusmarine.open_dataset(
                dataset_id=DATASET_ID,
                username=settings.CMEMS_USERNAME,
                password=settings.CMEMS_PASSWORD,
                start_date=datetime_start(day),
                end_date=datetime_end(day),
            )
        except TypeError as exc:  # pragma: no cover — client API drift
            raise RuntimeError(
                f"copernicusmarine.open_dataset rejected the request ({exc}); "
                "see https://github.com/copernicusmarine/copernicusmarine-py"
            ) from exc

    def regrid(self, raw: Any) -> np.ndarray:
        import xarray as xr
        from pyresample import SwathDefinition, kd_tree

        if not isinstance(raw, (xr.Dataset, xr.DataArray)):
            raise TypeError(f"cs2smos regrid expects xarray data, got {type(raw)!r}")

        if isinstance(raw, xr.Dataset):
            thickness = None
            for candidate in THICKNESS_VARIABLES:
                if candidate in raw.variables:
                    thickness = raw[candidate]
                    break
            if thickness is None:
                raise KeyError(
                    f"CS2SMOS file has none of {THICKNESS_VARIABLES}; "
                    f"found {list(raw.data_vars)}"
                )
            dataset = raw
        else:
            thickness = raw
            dataset = raw.to_dataset()

        for candidate in ("time", "t"):
            if candidate in thickness.dims and thickness.sizes.get(candidate, 1) > 1:
                thickness = thickness.isel({candidate: 0})

        lons, lats = _source_coordinates(dataset, thickness)
        target_lons, target_lats = roi_lat_lon_meshgrid()

        result = kd_tree.resample_nearest(
            SwathDefinition(lons=lons, lats=lats),
            SwathDefinition(lons=target_lons, lats=target_lats),
            source_data=np.asarray(thickness.values, dtype=np.float64),
            radius_of_influence=RADIUS_OF_INFLUENCE_M,
            fill_value=np.nan,
            reduce_data=True,
        )
        return validate_roi(np.asarray(result, dtype=np.float32), "cs2smos.thickness")


def _source_coordinates(dataset, thickness) -> tuple[np.ndarray, np.ndarray]:
    """lon/lat from the file, either as variables or derived from GeoTransform."""
    for lon_name in ("longitude", "lon"):
        for lat_name in ("latitude", "lat"):
            if lon_name in dataset.variables and lat_name in dataset.variables:
                lons = np.asarray(dataset[lon_name].values, dtype=np.float64)
                lats = np.asarray(dataset[lat_name].values, dtype=np.float64)
                if lons.shape == thickness.shape and lats.shape == thickness.shape:
                    return lons, lats

    geotransform = None
    crs_wkt = None
    for var in dataset.variables:
        attrs = dataset[var].attrs
        geotransform = geotransform or attrs.get("GeoTransform") or attrs.get("geotransform")
        crs_wkt = (
            crs_wkt
            or attrs.get("spatial_ref")
            or attrs.get("crs_wkt")
            or attrs.get("grid_mapping_wkt")
        )
    if geotransform and crs_wkt:
        from pyresample import AreaDefinition

        values = [float(v) for v in str(geotransform).split()]
        if len(values) == 6:
            x0, x_res, _, y0, _, y_res = values
            height, width = thickness.shape
            area_extent = (x0, y0 + y_res * height, x0 + x_res * width, y0)
            area = AreaDefinition(
                None, None, None, width, height, x_res, abs(y_res), area_extent, area_def_id=crs_wkt
            )
            cols, rows = np.meshgrid(np.arange(width), np.arange(height))
            lons, lats = area.get_lonlats(cols, rows)
            return np.asarray(lons, dtype=np.float64), np.asarray(lats, dtype=np.float64)

    raise ValueError(
        "CS2SMOS file carries neither longitude/latitude variables nor a "
        "usable GeoTransform + CRS; refusing to guess the grid."
    )


def datetime_start(day: date):
    from datetime import datetime, time, timezone

    return datetime.combine(day, time(0, 0), tzinfo=timezone.utc)


def datetime_end(day: date):
    from datetime import datetime, time, timezone

    return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
