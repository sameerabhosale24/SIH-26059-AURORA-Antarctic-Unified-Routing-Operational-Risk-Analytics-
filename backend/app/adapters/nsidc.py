"""NSIDC CDR v6 sea ice concentration (G02135).

Source grid: polar stereographic, 25 km, EPSG:3976 (both hemispheres). The
ROI grid sits half a cell off a conventional lat/lon quarter grid, so the
source is *resampled* rather than sliced: nearest neighbour with a 50 km
radius of influence.

Nearest neighbour with NaN fill is deliberate. Interpolating across the
coastline would invent intermediate concentrations between land and sea, and
a coastal band of NaN renders as transparent on the map — which is correct,
because we do not know what is there.
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
EPSG_NORTH = "EPSG:3413"
EPSG_SOUTH = "EPSG:3976"

CDR_VARIABLE = "cdr_sea_ice_concentration"
TIME_VARIABLES = ("time", "t")

# NSIDC Earthdata login (DAAC) — same credentials as Earthdata Login.
OCEAN_DATA_URL = "https://n5eil01u.ecs.nsidc.org/DP4/ICE_MEASURE/G02135/006"


class NSIDCAdapter(DataSource):
    name = "nsidc"
    label = "NSIDC CDR v6 (SIC)"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.NSIDC_USERNAME and settings.NSIDC_PASSWORD)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        settings = get_settings()
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover — dependency guard
            raise RuntimeError("httpx is required for the NSIDC adapter") from exc

        url = f"{OCEAN_DATA_URL}/{day:%Y}/{day:%m}/SeaIce_Daily_{day:%Y%m%d}_v2.0.nc"
        self.logger.info("downloading NSIDC CDR for %s", day.isoformat())
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                auth=(settings.NSIDC_USERNAME, settings.NSIDC_PASSWORD),
            )
            response.raise_for_status()
            payload = response.content

        try:
            import xarray as xr
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("xarray is required for the NSIDC adapter") from exc

        return xr.open_dataset(__import__("io").BytesIO(payload), decode_cf=True)

    def regrid(self, raw: Any) -> np.ndarray:
        """Nearest-neighbour onto the ROI grid; NaN outside 50 km."""
        import xarray as xr
        from pyresample import SwathDefinition, kd_tree

        if not isinstance(raw, xr.Dataset):
            raise TypeError(f"nsidc regrid expects an xarray.Dataset, got {type(raw)!r}")
        if CDR_VARIABLE not in raw:
            raise KeyError(
                f"NSIDC file has no '{CDR_VARIABLE}' variable; found "
                f"{list(raw.data_vars)}"
            )

        dataset = raw
        for candidate in TIME_VARIABLES:
            if candidate in dataset.sizes and dataset.sizes[candidate] > 1:
                dataset = dataset.isel({candidate: 0})
                break

        concentration = dataset[CDR_VARIABLE].squeeze()
        if concentration.ndim != 2:
            raise ValueError(
                f"expected a 2D SIC field after squeezing, got shape "
                f"{tuple(concentration.shape)}"
            )

        lons, lats = self._source_coordinates(dataset, concentration)
        target_lons, target_lats = roi_lat_lon_meshgrid()

        source = SwathDefinition(lons=lons, lats=lats)
        target = SwathDefinition(lons=target_lons, lats=target_lats)

        result = kd_tree.resample_nearest(
            source,
            target,
            source_data=np.asarray(concentration.values, dtype=np.float64),
            radius_of_influence=RADIUS_OF_INFLUENCE_M,
            fill_value=np.nan,
            reduce_data=True,
        )

        grid = np.asarray(result, dtype=np.float32)
        # The CDR ships integers scaled by 0.01. xarray usually applies the
        # scale factor, but files without CF attributes arrive as 0-100 —
        # normalise rather than feed a 100x-too-large field to the model.
        finite = grid[np.isfinite(grid)]
        if finite.size and float(np.nanmax(np.abs(finite))) > 1.5:
            grid = grid / 100.0
        grid = np.where(np.isfinite(grid), np.clip(grid, 0.0, 1.0), np.nan)
        return validate_roi(grid, "nsidc.sic")

    def _source_coordinates(self, dataset, concentration) -> tuple[np.ndarray, np.ndarray]:
        """Per-pixel lon/lat shipped in the file.

        Every distribution of the NSIDC CDR carries ``latitude`` and
        ``longitude`` arrays, so there is no need to reconstruct the grid from
        the CRS. If they are absent the file is not one we understand, and
        guessing a geotransform is exactly how a field ends up 500 km from
        where it belongs.
        """
        for lon_name in ("longitude", "lon"):
            for lat_name in ("latitude", "lat"):
                if lon_name in dataset.variables and lat_name in dataset.variables:
                    lons = np.asarray(dataset[lon_name].values, dtype=np.float64)
                    lats = np.asarray(dataset[lat_name].values, dtype=np.float64)
                    if lons.shape == concentration.shape and lats.shape == concentration.shape:
                        return lons, lats

        raise ValueError(
            "NSIDC file carries no longitude/latitude variables matching the "
            f"SIC field shape {tuple(concentration.shape)}; expected "
            "'longitude'/'latitude' (or 'lon'/'lat') in the file. "
            "Refusing to assume a geotransform."
        )
