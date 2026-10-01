"""IBCSO V2 bathymetry.

Source: polar stereographic, 500 m. Delivered as a single static file
rather than a date series — the sea floor does not change on the timescale
of a voyage — so ``is_configured()`` is unconditionally true: this adapter
has no credentials to be missing.

Reduction is ``min()``, never mean or nearest. Bathymetry feeds under-keel
clearance, and the shallowest sounding in a cell is the only defensible
answer when a cell contains both a 40 m channel and a 2 m shoal.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from app.adapters.base import DataSource
from app.services import field_storage
from app.utils.constants import ROI_LAT_MIN, ROI_LON_MIN, ROI_RES, ROI_SHAPE
from app.utils.rasters import validate_roi

GRID_SIDECAR = "bathymetry_grid.json"

_DOWNLOAD_HELP = (
    "IBCSO bathymetry has not been downloaded yet.\n"
    "Run:\n"
    "    cd backend\n"
    "    python scripts/download_ibcso.py --file <IBCSO V2 raster>\n"
    "to write:\n"
    "    {npy}\n"
    "    {sidecar}\n"
    "Obtain the raster from https://www.pangaea.de (search 'IBCSO v2'); the\n"
    "file location is versioned by DOI, so it is not hard-coded here.\n"
    "The download is one-time - there are no credentials involved."
)


def _download_help() -> str:
    """Substitute the resolved paths. Built lazily: resolving storage needs
    settings, and settings must not be required merely to import this module."""
    npy = field_storage.bathymetry_path()
    return _DOWNLOAD_HELP.format(npy=npy, sidecar=npy.parent / GRID_SIDECAR)


class IBCSOAdapter(DataSource):
    name = "ibcso"
    label = "IBCSO V2 (bathymetry)"

    def version_key(self) -> str:
        return "bathymetry"

    def is_configured(self) -> bool:
        # No credentials: a local static source is always "configured". The
        # file's absence is reported by fetch() as FileNotFoundError, which
        # is more useful than pretending the source is unconfigured.
        return True

    async def fetch(self, day: date) -> Any:
        del day  # static field — the date is irrelevant by design
        return self.load()

    def load(self) -> dict:
        """Read the stored raster and its grid description."""
        npy_path = field_storage.bathymetry_path()
        if not npy_path.exists():
            raise FileNotFoundError(_download_help())

        grid_path = npy_path.parent / GRID_SIDECAR
        if not grid_path.exists():
            raise FileNotFoundError(
                f"{grid_path} is missing alongside {npy_path}.\n"
                "Re-run `python scripts/download_ibcso.py` to regenerate both."
            )

        depth = np.load(npy_path)
        grid = json.loads(grid_path.read_text(encoding="utf-8"))
        for key in ("lat_min", "lat_step", "lon_min", "lon_step", "shape"):
            if key not in grid:
                raise ValueError(
                    f"{grid_path} is missing '{key}'; re-run "
                    "`python scripts/download_ibcso.py`"
                )

        rows, cols = depth.shape
        if tuple(grid["shape"]) != (rows, cols):
            raise ValueError(
                f"{grid_path} declares shape {grid['shape']} but {npy_path} is "
                f"{(rows, cols)}; re-run `python scripts/download_ibcso.py`"
            )

        lat = float(grid["lat_min"]) + np.arange(rows, dtype=np.float64) * float(grid["lat_step"])
        lon = float(grid["lon_min"]) + np.arange(cols, dtype=np.float64) * float(grid["lon_step"])
        return {"depth": np.asarray(depth, dtype=np.float32), "lat": lat, "lon": lon}

    def regrid(self, raw: Any) -> np.ndarray:
        """Coarsen the source onto the ROI grid with ``min()``."""
        if not isinstance(raw, dict) or "depth" not in raw:
            raise TypeError(
                "ibcso regrid expects {'depth': ndarray, 'lat': 1D, 'lon': 1D}"
            )
        depth = np.asarray(raw["depth"], dtype=np.float32)
        lat = np.asarray(raw["lat"], dtype=np.float64)
        lon = np.asarray(raw["lon"], dtype=np.float64)

        if depth.ndim != 2 or lat.ndim != 1 or lon.ndim != 1:
            raise ValueError(
                f"ibcso raw must be 2D depth with 1D axes, got "
                f"{depth.shape}, {lat.shape}, {lon.shape}"
            )
        if depth.shape != (lat.size, lon.size):
            raise ValueError(
                f"ibcso depth shape {depth.shape} does not match axes "
                f"({lat.size}, {lon.size})"
            )

        rows, cols = depth.shape
        n_rows, n_cols = ROI_SHAPE
        row_step = rows / n_rows
        col_step = cols / n_cols
        row_factor = round(row_step)
        col_factor = round(col_step)

        # Fast path: an exactly aligned grid reduces by a clean reshape,
        # which is both faster and free of off-by-one edge cases.
        if (
            row_factor == row_step
            and col_factor == col_step
            and row_factor >= 1
            and col_factor >= 1
            and abs(float(lat[0]) - ROI_LAT_MIN) < 1e-9
            and abs(float(lon[0]) - ROI_LON_MIN) < 1e-9
        ):
            reduced = depth.reshape(n_rows, row_factor, n_cols, col_factor)
            return np.nanmin(reduced, axis=(1, 3)).astype(np.float32)

        return self._bin_min(depth, lat, lon)

    @staticmethod
    def _bin_min(depth: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """General path: assign every source pixel to an ROI cell, take min.

        Correct for any source resolution or origin, which is what makes it
        the fallback when the fast path's alignment assumption does not hold.
        Two stages — reduce over source rows, then over source columns — so
        the full raster never has to be materialised as an index array.
        """
        n_rows, n_cols = ROI_SHAPE
        out = np.full(ROI_SHAPE, np.nan, dtype=np.float32)

        lat_idx = np.floor((lat - ROI_LAT_MIN) / ROI_RES).astype(np.int64)
        lon_idx = np.floor((lon - ROI_LON_MIN) / ROI_RES).astype(np.int64)
        row_ok = (lat_idx >= 0) & (lat_idx < n_rows)
        col_ok = (lon_idx >= 0) & (lon_idx < n_cols)
        if not row_ok.any() or not col_ok.any():
            raise ValueError(
                "the IBCSO raster does not overlap the AURORA ROI at all; "
                "the file is probably for the wrong hemisphere"
            )

        sub = depth[np.ix_(np.where(row_ok)[0], np.where(col_ok)[0])]
        # Land / nodata is NaN; pushing it to +inf keeps it from poisoning a
        # cell that also contains real soundings.
        sub = np.where(np.isfinite(sub), sub, np.inf)

        row_ids = lat_idx[row_ok]
        col_ids = lon_idx[col_ok]

        # Stage 1 — minimum across the source rows inside each ROI row.
        order = np.argsort(row_ids, kind="stable")
        sorted_row_ids = row_ids[order]
        starts = np.flatnonzero(
            np.concatenate(([True], sorted_row_ids[1:] != sorted_row_ids[:-1]))
        )
        row_min = np.minimum.reduceat(sub[order], starts, axis=0)
        row_targets = sorted_row_ids[starts]

        # Stage 2 — minimum across the source columns inside each ROI column.
        for target_row, mins in zip(row_targets, row_min):
            local = np.full(n_cols, np.inf, dtype=np.float32)
            np.minimum.at(local, col_ids, mins)
            out[target_row] = np.where(np.isfinite(local), local, np.nan)

        return validate_roi(out, "ibcso.depth")
