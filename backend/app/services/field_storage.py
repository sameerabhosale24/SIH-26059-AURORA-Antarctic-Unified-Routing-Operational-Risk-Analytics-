"""On-disk store for regridded fields.

Layout::

    {STORAGE_ROOT}/fields/{source}/YYYY-MM-DD.npy
    {STORAGE_ROOT}/fields/bathymetry.npy      # single static file

Every file is one ``float32`` array on the ROI grid (``[101, 361]``) or a
channel stack (``[C, 101, 361]``). Missing data is NaN in the file and
missing files are ``None`` — this module never invents a field.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from app.config import get_settings

logger = logging.getLogger("aurora.field_storage")

BATHYMETRY_FILE = "bathymetry.npy"


def storage_root() -> Path:
    return Path(get_settings().STORAGE_ROOT)


def fields_root() -> Path:
    return storage_root() / "fields"


def source_dir(source: str) -> Path:
    return fields_root() / source


def field_path(source: str, day: date) -> Path:
    return source_dir(source) / f"{day.isoformat()}.npy"


def bathymetry_path() -> Path:
    return fields_root() / BATHYMETRY_FILE


def write_field(source: str, day: date, array: np.ndarray) -> Path:
    """Persist ``array`` for ``day``. Creates the directory on first write.

    The array is stored as float32 exactly as given: no normalisation, no
    NaN replacement, no silent reshaping.
    """
    if not isinstance(array, np.ndarray):
        raise TypeError(f"write_field expects an ndarray, got {type(array)!r}")
    path = field_path(source, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = np.ascontiguousarray(array, dtype=np.float32)
    tmp = path.with_suffix(".npy.tmp")
    # np.save appends ".npy" to any filename that lacks it, so pass a stream:
    # otherwise the temp file lands at "<name>.npy.tmp.npy" and the replace
    # below fails with FileNotFoundError on the first write of a day.
    with open(tmp, "wb") as handle:
        np.save(handle, payload)
    tmp.replace(path)
    logger.info("wrote field %s/%s shape=%s", source, day.isoformat(), payload.shape)
    return path


def read_field(source: str, day: date) -> np.ndarray | None:
    """Return the field for ``day``, or ``None`` when there is no such file.

    A corrupt file is logged and treated as absent rather than raising: the
    assembly layer already knows how to fall back to persistence, and a
    half-written file must not take the daily cycle down.
    """
    path = field_path(source, day)
    if not path.exists():
        return None
    try:
        return np.load(path)
    except Exception:  # noqa: BLE001 — a bad file is "no data", not a crash
        logger.exception("unreadable field file %s; treating as missing", path)
        return None


def list_available_dates(source: str, start: date | None = None,
                         end: date | None = None) -> list[date]:
    """Sorted dates for which ``source`` has a file.

    ``start``/``end`` bound the scan so a lookup never walks years of files
    when only a five-day window is needed.
    """
    directory = source_dir(source)
    if not directory.is_dir():
        return []

    found: list[date] = []
    for entry in directory.iterdir():
        if not entry.is_file() or entry.suffix != ".npy":
            continue
        try:
            day = date.fromisoformat(entry.stem)
        except ValueError:
            logger.debug("ignoring non-date file in %s: %s", source, entry.name)
            continue
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            continue
        found.append(day)
    return sorted(found)


def latest_available_date(source: str, on_or_before: date) -> date | None:
    """Newest stored date that is not after ``on_or_before``.

    This is the persistence lookup: "use the most recent prior observation".
    """
    candidates = list_available_dates(source, start=None, end=on_or_before)
    return candidates[-1] if candidates else None


def days_back_available(source: str, on_or_before: date, max_days: int) -> list[date]:
    """Dates in ``[on_or_before - max_days, on_or_before]``, newest first."""
    earliest = on_or_before - timedelta(days=max_days)
    return sorted(list_available_dates(source, start=earliest, end=on_or_before),
                  reverse=True)


def describe(source: str) -> dict:
    """Small summary for health output."""
    dates = list_available_dates(source)
    return {
        "source": source,
        "files": len(dates),
        "first": dates[0].isoformat() if dates else None,
        "last": dates[-1].isoformat() if dates else None,
    }


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()
