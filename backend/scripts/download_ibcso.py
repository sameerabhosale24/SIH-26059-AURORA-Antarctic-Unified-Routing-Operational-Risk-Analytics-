"""Fetch IBCSO V2 bathymetry and store it for the AURORA ROI.

    python scripts/download_ibcso.py --file IBCSO_v2.tif
    python scripts/download_ibcso.py --url  <direct file URL>

Writes two files next to the other fields:

    data/fields/bathymetry.npy        float32 depth, positive down
    data/fields/bathymetry_grid.json  grid origin, step and shape

The grid is deliberately aligned to the ROI: origin exactly on
``ROI_LAT_MIN``/``ROI_LON_MIN`` at a resolution that divides 0.25 degrees
evenly. That is what lets ``IBCSOAdapter.regrid`` take the fast
reshape-and-min path instead of binning 90 million pixels.

Depth is positive down and clipped at zero, so land reads as 0 — the
shallowest possible value. ``min()`` then picks the least deep sounding in
each cell, which is the conservative answer for under-keel clearance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_BACKEND))

from affine import Affine

from app.services.field_storage import bathymetry_path  # noqa: E402
from app.utils.constants import ROI_LAT_MAX, ROI_LAT_MIN, ROI_LON_MAX, ROI_LON_MIN  # noqa: E402

GRID_SIDECAR = "bathymetry_grid.json"
DEFAULT_RESOLUTION = 0.01


def build_target_grid(resolution: float) -> dict:
    """A grid whose pixel CENTRES land exactly on the ROI sample points.

    ``lat_min``/``lon_min`` are the centres of pixel (0, 0), so
    ``lat_min + i * lat_step == ROI_LAT_MIN + i * resolution``. That is what
    lets ``IBCSOAdapter.regrid`` group 25 consecutive rows into one ROI cell
    and still agree with its own ``_bin_min`` fallback. It also means the
    raster transform below has to start a half step outside the ROI — see
    ``_dst_transform``.
    """
    if resolution <= 0:
        raise ValueError("resolution must be positive")
    rows = int(round((ROI_LAT_MAX - ROI_LAT_MIN) / resolution))
    cols = int(round((ROI_LON_MAX - ROI_LON_MIN) / resolution))
    if rows % 101 or cols % 361:
        raise ValueError(
            f"resolution {resolution} gives a {rows}x{cols} grid, which is not "
            "divisible into the 101x361 ROI cells; choose a resolution that "
            "divides 0.25 evenly (0.01, 0.005, 0.0025, ...)"
        )
    return {
        "lat_min": ROI_LAT_MIN,
        "lat_step": resolution,
        "lon_min": ROI_LON_MIN,
        "lon_step": resolution,
        "shape": (rows, cols),
        "resolution": resolution,
    }


def _dst_transform(grid: dict):
    """South-up affine: row 0 is the southernmost row, and each pixel's
    centre sits on the grid the sidecar advertises."""
    rows, cols = grid["shape"]
    step = float(grid["resolution"])
    return Affine(
        step, 0.0, float(grid["lon_min"]) - step / 2.0,
        0.0, step, float(grid["lat_min"]) - step / 2.0,
    )


def _load_source(path: Path):
    """Return ``(array, transform, crs)`` for a GeoTIFF or a georeferenced NetCDF."""
    import rasterio

    suffix = path.suffix.lower()
    if suffix in (".tif", ".tiff"):
        with rasterio.open(path) as src:
            data = src.read(1, masked=True)
            return np.ma.filled(data, np.nan).astype(np.float32), src.transform, src.crs

    if suffix in (".nc", ".nc4", ".netcdf"):
        import xarray as xr

        with xr.open_dataset(path) as dataset:
            variable = _pick_depth_variable(dataset)
            values = np.asarray(variable.values, dtype=np.float32)
            if values.ndim > 2:
                values = np.squeeze(values)

            crs = _crs_from_dataset(dataset, variable)
            transform = _transform_from_dataset(dataset, variable, values.shape, crs)
            # NetCDF convention: elevation above the ellipsoid. Convert to
            # depth, positive down, with land floored at zero.
            depth = -values
            depth = np.where(np.isfinite(depth), np.maximum(depth, 0.0), np.nan)
            return depth.astype(np.float32), transform, crs

    raise ValueError(
        f"unsupported input {path.name!r}: use a GeoTIFF (.tif) or a "
        "georeferenced NetCDF (.nc) carrying a grid mapping"
    )


def _pick_depth_variable(dataset):
    import xarray as xr

    preferred = ("elevation", "depth", "z", "band", "ibcso_bedrock")
    for name in preferred:
        if name in dataset.data_vars:
            return dataset[name]
    numeric = [
        var for name, var in dataset.data_vars.items()
        if np.issubdtype(var.dtype, np.floating) and var.ndim >= 2
    ]
    if len(numeric) == 1:
        return numeric[0]
    raise ValueError(
        f"could not identify the depth variable; candidates were "
        f"{list(dataset.data_vars)}. Rename it to 'elevation' or 'depth'."
    )


def _crs_from_dataset(dataset, variable):
    from rasterio.crs import CRS

    for attrs in (variable.attrs, *[v.attrs for v in dataset.variables.values()]):
        for key in ("spatial_ref", "crs_wkt", "grid_mapping_wkt"):
            if key in attrs:
                try:
                    return CRS.from_wkt(str(attrs[key]))
                except Exception:  # noqa: BLE001 — try the next attribute
                    continue
    raise ValueError(
        "the NetCDF has no spatial_ref / crs_wkt attribute; IBCSO must be "
        "georeferenced. Re-project it to a GeoTIFF first, then pass --file."
    )


def _transform_from_dataset(dataset, variable, shape, crs):
    from affine import Affine
    from rasterio.crs import CRS

    height, width = shape
    for attrs in (variable.attrs, *[v.attrs for v in dataset.variables.values()]):
        raw = attrs.get("GeoTransform") or attrs.get("geotransform")
        if raw:
            parts = [float(v) for v in str(raw).split()]
            if len(parts) == 6:
                x0, x_res, x_skew, y0, y_skew, y_res = parts
                return Affine(x_res, x_skew, x0, y_skew, y_res, y0)
    raise ValueError(
        "the NetCDF has no GeoTransform attribute; re-project it to a "
        "GeoTIFF first, then pass --file."
    )


def reproject_to_roi_grid(depth, transform, crs, resolution: float) -> np.ndarray:
    """Warp onto the aligned ROI grid using the shallowest source sample.

    ``Resampling.min`` is the conservative choice: a cell keeps its least
    deep sounding, so under-keel clearance is never over-estimated.
    """
    from rasterio.warp import Resampling, reproject

    grid = build_target_grid(resolution)
    rows, cols = grid["shape"]
    dst_transform = _dst_transform(grid)
    destination = np.full((rows, cols), np.nan, dtype=np.float32)

    reproject(
        source=np.ascontiguousarray(depth, dtype=np.float32),
        destination=destination,
        src_transform=transform,
        src_crs=crs,
        src_nodata=np.nan,
        dst_transform=dst_transform,
        dst_crs="EPSG:4326",
        dst_nodata=np.nan,
        resampling=Resampling.min,
    )
    return destination


def write_outputs(array: np.ndarray, grid: dict, output: Path | None) -> tuple[Path, Path]:
    target = output or bathymetry_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {key: (list(value) if isinstance(value, tuple) else value) for key, value in grid.items()}
    payload["shape"] = list(array.shape)
    payload["crs"] = "EPSG:4326"
    payload["units"] = "metres, positive down"
    payload["land_value"] = 0

    np.save(target, np.ascontiguousarray(array, dtype=np.float32))
    sidecar = target.parent / GRID_SIDECAR
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target, sidecar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="direct URL of the IBCSO V2 raster")
    source.add_argument("--file", type=Path, help="path to an already-downloaded file")
    parser.add_argument(
        "--resolution", type=float, default=DEFAULT_RESOLUTION,
        help=f"output grid step in degrees (default {DEFAULT_RESOLUTION})",
    )
    parser.add_argument("--output", type=Path, default=None,
                        help="override the destination .npy path")
    args = parser.parse_args(argv)

    if args.url:
        raise SystemExit(
            "Downloading by URL is not implemented in this build because the "
            "canonical IBCSO V2 file location is versioned by DOI and must be "
            "confirmed before use.\n"
            "1. Get the current IBCSO V2 raster from PANGAEA "
            "   (https://www.pangaea.de, search 'IBCSO v2').\n"
            "2. Download it (any HTTP client), then run:\n"
            "       python scripts/download_ibcso.py --file <downloaded file>"
        )

    source_path: Path = args.file
    if not source_path.exists():
        raise SystemExit(f"input file not found: {source_path}")

    print(f"reading {source_path} ...")
    depth, transform, crs = _load_source(source_path)
    print(f"  source shape={depth.shape} crs={crs}")

    print(f"reprojecting onto a {args.resolution} deg ROI-aligned grid ...")
    array = reproject_to_roi_grid(depth, transform, crs, args.resolution)
    grid = build_target_grid(args.resolution)
    print(f"  output shape={array.shape}")

    finite = np.isfinite(array)
    print(
        f"  {int(finite.sum())}/{array.size} cells have soundings "
        f"({finite.mean() * 100:.1f}%), min depth {float(np.nanmin(array)) if finite.any() else float('nan'):.1f} m"
    )

    npy_path, sidecar_path = write_outputs(array, grid, args.output)
    print(f"wrote {npy_path}")
    print(f"wrote {sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
