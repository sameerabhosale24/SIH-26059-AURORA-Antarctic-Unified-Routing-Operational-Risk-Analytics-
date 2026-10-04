"""Import the 2026 held-out test set into AURORA's SIC display tree.

The forecaster has never run here, so the frames on the map came from a
synthetic placeholder written to exercise the display pipeline. This script
replaces them with real forecaster output: the predictions the sic repo
produced on its 2026 test set, read from that repo's cache (read-only) and
rendered through the normal display pipeline so the PNGs, the arrays and the
manifest are exactly what a live cycle would have written.

    python scripts/import_2026_test_frames.py \
        --start-date 2026-01-15 --end-date 2026-01-21 --force

Source layout (sic repo ``backend/cache``)::

    ensemble_2026.npy        [N, 3, 3, 101, 361]  lower/mean/upper per horizon
    true_2026.npy            [N, 3, 101, 361]     observed SIC
    uncertainty_2026.npy     [N, 3, 101, 361]     ensemble spread (1 sigma)
    confidence_class_2026.npy[N, 3, 101, 361]     uint8 class per cell
    dates_2026.npy           [N]                  datetime64 issue dates
    valid_mask.npy           [101, 361]           cells the model may speak for

A 4-D ``ensemble_2026.npy`` (no quantile axis) is accepted too; the mean
plane is then the array itself. Nothing is written outside AURORA's own
``data/sic_frames`` and ``data/sic_arrays`` trees plus the ``data_version``
ledger row for ``sic``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
#: The sic repo lives next to AURORA in this workspace; override with
#: ``--source-dir`` on any other layout.
DEFAULT_SOURCE_DIR = REPO_ROOT.parent / "sic" / "backend" / "cache"

#: Ledger revision the import publishes. High enough that any existing
#: manifest version is superseded, so the version poller sees a change and
#: refetches the frame manifest.
DATA_VERSION = 9001
DATA_VERSION_NOTES = "2026 test set import"

ENSEMBLE_FILE = "ensemble_2026.npy"
TRUE_FILE = "true_2026.npy"
UNCERTAINTY_FILE = "uncertainty_2026.npy"
CONFIDENCE_FILE = "confidence_class_2026.npy"
DATES_FILE = "dates_2026.npy"
VALID_MASK_FILE = "valid_mask.npy"

SOURCE_FILES = (
    ENSEMBLE_FILE,
    TRUE_FILE,
    UNCERTAINTY_FILE,
    CONFIDENCE_FILE,
    DATES_FILE,
    VALID_MASK_FILE,
)

HORIZONS = (1, 2, 3)
#: What the manifest calls the rendered field per horizon. ``diff`` is also
#: written by the pipeline when an observation exists; it is not one of the
#: files the importer requires to consider a date complete.
REQUIRED_FIELDS = ("median", "actual", "uncertainty")

ROI_SHAPE = (101, 361)
PROVENANCE_NOTE = "Real forecaster output on the 2026 held-out test set."


class SourceError(RuntimeError):
    """A required source file is missing, unreadable or the wrong shape."""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import 2026 test-set SIC frames into data/sic_frames.",
    )
    parser.add_argument("--start-date", default="2026-01-15", help="first issue date, inclusive")
    parser.add_argument("--end-date", default="2026-01-21", help="last issue date, inclusive")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite date directories that already exist",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"cache directory holding the six .npy files (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "--no-version-bump",
        action="store_true",
        help="render frames but leave the data_version ledger untouched",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------
def load_source(source_dir: Path) -> dict:
    """Open the six cache arrays, validating what each one must look like.

    Everything is opened memory-mapped: the ensemble alone is 200 MB, and a
    seven-day window touches a few megabytes of it.
    """
    if not source_dir.is_dir():
        raise SourceError(f"source directory not found: {source_dir}")

    missing = [name for name in SOURCE_FILES if not (source_dir / name).is_file()]
    if missing:
        raise SourceError(
            "required source file(s) missing from "
            f"{source_dir}: {', '.join(missing)} — nothing was imported"
        )

    source = {
        "dir": source_dir,
        "dates": np.load(source_dir / DATES_FILE),
        "ensemble": np.load(source_dir / ENSEMBLE_FILE, mmap_mode="r"),
        "true": np.load(source_dir / TRUE_FILE, mmap_mode="r"),
        "uncertainty": np.load(source_dir / UNCERTAINTY_FILE, mmap_mode="r"),
        "confidence": np.load(source_dir / CONFIDENCE_FILE, mmap_mode="r"),
        "valid_mask": np.load(source_dir / VALID_MASK_FILE),
    }

    dates = source["dates"]
    if dates.ndim != 1 or not np.issubdtype(dates.dtype, np.datetime64):
        raise SourceError(f"{DATES_FILE} must be 1-D datetime64, got {dates.dtype} {dates.shape}")
    count = dates.shape[0]

    ensemble = source["ensemble"]
    if ensemble.ndim == 5:
        if ensemble.shape[0] != count or ensemble.shape[2] != 3:
            raise SourceError(
                f"{ENSEMBLE_FILE} has shape {ensemble.shape}; expected "
                f"({count}, 3, 3, {ROI_SHAPE[0]}, {ROI_SHAPE[1]}) with the "
                "quantile axis (lower, mean, upper) third"
            )
        if ensemble.shape[-2:] != ROI_SHAPE:
            raise SourceError(
                f"{ENSEMBLE_FILE} spatial shape {ensemble.shape[-2:]} != {ROI_SHAPE}"
            )
    elif ensemble.ndim == 4:
        if ensemble.shape[0] != count or ensemble.shape[1] != 3:
            raise SourceError(
                f"{ENSEMBLE_FILE} has shape {ensemble.shape}; expected "
                f"({count}, 3, {ROI_SHAPE[0]}, {ROI_SHAPE[1]})"
            )
        if ensemble.shape[-2:] != ROI_SHAPE:
            raise SourceError(
                f"{ENSEMBLE_FILE} spatial shape {ensemble.shape[-2:]} != {ROI_SHAPE}"
            )
    else:
        raise SourceError(f"{ENSEMBLE_FILE} must be 4-D or 5-D, got shape {ensemble.shape}")

    for key, name in (
        ("true", TRUE_FILE),
        ("uncertainty", UNCERTAINTY_FILE),
        ("confidence", CONFIDENCE_FILE),
    ):
        if source[key].shape != (count, 3, *ROI_SHAPE):
            raise SourceError(
                f"{name} has shape {source[key].shape}, expected {(count, 3, *ROI_SHAPE)}"
            )

    mask = source["valid_mask"]
    if mask.shape != ROI_SHAPE:
        raise SourceError(f"{VALID_MASK_FILE} has shape {mask.shape}, expected {ROI_SHAPE}")

    return source


def match_dates(dates: np.ndarray, start: date, end: date) -> list[tuple[int, date]]:
    """``[(index, issue date)]`` for every source date inside the window."""
    if end < start:
        raise SourceError(f"end date {end} is before start date {start}")
    matched: list[tuple[int, date]] = []
    for index, value in enumerate(dates):
        day = date.fromisoformat(str(value)[:10])
        if start <= day <= end:
            matched.append((index, day))
    return matched


def horizon_planes(source: dict, index: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(median, half_width, actual, confidence)`` as ``[3, 101, 361]``."""
    ensemble = source["ensemble"]
    if ensemble.ndim == 5:
        # [date, horizon, quantile, row, col] — quantile 1 is the ensemble mean.
        median = np.asarray(ensemble[index, :, 1, :, :], dtype=np.float32)
    else:
        median = np.asarray(ensemble[index], dtype=np.float32)

    half_width = np.asarray(source["uncertainty"][index], dtype=np.float32)
    actual = np.asarray(source["true"][index], dtype=np.float32)
    confidence = np.asarray(source["confidence"][index])
    return median, half_width, actual, confidence


def apply_valid_mask(mask: np.ndarray, *arrays: np.ndarray) -> tuple[np.ndarray, ...]:
    """NaN every cell the forecaster does not claim, before reprojection."""
    masked = []
    for array in arrays:
        copy = np.array(array, dtype=np.float32, copy=True)
        copy[..., ~mask] = np.nan
        masked.append(copy)
    return tuple(masked)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def required_paths(frames_dir: Path) -> list[Path]:
    return [
        frames_dir / f"{horizon}_{field}.png"
        for horizon in HORIZONS
        for field in REQUIRED_FIELDS
    ] + [frames_dir / "manifest.json"]


def is_complete(frames_dir: Path) -> bool:
    return all(path.is_file() for path in required_paths(frames_dir))


def wipe_day(display_pipeline, day: date) -> None:
    """Remove one issue date from both trees so nothing stale survives."""
    for root in (display_pipeline.frames_dir(day), display_pipeline.arrays_dir(day)):
        if root.exists():
            shutil.rmtree(root)


def render_day(display_pipeline, day: date, median, half_width, actual, confidence,
               *, date_index: int, source_name: str) -> dict:
    """Render one date through the display pipeline and stamp provenance."""
    manifest = display_pipeline.render_frames(
        SimpleNamespace(median=median, interval_half_width=half_width),
        day,
        version=DATA_VERSION,
        actual=actual,
    )

    pipeline_fields = dict(manifest)
    provenance = {
        "date": day.isoformat(),
        "source": source_name,
        "ensemble_file": ENSEMBLE_FILE,
        "date_index": int(date_index),
        "frames": pipeline_fields.pop("frames"),
        "notes": PROVENANCE_NOTE,
        "observed_file": TRUE_FILE,
        "uncertainty_file": UNCERTAINTY_FILE,
        "confidence_file": CONFIDENCE_FILE,
        "valid_mask_file": VALID_MASK_FILE,
        "valid_cells": int(np.isfinite(median[0]).sum()),
        "confidence_classes": {
            str(int(value)): int(count)
            for value, count in zip(*np.unique(confidence, return_counts=True))
        },
    }
    provenance.update(pipeline_fields)

    manifest_path = display_pipeline.frames_dir(day) / "manifest.json"
    manifest_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return provenance


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def bump_data_version(version: int, notes: str) -> dict:
    """Set ``data_version['sic']`` to ``version`` (never backwards).

    The scheduler's own ``bump`` only increments by one, which cannot move
    the ledger to the revision this import publishes, so the row is written
    directly through the same sync session factory.
    """
    from sqlalchemy import update

    from app.models import DataVersion
    from app.services import version_service

    now = datetime.now(timezone.utc)
    with version_service.open_session() as session:
        row = session.get(DataVersion, "sic")
        if row is None:
            session.add(DataVersion(key="sic", version=version, updated_at=now, notes=notes))
            result = {"key": "sic", "version": version, "action": "inserted"}
        elif row.version < version:
            session.execute(
                update(DataVersion)
                .where(DataVersion.key == "sic")
                .values(version=version, updated_at=now, notes=notes)
            )
            result = {"key": "sic", "version": version, "action": "set"}
        else:
            session.execute(
                update(DataVersion)
                .where(DataVersion.key == "sic")
                .values(updated_at=now, notes=notes)
            )
            result = {"key": "sic", "version": int(row.version), "action": "kept_higher"}
        session.commit()
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Settings resolves ``.env`` and ``STORAGE_ROOT`` against the working
    # directory; run from anywhere and the backend's own tree still wins.
    if not (Path.cwd() / ".env").is_file() and (BACKEND_ROOT / ".env").is_file():
        os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))

    from app.services import display_pipeline

    source_dir = (args.source_dir or DEFAULT_SOURCE_DIR).expanduser()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)

    try:
        source = load_source(source_dir)
    except SourceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    matched = match_dates(source["dates"], start, end)
    print(f"source: {source_dir}")
    print(f"source arrays: {len(source['dates'])} dates, "
          f"ensemble {tuple(source['ensemble'].shape)}, "
          f"valid cells {int(source['valid_mask'].sum())}/{source['valid_mask'].size}")
    print(f"window {start.isoformat()}..{end.isoformat()}: {len(matched)} date(s) matched")
    if not matched:
        print("nothing to do", file=sys.stderr)
        return 1

    imported, skipped, failed = [], [], []
    for index, day in matched:
        frames_dir = display_pipeline.frames_dir(day)
        if not args.force and is_complete(frames_dir):
            skipped.append(day)
            print(f"{day}: complete on disk, skipping (use --force to rebuild)")
            continue

        try:
            median, half_width, actual, confidence = horizon_planes(source, index)
            median, half_width, actual = apply_valid_mask(
                source["valid_mask"], median, half_width, actual
            )

            # The three horizons must be three different forecasts: a
            # collapsed axis would render one day three times.
            collapsed = [
                (a + 1, b + 1)
                for a in range(len(HORIZONS))
                for b in range(a + 1, len(HORIZONS))
                if np.array_equal(median[a], median[b])
            ]
            if collapsed:
                raise SourceError(
                    f"horizons {collapsed} are identical for {day} — the import "
                    "collapsed the horizon axis"
                )
            if not np.isfinite(median).any():
                raise SourceError(f"{day}: median has no finite cell after masking")

            if frames_dir.exists() or display_pipeline.arrays_dir(day).exists():
                wipe_day(display_pipeline, day)

            manifest = render_day(
                display_pipeline, day, median, half_width, actual, confidence,
                date_index=index, source_name="2026_test_set",
            )
        except SourceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            failed.append(day)
            continue

        imported.append(day)
        finite = median[np.isfinite(median)]
        print(
            f"{day}: index {index}, {manifest['png_count']} PNGs, "
            f"h1 range {finite.min():.3f}..{finite.max():.3f} "
            f"(mean {finite.mean():.3f}), h1/h2 differ, h1/h3 differ"
        )

    bump_ok = True
    if args.no_version_bump:
        print("data_version[sic]: left untouched (--no-version-bump)")
    else:
        try:
            result = bump_data_version(DATA_VERSION, DATA_VERSION_NOTES)
            print(f"data_version[sic]: {result['version']} ({result['action']}), "
                  f"notes {DATA_VERSION_NOTES!r}")
        except Exception as exc:  # noqa: BLE001 — report, never hide the frame result
            bump_ok = False
            print(f"ERROR: data_version bump failed: {exc}", file=sys.stderr)

    print(
        f"done: {len(imported)} imported ({', '.join(d.isoformat() for d in imported)}), "
        f"{len(skipped)} skipped, {len(failed)} failed"
    )
    return 0 if bump_ok and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
