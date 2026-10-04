"""``GET /api/sic/frames`` and the PNG endpoint behind its URLs.

The SIC product is published as pre-rendered rasters: three horizons per
issue, rendered once each. The manifest this endpoint returns carries the
single presentation AURORA renders — ``day`` — and drops any entry that
does not, so a manifest written before the console settled on one
presentation still publishes cleanly.

A frame is listed only when its PNG is actually on disk. A manifest that
names a file which has since been cleaned up is a manifest that is wrong,
and publishing it would put a broken image on the map instead of nothing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.schemas.telemetry import SicFrameMeta, SicFramesResponse
from app.services import display_pipeline

logger = logging.getLogger("aurora.sic")

router = APIRouter(prefix="/api", tags=["sic"])

#: Only this mode is published; see the module docstring.
PUBLISHED_MODE = "day"
#: Issues beyond this age are still on disk but no longer offered.
MAX_ISSUES = 14


def _manifest_days() -> list[date]:
    """Issue dates present on disk, newest first."""
    root = display_pipeline.frames_root()
    if not root.is_dir():
        return []
    days: list[date] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            days.append(date.fromisoformat(path.name))
        except ValueError:
            continue
    return sorted(days, reverse=True)[:MAX_ISSUES]


def _png_exists(url: str) -> bool:
    """Whether ``url`` names a file that is really in the issue directory.

    ``url`` is one this module generated (:func:`display_pipeline.frame_url`),
    so it is already relative and already trusted; the check is against the
    frames root, never against the request.
    """
    prefix, _, filename = url.rpartition("/")
    day_part = prefix.rpartition("/")[2]
    if not day_part or not filename:
        return False
    try:
        day = date.fromisoformat(day_part)
    except ValueError:
        return False
    return (display_pipeline.frames_dir(day) / filename).is_file()


def build_manifest() -> SicFramesResponse:
    """Every published frame, newest issue first."""
    frames: list[SicFrameMeta] = []
    newest_version = 0

    for day in _manifest_days():
        manifest = display_pipeline.read_manifest(day)
        if manifest is None:
            continue
        try:
            newest_version = max(newest_version, int(manifest.get("version") or 0))
        except (TypeError, ValueError):
            pass

        for entry in manifest.get("frames") or []:
            if not isinstance(entry, dict) or entry.get("mode") != PUBLISHED_MODE:
                continue
            frame_url = entry.get("median_url")
            if not isinstance(frame_url, str) or not _png_exists(frame_url):
                continue

            interval_url = entry.get("uncertainty_url")
            if not isinstance(interval_url, str) or not _png_exists(interval_url):
                interval_url = None

            extent = entry.get("extent_lcc")
            if not isinstance(extent, list) or len(extent) != 4:
                logger.warning("frame %s has no usable extent; skipping", frame_url)
                continue

            try:
                horizon = int(entry["horizon"])
            except (KeyError, TypeError, ValueError):
                continue

            frames.append(
                SicFrameMeta(
                    date=day.isoformat(),
                    horizon=horizon,
                    version=newest_version,
                    frame_url=frame_url,
                    frame_extent=[float(value) for value in extent],
                    interval_url=interval_url,
                )
            )

    return SicFramesResponse(version=newest_version, frames=frames)


@router.get("/sic/frames", response_model=SicFramesResponse, tags=["sic"])
def sic_frames() -> SicFramesResponse:
    """The frame manifest. Empty when no forecast has been rendered yet."""
    return build_manifest()


@router.get("/sic/frame/{day}/{filename}", tags=["sic"])
def sic_frame(day: str, filename: str) -> FileResponse:
    """One rendered PNG.

    The path is rebuilt from a validated date and a validated filename and
    then required to sit inside the frames directory, so neither ``..`` nor
    an absolute path can escape it. A malformed day or a non-PNG name is a
    404, never a parse error.
    """
    if "/" in filename or "\\" in filename or not filename.endswith(".png"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    try:
        issue_day = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found") from None

    root = display_pipeline.frames_root().resolve()
    path = (display_pipeline.frames_dir(issue_day) / filename).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")

    # The URL carries no revision, so the browser must revalidate rather than
    # keep serving a frame the next run has replaced.
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )
