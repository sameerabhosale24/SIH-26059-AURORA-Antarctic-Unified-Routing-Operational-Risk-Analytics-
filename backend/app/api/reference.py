"""Reference data the map needs before anything else has loaded.

ROI, stations, coastline and the ENC manifest are the four answers the
console cannot draw a single pixel without, and none of them depends on a
sensor, a fetch or an operator's identity — which is why they are the four
endpoints left open. An unauthenticated client that can see the map
outline has learned nothing it could not learn from the horizon.

Every one of them treats "not published" as a first-class answer: no
stations file means ``[]``, no coastline means 204, no ENC cells means
``{"cells": [], "version": n}``. None of them substitutes a placeholder,
because a synthetic coastline on a navigation console is worse than a
blank one.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse

from app.config import get_settings
from app.schemas.common import EncCellOut, EncManifestOut, RoiOut, StationOut
from app.services import version_service
from app.services.field_storage import storage_root

logger = logging.getLogger("aurora.reference")

router = APIRouter(prefix="/api", tags=["reference"])

#: Served from ``data/`` when present; each file is optional.
STATIONS_FILENAME = "stations.json"
COASTLINE_FILENAME = "coastline.geojson"


def _read_json(path: Path) -> Any | None:
    """Parse a static JSON asset, or ``None`` if it is missing or broken.

    A corrupt asset degrades to "no data" rather than to a 500: the console
    renders an empty layer and the log says which file failed.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.exception("could not read %s", path)
        return None


def enc_directory() -> Path:
    return storage_root() / "enc"


def _enc_cells() -> list[EncCellOut]:
    """Every ``.000`` cell on disk.

    ``bounds`` is left empty on purpose. A cell's footprint is only known
    after the S-57 file has been parsed, which the chart layer does itself;
    reporting a guessed extent here would be a number nobody measured.
    """
    directory = enc_directory()
    if not directory.is_dir():
        return []
    cells: list[EncCellOut] = []
    for path in sorted(directory.glob("*.000")):
        try:
            stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:  # pragma: no cover - file vanished mid-scan
            logger.exception("could not stat %s", path)
            continue
        cells.append(
            EncCellOut(
                id=path.stem,
                name=path.stem,
                url=f"/api/enc/{path.name}",
                bounds=[],
                updated_at=stamp.isoformat(),
            )
        )
    return cells


@router.get("/roi", response_model=RoiOut, tags=["reference"])
def roi() -> RoiOut:
    """The configured region of interest, straight from settings."""
    settings = get_settings()
    return RoiOut(
        lon_min=settings.ROI_LON_MIN,
        lat_min=settings.ROI_LAT_MIN,
        lon_max=settings.ROI_LON_MAX,
        lat_max=settings.ROI_LAT_MAX,
    )


@router.get("/stations", response_model=list[StationOut], tags=["reference"])
def stations() -> list[StationOut]:
    """Station metadata, or ``[]`` when none has been published."""
    raw = _read_json(storage_root() / STATIONS_FILENAME)
    if not isinstance(raw, list):
        return []

    parsed: list[StationOut] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            parsed.append(
                StationOut(
                    id=str(entry["id"]),
                    name=str(entry.get("name") or entry["id"]),
                    country=str(entry.get("country") or ""),
                    lat=float(entry["lat"]),
                    lon=float(entry["lon"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            # One malformed record must not blank the whole layer.
            logger.warning("skipping malformed station record: %r", entry)
    return parsed


@router.get("/coastline", response_model=None, tags=["reference"])
def coastline() -> Response | dict:
    """Coastline GeoJSON, or 204 when the backend has not published one.

    204 rather than an empty FeatureCollection: the client distinguishes
    "has no coastline yet" from "the coastline is empty", and only the
    first of those is true here.
    """
    raw = _read_json(storage_root() / COASTLINE_FILENAME)
    if raw is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return raw


@router.get("/enc/manifest", response_model=EncManifestOut, tags=["reference"])
def enc_manifest() -> EncManifestOut:
    """Available S-57 cells. Empty when the deployment ships no charts."""
    row = version_service.get("enc")
    return EncManifestOut(
        cells=_enc_cells(),
        version=int(row.version) if row is not None else 0,
    )


@router.get("/enc/{filename}", tags=["reference"])
def enc_file(filename: str) -> FileResponse:
    """Serve one raw S-57 cell.

    The name is resolved against the ENC directory and then re-checked, so
    a traversal attempt cannot read outside it — ``Path`` normalises
    ``..`` before the containment test, and the suffix requirement rejects
    anything that is not a chart file to begin with.
    """
    if "/" in filename or "\\" in filename or not filename.endswith(".000"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ENC cell not found")

    directory = enc_directory().resolve()
    path = (directory / filename).resolve()
    if directory not in path.parents or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ENC cell not found")
    return FileResponse(path, media_type="application/octet-stream")
