"""Local disk: what it is holding, and throwing away what is no longer true.

Two very different jobs live here, and conflating them would be dangerous:

* **Retention** deletes forecasts whose horizon has passed. An SIC frame
  issued for D+1 is meaningless a month later, and keeping it would let a
  stale raster be mistaken for a current one. The whole day directory goes
  together — PNGs, manifest and the raw arrays — so no part of an issue can
  survive its own metadata.
* **Scratch** deletes ``raw_temp``, which by construction only ever holds
  downloads that never finished. Nothing in it can be the answer to any
  question, so it is cleared at the *start* of a fetch rather than at the
  end: an interrupted run must not leave half a file behind for the next
  one to find.

``report_disk_usage`` never deletes. It exists so ``GET /api/health`` can
say "frames are 600 MB, over the 500 MB warning line" instead of letting
the operator discover it when the disk fills.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.services.display_pipeline import arrays_root, frames_root
from app.services.field_storage import storage_root

logger = logging.getLogger("aurora.storage")

#: Scratch space for in-flight downloads. Everything in it is disposable.
RAW_TEMP_DIRNAME = "raw_temp"
#: Long-lived raw artefacts (the IBCSO GeoTIFF). Never cleaned automatically.
RAW_PERMANENT_DIRNAME = "raw_permanent"


def raw_temp_dir() -> Path:
    return storage_root() / RAW_TEMP_DIRNAME


def raw_permanent_dir() -> Path:
    return storage_root() / RAW_PERMANENT_DIRNAME


def _tree_size(path: Path) -> int:
    """Bytes under ``path``, or 0 when it does not exist."""
    if not path.is_dir():
        return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:  # pragma: no cover - removed while walking
            continue
    return total


def _mb(size_bytes: int) -> float:
    return round(size_bytes / (1024 * 1024), 2)


def _usage(path: Path, warn_mb: int | None = None) -> dict:
    size = _tree_size(path)
    usage = {"path": str(path), "exists": path.is_dir(), "bytes": size, "mb": _mb(size)}
    if warn_mb is not None:
        usage["warn_mb"] = int(warn_mb)
        usage["over_warn"] = size > int(warn_mb) * 1024 * 1024
    return usage


def report_disk_usage() -> dict:
    """Sizes of every storage subtree, with the configured warning lines.

    Purely a read. The warning flags are what ``GET /api/health`` surfaces
    so a deployment that is quietly filling up says so before it runs out.
    """
    settings = get_settings()
    subtrees = {
        "sic_frames": _usage(frames_root(), settings.WARN_SIC_FRAMES_MB),
        "sic_arrays": _usage(arrays_root()),
        "fields": _usage(storage_root() / "fields", settings.WARN_FIELDS_MB),
        "enc": _usage(storage_root() / "enc"),
        "raw_temp": _usage(raw_temp_dir()),
        "raw_permanent": _usage(raw_permanent_dir()),
    }
    total = sum(entry["bytes"] for entry in subtrees.values())
    over = [name for name, entry in subtrees.items() if entry.get("over_warn")]
    return {
        "subtrees": subtrees,
        "total_bytes": total,
        "total_mb": _mb(total),
        "over_warn": sorted(over),
    }


def _issue_day(path: Path) -> datetime | None:
    """Midnight UTC of the issue date encoded in a directory name, if any."""
    try:
        day = datetime.strptime(path.name, "%Y-%m-%d")
    except ValueError:
        return None
    return day.replace(tzinfo=timezone.utc)


def _delete_before(root: Path, cutoff: datetime) -> tuple[int, int]:
    """Remove issue directories older than ``cutoff``.

    Returns ``(directories removed, bytes freed)``. A directory whose name
    is not a date is left alone — it was not written by the display
    pipeline, so nothing here knows whether it is safe to delete.
    """
    if not root.is_dir():
        return 0, 0

    removed = 0
    freed = 0
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        day = _issue_day(entry)
        if day is None or day >= cutoff:
            continue
        size = _tree_size(entry)
        try:
            shutil.rmtree(entry)
        except OSError:  # pragma: no cover - permission or in-flight write
            logger.exception("could not remove %s", entry)
            continue
        removed += 1
        freed += size
    return removed, freed


def cleanup_sic_frames(retention_days: int | None = None) -> dict:
    """Delete forecast issues older than the retention window.

    Frames and their raw arrays are deleted together so the two never
    disagree about which issues exist — a ``manifest.json`` describing PNGs
    that a partial cleanup removed would put a broken image on the map.
    """
    settings = get_settings()
    days = int(settings.SIC_FRAMES_RETENTION_DAYS if retention_days is None else retention_days)
    days = max(1, days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    frame_dirs, frame_bytes = _delete_before(frames_root(), cutoff)
    array_dirs, array_bytes = _delete_before(arrays_root(), cutoff)

    result = {
        "retention_days": days,
        "cutoff": cutoff.date().isoformat(),
        "frames_removed": frame_dirs,
        "arrays_removed": array_dirs,
        "freed_bytes": frame_bytes + array_bytes,
    }
    if frame_dirs or array_dirs:
        logger.info(
            "retention: removed %d frame day(s) and %d array day(s), freed %.1f MB",
            frame_dirs, array_dirs, _mb(result["freed_bytes"]),
        )
    return result


def cleanup_raw_temp() -> dict:
    """Delete everything in the scratch download directory.

    Safe by construction: ``raw_temp`` only ever holds downloads that were
    interrupted, so there is no file in it worth keeping.
    """
    root = raw_temp_dir()
    if not root.is_dir():
        return {"removed": 0, "freed_bytes": 0, "path": str(root)}

    freed = _tree_size(root)
    removed = 0
    for entry in list(root.iterdir()):
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError:  # pragma: no cover
            logger.exception("could not remove %s", entry)
            continue
        removed += 1
    return {"removed": removed, "freed_bytes": freed, "path": str(root)}


def ensure_raw_temp_clean() -> dict:
    """Clear scratch space at the start of a fetch. Never raises.

    Called before the first download of every cycle rather than after the
    last: a fetch that died halfway must not leave a truncated file for the
    next run to treat as complete, and clearing at the start means the
    window where a stale file could be read is as small as it can be.
    """
    try:
        result = cleanup_raw_temp()
    except Exception:  # noqa: BLE001 — a cleanup failure must not stop a fetch
        logger.exception("raw_temp cleanup failed; fetch continues")
        return {"removed": 0, "freed_bytes": 0, "error": True}
    if result["removed"]:
        logger.info(
            "raw_temp cleared before fetch: %d entr(ies), %.1f MB",
            result["removed"], _mb(result["freed_bytes"]),
        )
    return result
