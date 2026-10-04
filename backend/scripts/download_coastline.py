"""Fetch the land polygons the map draws beneath the SIC overlay.

    python scripts/download_coastline.py
    python scripts/download_coastline.py --refresh    # ignore the local cache

Writes ``data/coastline.geojson``, which ``GET /api/coastline`` serves
verbatim and the map draws underneath the SIC overlay.

Two datasets, one clip window:

* **Natural Earth 10m land**, north of 60°S — Africa, Madagascar and the
  sub-Antarctic islands, at exactly the simplification this map has always
  drawn them at, so nothing north of 60°S moves a pixel.
* **SCAR ADD**, south of 60°S — the coastline polygons (``land``,
  ``ice shelf``, ``ice tongue``, ``rumple``) *and* the rock outcrop layer.
  ADD is what puts Maitri on land at its own coordinates: Natural Earth
  has the station in the sea, and rock outcrop is the ADD layer whose
  polygon covers it.

ADD travels over whichever of BAS's two doors is open:

1. the shapefile the catalogue links (``ramadda.data.bas.ac.uk``) — the
   preferred, complete form;
2. BAS's own ArcGIS feature service — the same published dataset, same
   DOI and same version — when ramadda is unavailable. That is a
   transport, not a different source: geometry is pulled whole by object
   id and simplified here, never server-side (the service's own
   ``maxAllowableOffset`` hands back coordinates in the wrong system).

Nothing here is generated. If a source cannot be fetched the script exits
non-zero and leaves whatever file already exists untouched, because a
coastline drawn from guesses is worse than no coastline at all and the
backend already answers 204 for this endpoint.

The clip window is the **route corridor**, not the SIC ROI: it runs from
5°E to 85°E and 78°S to 25°S, so Africa's southern tip, Madagascar and the
whole Antarctic coast are inside it. Clipping to the SIC grid instead is
what left the old file with nothing north of 48°S — a continent-shaped hole
at the top of the map. Natural Earth is clipped where the ADD data limit
is drawn (60°S), so the two datasets meet instead of overlapping.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

#: One ADD polygon is tens of megabytes; GDAL otherwise refuses to open it.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

REPO_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_BACKEND))

from app.services.field_storage import storage_root  # noqa: E402
from app.services.storage_manager import raw_permanent_dir  # noqa: E402

FILENAME = "coastline.geojson"
#: Natural Earth 10m land polygons, zipped with their .shp/.dbf/.shx/.prj.
DEFAULT_URL = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip"
#: ``lon_min, lat_min, lon_max, lat_max`` — the Cape Town → Antarctica corridor.
CLIP_BBOX = (5.0, -78.0, 85.0, -25.0)
#: Natural Earth stops where the ADD data limit is drawn, at 60°S.
NE_BBOX = (5.0, -60.0, 85.0, -25.0)
#: Simplification applied to ADD after clipping: 0.001° ≈ 111 m, and a
#: fraction of a pixel at every scale this map is used at.
SIMPLIFY_ADD_DEG = 0.001
#: Used only when the finer pass leaves the file over 10 MB.
SIMPLIFY_ADD_DEG_LARGE = 0.005
#: Natural Earth keeps the simplification the map shipped with, so the
#: northern half of the file is the geometry it draws today.
SIMPLIFY_NE_DEG = 0.05
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
SHP_NAME = "ne_10m_land.shp"
USER_AGENT = "aurora-backend/1.0"
#: Checked against the finished file before anything is written.
STATIONS = {
    "Maitri": (11.7375, -70.7658),
    "Bharati": (76.1878, -69.4064),
    "Novolazarevskaya": (11.8300, -70.8236),
}

#: SCAR ADD as published by BAS. ``url`` is the catalogue's shapefile link;
#: ``service`` is the ArcGIS feature service carrying the same dataset.
ADD_SOURCES = {
    "coastline": {
        "label": "ADD coastline",
        "stem": "add_coastline",
        "zip": "add_coastline_high_res_polygon_v7_12.shp.zip",
        "shp": "add_coastline_high_res_polygon_v7_12.shp",
        "url": (
            "https://ramadda.data.bas.ac.uk/repository/entry/get/"
            "add_coastline_high_res_polygon_v7_12.shp.zip"
            "?entryid=synth%3A13c4d2f1-8903-4d7f-8977-592121975554%3A"
            "L2FkZF9jb2FzdGxpbmVfaGlnaF9yZXNfcG9seWdvbl92N18xMi5zaHAuemlw"
        ),
        "service": (
            "https://services7.arcgis.com/tPxy1hrFDhJfZ0Mf/arcgis/rest/services/"
            "High_resolution_vector_polygons_of_the_Antarctic_coastline/FeatureServer/1"
        ),
        "variant": "v7.12, high resolution",
        "service_variant": "v7.12, high resolution",
    },
    "rock_outcrop": {
        "label": "ADD rock outcrop",
        "stem": "add_rock_outcrop",
        "zip": "add_rock_outcrop_high_res_polygon_v7_11.shp.zip",
        "shp": "add_rock_outcrop_high_res_polygon_v7_11.shp",
        "url": (
            "https://ramadda.data.bas.ac.uk/repository/entry/get/"
            "add_rock_outcrop_high_res_polygon_v7_11.shp.zip"
            "?entryid=synth%3A815525ca-cefe-4fbf-9224-3ee784e7de4e%3A"
            "L2FkZF9yb2NrX291dGNyb3BfaGlnaF9yZXNfcG9seWdvbl92N18xMS5zaHAuemlw"
        ),
        "service": (
            "https://services7.arcgis.com/tPxy1hrFDhJfZ0Mf/arcgis/rest/services/"
            "Medium_resolution_vector_polygons_of_Antarctic_rock_outcrop/FeatureServer/0"
        ),
        "variant": "v7.11, high resolution",
        "service_variant": "v7.11, medium resolution",
    },
}


def cache_dir() -> Path:
    """Long-lived raw artefacts: never cleaned, so a re-run is not a re-fetch."""
    return raw_permanent_dir() / "coastline"


def _get_json(url: str, params: dict[str, str], timeout: float, attempts: int = 3) -> dict:
    import requests

    last = "unknown error"
    for attempt in range(attempts):
        try:
            response = requests.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("error"):
                    raise RuntimeError(f"{url}: {payload['error']}")
                return payload
            last = f"HTTP {response.status_code}"
            if response.status_code in (400, 401, 403, 404):
                break
        except (requests.RequestException, ValueError) as exc:
            last = str(exc)
        time.sleep(2**attempt)
    raise RuntimeError(f"{url}: {last}")


def download_ne(url: str, dest: Path, timeout: float) -> Path:
    """Natural Earth zip (downloaded once, then cached) → extracted .shp."""
    import requests

    if not dest.is_file():
        with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            part = dest.parent / (dest.name + ".part")
            with part.open("wb") as handle:
                for chunk in response.iter_content(1 << 20):
                    handle.write(chunk)
            part.replace(dest)

    workdir = Path(tempfile.mkdtemp(prefix="aurora-coastline-"))
    with zipfile.ZipFile(dest) as zip_file:
        zip_file.extractall(workdir)
    shp = workdir / SHP_NAME
    if not shp.is_file():
        raise FileNotFoundError(f"{SHP_NAME} not found inside {dest.name}")
    return shp


def try_add_shapefile(spec: dict, dest_zip: Path, timeout: float) -> Path | None:
    """Pull the catalogue's own zip. ``None`` when BAS is not serving it."""
    if not dest_zip.is_file():
        print(f"  {spec['label']}: trying {dest_zip.name} from ramadda")
        try:
            import requests

            with requests.get(
                spec["url"],
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
                stream=True,
            ) as response:
                if response.status_code != 200:
                    print(f"  {spec['label']}: ramadda unavailable (HTTP {response.status_code})")
                    return None
                part = dest_zip.parent / (dest_zip.name + ".part")
                with part.open("wb") as handle:
                    for chunk in response.iter_content(1 << 20):
                        handle.write(chunk)
                part.replace(dest_zip)
        except requests.RequestException as exc:
            print(f"  {spec['label']}: ramadda unavailable ({exc})")
            return None
        print(f"  {spec['label']}: downloaded {dest_zip.stat().st_size / 1e6:.1f} MB")

    workdir = dest_zip.parent / dest_zip.stem
    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip) as zip_file:
        zip_file.extractall(workdir)
    shp = workdir / spec["shp"]
    if not shp.is_file():
        candidates = sorted(workdir.glob("*.shp"))
        if not candidates:
            raise FileNotFoundError(f"{spec['shp']} not found inside {dest_zip.name}")
        shp = candidates[0]
    return shp


def _arcgis_envelope(bbox: tuple[float, float, float, float]) -> str:
    west, south, east, north = bbox
    return json.dumps(
        {
            "xmin": west,
            "ymin": south,
            "xmax": east,
            "ymax": north,
            "spatialReference": {"wkid": 4326},
        },
        separators=(",", ":"),
    )


def _arcgis_srid(service: str, timeout: float) -> int:
    meta = _get_json(service, {"f": "json"}, timeout, attempts=2)
    wkid = (meta.get("spatialReference") or {}).get("wkid")
    if not wkid:
        raise RuntimeError(f"{service}: no spatial reference in layer metadata")
    return int(wkid)


def _arcgis_ids(service: str, bbox: tuple[float, float, float, float], timeout: float) -> list[int]:
    data = _get_json(
        f"{service}/query",
        {
            "where": "1=1",
            "geometry": _arcgis_envelope(bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "returnIdsOnly": "true",
            "f": "json",
        },
        timeout,
    )
    return [int(oid) for oid in data.get("objectIds") or []]


def _fetch_batch(
    service: str,
    object_ids: list[int],
    srid: int,
    dest: Path,
    timeout: float,
) -> Path:
    """One batch of object ids → one GeoJSON page on disk (atomic)."""
    if dest.is_file():
        return dest
    base = {
        "objectIds": ",".join(str(oid) for oid in object_ids),
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": str(srid),
        "f": "geojson",
    }
    try:
        payload = _get_json(f"{service}/query", base, timeout, attempts=3)
    except RuntimeError:
        # Some layers refuse integer precision; round coordinates locally instead.
        payload = _get_json(
            f"{service}/query", {**base, "geometryPrecision": "0"}, timeout, attempts=3
        )
    features = payload.get("features") or []
    if len(features) != len(object_ids):
        raise RuntimeError(
            f"{dest.name}: asked for {len(object_ids)} features, got {len(features)}"
        )
    part = dest.parent / (dest.name + ".part")
    part.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    part.replace(dest)
    return dest


def fetch_add_arcgis(
    spec: dict,
    dest_dir: Path,
    timeout: float,
    workers: int,
    batch: int,
    refresh: bool,
) -> list[Path]:
    """Every ADD feature in the corridor, one resumable page file per batch."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    srid = _arcgis_srid(spec["service"], timeout)
    object_ids = _arcgis_ids(spec["service"], CLIP_BBOX, timeout)
    if not object_ids:
        raise RuntimeError(f"{spec['label']}: feature service returned no features")

    dest_dir.mkdir(parents=True, exist_ok=True)
    if refresh:
        for stale in dest_dir.glob(f"{spec['stem']}_b*.geojson"):
            stale.unlink()

    batches = [object_ids[i : i + batch] for i in range(0, len(object_ids), batch)]
    pages = [dest_dir / f"{spec['stem']}_b{index:04d}.geojson" for index in range(len(batches))]
    pending = [
        (ids, page)
        for ids, page in zip(batches, pages)
        if not page.is_file()
    ]

    print(
        f"  {spec['label']}: {len(object_ids)} features in the corridor, "
        f"{len(batches)} batches ({len(pending)} to fetch, EPSG:{srid})"
    )
    if pending:
        started = time.time()
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(_fetch_batch, spec["service"], ids, srid, page, timeout): page
                for ids, page in pending
            }
            done = 0
            for future in as_completed(futures):
                page = futures[future]
                future.result()  # a missing batch is not shippable: let it raise
                done += 1
                print(
                    f"  [{done}/{len(pending)}] {page.name} "
                    f"({page.stat().st_size / 1e6:.1f} MB, {time.time() - started:.0f}s)"
                )
    return pages


def _read_pages(paths: list[Path]):
    import geopandas as gpd
    import pandas as pd

    frames = [gpd.read_file(path) for path in paths]
    merged = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=frames[0].crs,
    )
    merged = merged[~merged.geometry.isna() & ~merged.geometry.is_empty]
    if "FID" in merged.columns:
        merged = merged.drop_duplicates(subset=["FID"])
    return merged.reset_index(drop=True)


def _clip_to_corridor(gdf, bbox: tuple[float, float, float, float]):
    from shapely.geometry import box

    west, south, east, north = bbox
    clipped = gdf.clip(box(west, south, east, north))
    return clipped[~clipped.geometry.isna() & ~clipped.geometry.is_empty]


def load_add_source(
    name: str,
    refresh: bool,
    timeout: float,
    workers: int,
    batch: int,
):
    """``(corridor geometry in EPSG:4326, note of how it arrived)``.

    The corridor geometry is cached under ``raw_permanent``, so re-running
    the script to change simplification never costs another download.
    """
    import geopandas as gpd

    spec = ADD_SOURCES[name]
    dest_dir = cache_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    roi_path = dest_dir / f"{spec['stem']}_roi.geojson"
    meta_path = dest_dir / f"{spec['stem']}.meta.json"

    if refresh:
        roi_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    if roi_path.is_file():
        variant = spec["variant"]
        if meta_path.is_file():
            variant = json.loads(meta_path.read_text(encoding="utf-8")).get("variant", variant)
        print(f"  {spec['label']}: using cached corridor geometry ({variant})")
        return gpd.read_file(roi_path), variant

    shp = try_add_shapefile(spec, dest_dir / spec["zip"], timeout)
    if shp is not None:
        gdf = gpd.read_file(shp)
        shutil.rmtree(shp.parent, ignore_errors=True)
        variant = spec["variant"]
    else:
        pages = fetch_add_arcgis(spec, dest_dir, timeout, workers, batch, refresh)
        gdf = _read_pages(pages)
        variant = spec["service_variant"]

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    corridor = _clip_to_corridor(gdf.to_crs(4326), CLIP_BBOX)
    if corridor.empty:
        raise RuntimeError(f"{spec['label']}: clip produced no geometry")

    corridor.to_file(roi_path, driver="GeoJSON")
    meta_path.write_text(
        json.dumps(
            {
                "variant": variant,
                "features": int(len(corridor)),
            }
        ),
        encoding="utf-8",
    )
    print(f"  {spec['label']}: {len(corridor)} corridor features cached ({variant})")
    return corridor, variant


def _features(gdf, source: str, simplify_deg: float | None) -> list[dict]:
    from shapely.geometry import mapping

    has_surface = "surface" in gdf.columns
    features: list[dict] = []
    for _, row in gdf.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue
        if simplify_deg:
            geometry = geometry.simplify(simplify_deg, preserve_topology=True)
            if geometry is None or geometry.is_empty:
                continue
        properties: dict[str, str | None] = {
            "id": "",
            "name": "Land",
            "source": source,
            "surface": None,
        }
        if has_surface:
            surface = row.get("surface")
            if surface is not None and str(surface).strip():
                properties["surface"] = str(surface).strip()
        features.append(
            {
                "type": "Feature",
                "properties": properties,  # type: ignore[arg-type]
                "geometry": mapping(geometry),
            }
        )
    for index, feature in enumerate(features):
        feature["properties"]["id"] = f"land-{index}"
        feature["properties"] = {
            key: value for key, value in feature["properties"].items() if value is not None
        }
    return features


def _inspect(features: list[dict]) -> dict:
    """Stations, bounds and vertex count of a candidate file."""
    import shapely
    from shapely.geometry import shape

    geoms = [shape(feature["geometry"]) for feature in features]
    tree = shapely.STRtree(geoms)
    stations = {
        name: bool(tree.query(shapely.Point(lon, lat), predicate="intersects").size)
        for name, (lon, lat) in STATIONS.items()
    }
    bounds = shapely.total_bounds(geoms) if geoms else [0, 0, 0, 0]
    vertices = int(sum(shapely.get_num_coordinates(geom) for geom in geoms))
    return {
        "stations": stations,
        "bbox": tuple(float(value) for value in bounds),
        "vertices": vertices,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the coastline GeoJSON")
    parser.add_argument("--url", default=DEFAULT_URL, help="Natural Earth zip URL")
    parser.add_argument("--out", default=None, help=f"output path (default data/{FILENAME})")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--workers", type=int, default=4, help="parallel feature-service batches")
    parser.add_argument("--batch", type=int, default=150, help="object ids per feature-service call")
    parser.add_argument("--refresh", action="store_true", help="discard cached ADD geometry")
    args = parser.parse_args(argv)

    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    shp: Path | None = None

    try:
        print("Natural Earth land (north of 60°S)")
        shp = download_ne(args.url, cache / "ne_10m_land.zip", args.timeout)
        import geopandas as gpd

        ne_clip = _clip_to_corridor(gpd.read_file(shp), NE_BBOX)

        print("SCAR ADD (south of 60°S)")
        coast, coast_variant = load_add_source(
            "coastline", args.refresh, args.timeout, args.workers, args.batch
        )
        rock, rock_variant = load_add_source(
            "rock_outcrop", args.refresh, args.timeout, args.workers, args.batch
        )
    except Exception as exc:  # noqa: BLE001 — report, then leave the old file alone
        print(f"Download/build failed: {exc}", file=sys.stderr)
        print("No coastline written; /api/coastline keeps its current answer.", file=sys.stderr)
        return 1
    finally:
        if shp is not None:
            shutil.rmtree(shp.parent, ignore_errors=True)

    chosen = None
    for simplify_deg in (SIMPLIFY_ADD_DEG, None):
        label = "none" if simplify_deg is None else f"{simplify_deg}°"
        features = (
            _features(ne_clip, "NE", SIMPLIFY_NE_DEG)
            + _features(coast, "ADD", simplify_deg)
            + _features(rock, "ADD", simplify_deg)
        )
        if not features:
            print("Clip produced no features; nothing written.", file=sys.stderr)
            return 1
        report = _inspect(features)
        print(
            f"  pass ADD simplification {label}: {len(features)} features, "
            + ", ".join(
                f"{name}={'inside' if ok else 'OUTSIDE'}"
                for name, ok in report["stations"].items()
            )
        )
        if all(report["stations"].values()):
            chosen = (features, report, simplify_deg)
            break

    if chosen is None:
        print(
            "A station is outside the drawn land at every simplification; nothing written.",
            file=sys.stderr,
        )
        return 1

    features, report, simplify_deg = chosen
    payload = {"type": "FeatureCollection", "features": features}
    path = Path(args.out) if args.out else storage_root() / FILENAME
    encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    if len(encoded) > MAX_OUTPUT_BYTES and simplify_deg is not None:
        coarse = (
            _features(ne_clip, "NE", SIMPLIFY_NE_DEG)
            + _features(coast, "ADD", SIMPLIFY_ADD_DEG_LARGE)
            + _features(rock, "ADD", SIMPLIFY_ADD_DEG_LARGE)
        )
        coarse_report = _inspect(coarse)
        print(
            f"  {len(encoded) / 1e6:.1f} MB over the "
            f"{MAX_OUTPUT_BYTES / 1e6:.0f} MB line: retrying at "
            f"{SIMPLIFY_ADD_DEG_LARGE}°"
        )
        if all(coarse_report["stations"].values()):
            features, report = coarse, coarse_report
            simplify_deg = SIMPLIFY_ADD_DEG_LARGE
            payload = {"type": "FeatureCollection", "features": features}
            encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    if len(encoded) > MAX_OUTPUT_BYTES:
        print(
            f"warning: output is {len(encoded) / 1e6:.1f} MB, over the "
            f"{MAX_OUTPUT_BYTES / 1e6:.0f} MB line at {simplify_deg}°",
            file=sys.stderr,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.parent / (path.name + ".part")
    part.write_bytes(encoded)
    part.replace(path)

    west, south, east, north = report["bbox"]
    print(f"ADD coastline:  {coast_variant}")
    print(f"ADD rock outcrop: {rock_variant}")
    print(f"features: {len(features)} ({report['vertices']} vertices)")
    print(f"bbox:     [{west:.4f}, {south:.4f}, {east:.4f}, {north:.4f}]")
    print(f"stations: " + ", ".join(f"{name} inside" for name in STATIONS))
    print(f"simplify: NE {SIMPLIFY_NE_DEG}°, ADD {simplify_deg if simplify_deg else 'none'}")
    print(f"output:   {path} ({len(encoded) / 1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — report and exit non-zero
        print(f"Coastline fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
