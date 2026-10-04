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
from app.services.field_storage import storage_root
from app.utils.grid import roi_lat_lon_meshgrid
from app.utils.rasters import validate_roi

RADIUS_OF_INFLUENCE_M = 50_000.0
EPSG_NORTH = "EPSG:3413"
EPSG_SOUTH = "EPSG:3976"

# NOAA CDR v4 (G10016) names the field cdr_seaice_conc; the NASA CDR v6
# (G02135) called it cdr_sea_ice_concentration. Accept both rather than
# breaking on a rename between product generations.
CDR_VARIABLES = ("cdr_seaice_conc", "cdr_sea_ice_concentration")
TIME_VARIABLES = ("time", "t")

# NOAA/NSIDC NRT CDR v4 (G10016) on the anonymous NOAA data pool. The old
# ECS data pool (n5eil01u.ecs.nsidc.org) is unreachable from this network and
# has been superseded; this endpoint needs no Earthdata credentials.
NOAA_NRT_BASE = "https://noaadata.apps.nsidc.org/NOAA/G10016_V4/south/daily"
NRT_FILENAME = "sic_pss25_{day:%Y%m%d}_am2_icdr_v04r00.nc"


class NSIDCAdapter(DataSource):
    name = "nsidc"
    label = "NSIDC CDR v6 (SIC)"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.NSIDC_USERNAME and settings.NSIDC_PASSWORD)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover — dependency guard
            raise RuntimeError("httpx is required for the NSIDC adapter") from exc

        url = f"{NOAA_NRT_BASE}/{day:%Y}/{NRT_FILENAME.format(day=day)}"
        self.logger.info("downloading NSIDC NRT CDR for %s", day.isoformat())
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.content

        try:
            import xarray as xr
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("xarray is required for the NSIDC adapter") from exc

        # Keep the raw download on disk: a regrid failure is then debuggable
        # instead of leaving the payload only in a closed buffer.
        target = storage_root() / "raw_temp" / "nsidc" / NRT_FILENAME.format(day=day)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return xr.open_dataset(target, decode_cf=True)

    def regrid(self, raw: Any) -> np.ndarray:
        """Nearest-neighbour onto the ROI grid; NaN outside 50 km."""
        import xarray as xr
        from pyresample import SwathDefinition, kd_tree

        if not isinstance(raw, xr.Dataset):
            raise TypeError(f"nsidc regrid expects an xarray.Dataset, got {type(raw)!r}")
        variable = next((name for name in CDR_VARIABLES if name in raw), None)
        if variable is None:
            raise KeyError(
                f"NSIDC file has none of {list(CDR_VARIABLES)}; found "
                f"{list(raw.data_vars)}"
            )

        dataset = raw
        for candidate in TIME_VARIABLES:
            if candidate in dataset.sizes and dataset.sizes[candidate] > 1:
                dataset = dataset.isel({candidate: 0})
                break

        concentration = dataset[variable].squeeze()
        if concentration.ndim != 2:
            raise ValueError(
                f"expected a 2D SIC field after squeezing, got shape "
                f"{tuple(concentration.shape)}"
            )

        lons, lats = self._source_coordinates(dataset, concentration)
        # roi_lat_lon_meshgrid() documents (lat2d, lon2d) — unpack in that
        # order or every target coordinate is swapped and the resample
        # silently returns all-NaN.
        target_lats, target_lons = roi_lat_lon_meshgrid()

        source = SwathDefinition(lons=lons, lats=lats)
        target = SwathDefinition(lons=target_lons, lats=target_lats)

        result = kd_tree.resample_nearest(
            source,
            np.asarray(concentration.values, dtype=np.float64),
            target,
            RADIUS_OF_INFLUENCE_M,
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
        """Per-pixel lon/lat for the source grid.

        Two layouts are accepted, in order:

        1. ``longitude``/``latitude`` arrays shipped in the file (the NASA
           CDR layout).
        2. ``x``/``y`` polar-stereographic axes plus a CF ``grid_mapping``
           with a ``proj4text`` (the NOAA CDR v4 layout). The lon/lat grid is
           then computed from that declared CRS — from the file's own
           projection parameters, not from an assumed geotransform.
        """
        for lon_name in ("longitude", "lon"):
            for lat_name in ("latitude", "lat"):
                if lon_name in dataset.variables and lat_name in dataset.variables:
                    lons = np.asarray(dataset[lon_name].values, dtype=np.float64)
                    lats = np.asarray(dataset[lat_name].values, dtype=np.float64)
                    if lons.shape == concentration.shape and lats.shape == concentration.shape:
                        return lons, lats

        if "x" in dataset.coords and "y" in dataset.coords:
            lons, lats = self._project_xy_to_lonlat(dataset)
            if lons.shape == concentration.shape and lats.shape == concentration.shape:
                return lons, lats

        raise ValueError(
            "NSIDC file carries no longitude/latitude variables matching the "
            f"SIC field shape {tuple(concentration.shape)}, and no usable "
            "x/y grid mapping; found "
            f"coordinates {list(dataset.coords)}."
        )

    def _project_xy_to_lonlat(self, dataset) -> tuple[np.ndarray, np.ndarray]:
        """Transform the file's ``x``/``y`` axes to lon/lat via its own CRS."""
        try:
            import pyproj
        except ImportError as exc:  # pragma: no cover — dependency guard
            raise RuntimeError("pyproj is required to read the polar-stereographic grid") from exc

        proj4 = None
        for candidate in ("crs", "spatial_ref", "grid_mapping"):
            if candidate in dataset.variables:
                attrs = dataset[candidate].attrs
                proj4 = attrs.get("proj4text")
                if proj4:
                    break
        if not proj4:
            raise ValueError(
                "NSIDC x/y grid has no grid_mapping variable carrying "
                "'proj4text'; cannot derive lon/lat without the declared CRS."
            )

        x = np.asarray(dataset["x"].values, dtype=np.float64)
        y = np.asarray(dataset["y"].values, dtype=np.float64)
        xx, yy = np.meshgrid(x, y)
        transformer = pyproj.Transformer.from_crs(
            pyproj.CRS.from_proj4(proj4), pyproj.CRS.from_epsg(4326), always_xy=True
        )
        lons, lats = transformer.transform(xx, yy)
        return np.asarray(lons, dtype=np.float64), np.asarray(lats, dtype=np.float64)
