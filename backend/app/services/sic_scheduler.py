"""The daily SIC forecast cycle.

Runs at 03:00 UTC via APScheduler, or on demand::

    python -m app.services.sic_scheduler --date 2026-03-15
    python -m app.services.sic_scheduler --dry-run

The cycle's job is to be honest. It will happily skip a day, keep the last
good forecast, and raise a ``forecast_stale`` alarm — what it will never do
is publish a forecast built from data it does not have.

Staleness policy
----------------
``FORECASTER_MAX_STALENESS_DAYS`` (7) is the point at which a forecast is
still usable but must be marked DEGRADED so the frontend halves the layer
opacity. ``FORECASTER_DEGRADED_DAYS`` (10) is the point at which it is no
longer usable at all: the run is abandoned, the previous version is kept,
and an alarm is raised.

.. note::
   The prompt assigns "do not publish" to the 7-day threshold and
   "publish as DEGRADED" to the 10-day threshold, which cannot both hold —
   anything past 10 days is also past 7. The thresholds are applied here in
   the only order that produces a sensible policy (degrade at 7, stop at
   10) and the deviation is reported in the build notes.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import traceback
from datetime import date, datetime, timezone

import numpy as np

from app.adapters import ADAPTERS
from app.config import get_settings
from app.models import Alarm
from app.redis.pubsub import CHANNEL_SIC_UPDATED, publish_sync, record_sic_run_sync
from app.services import display_pipeline, input_assembly, version_service
from app.services.input_assembly import assemble_input_window

logger = logging.getLogger("aurora.sic")

#: The six sources the cycle asks about. All are reported whether or not
#: they are configured, so a run's log explains itself after the fact.
SOURCES = ("nsidc", "era5", "cmems", "cs2smos", "ibcso", "byu_scp")

# The forecaster is imported defensively: a backend whose forecaster is
# broken must still start, serve health, and let the scheduler skip runs.
try:
    from forecaster import ForecastOutput, predict  # noqa: F401

    FORECASTER_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001 — reported through GET /api/health
    ForecastOutput = None  # type: ignore[assignment]
    predict = None  # type: ignore[assignment]
    FORECASTER_IMPORT_ERROR = exc
    logger.warning("forecaster import failed; SIC runs will be skipped: %s", exc)


def forecaster_available() -> bool:
    return predict is not None and FORECASTER_IMPORT_ERROR is None


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------
def create_alarm(
    *,
    severity: str,
    type: str,
    message: str,
    payload: dict | None = None,
    vessel_id: int | None = None,
    geom_wkt: str | None = None,
    ts: datetime | None = None,
) -> dict:
    """Write an alarm row. Synchronous, because every caller is a job thread.

    An alarm that fails to persist is logged, not raised: losing the
    notification is bad, but losing the forecast cycle that triggered it is
    worse, and the hourly freshness check will raise the same alarm again.
    """
    from sqlalchemy import insert

    occurred = ts or datetime.now(timezone.utc)
    values: dict = {
        "ts": occurred,
        "vessel_id": vessel_id,
        "severity": severity,
        "type": type,
        "message": message,
        "payload": payload,
    }
    if geom_wkt:
        from geoalchemy2.elements import WKTElement

        values["geom"] = WKTElement(geom_wkt, srid=4326)

    try:
        with version_service.open_session() as session:
            alarm_id = session.execute(
                insert(Alarm).values(**values).returning(Alarm.id)
            ).scalar_one()
            session.commit()
        logger.warning("alarm raised: %s/%s — %s", severity, type, message)
        return {"id": int(alarm_id), "severity": severity, "type": type, "message": message}
    except Exception:  # noqa: BLE001
        logger.exception("could not persist alarm %s/%s", severity, type)
        return {"id": None, "severity": severity, "type": type, "message": message}


def raise_forecast_stale(reason: str, staleness: dict, target: date) -> dict:
    return create_alarm(
        severity="critical",
        type="forecast_stale",
        message=f"SIC forecast for {target.isoformat()} not published: {reason}",
        payload={"target_date": target.isoformat(), "staleness": staleness, "reason": reason},
    )


# ---------------------------------------------------------------------------
# The cycle
# ---------------------------------------------------------------------------
def source_availability() -> dict[str, bool]:
    availability: dict[str, bool] = {}
    for name in SOURCES:
        adapter = ADAPTERS.get(name)
        if adapter is None:
            availability[name] = False
            continue
        configured = adapter.is_configured()
        availability[name] = configured
        if not configured:
            logger.warning("adapter %s not configured", name)
    return availability


def _empty_summary(target: date, status: str, reason: str, started: float) -> dict:
    settings = get_settings()
    return {
        "target_date": target.isoformat(),
        "status": status,
        "reason": reason,
        "version": None,
        "staleness": None,
        "penalty_applied": 0.0,
        "interval_widened": False,
        "degraded": False,
        "frames_written": 0,
        "duration_s": round(time.perf_counter() - started, 3),
        "forecaster_available": forecaster_available(),
        "sources": source_availability(),
        "thresholds": {
            "max_staleness_days": settings.FORECASTER_MAX_STALENESS_DAYS,
            "degraded_days": settings.FORECASTER_DEGRADED_DAYS,
            "penalty_per_day": settings.STALENESS_PENALTY_PER_DAY,
        },
    }


def run_sic_cycle(target_date: date | None = None, *, dry_run: bool = False) -> dict:
    """Run one forecast cycle end to end. Returns a run summary.

    Never raises for expected failures (no data, stale data, forecaster
    error): each one is recorded in the returned summary so the caller and
    the health endpoint agree on what happened.
    """
    started = time.perf_counter()
    target = target_date or datetime.now(timezone.utc).date()
    settings = get_settings()
    mode = "dry-run" if dry_run else "cycle"
    logger.info("SIC %s starting for %s", mode, target.isoformat())

    # A dry run is strictly read-only. It reports what *would* happen and
    # must leave no alarm row, no ledger bump and no run record behind —
    # otherwise `--dry-run` pollutes the very state it is meant to inspect.
    def _stale(reason: str, staleness: dict) -> None:
        if dry_run:
            logger.warning("dry run: would raise forecast_stale — %s", reason)
            return
        raise_forecast_stale(reason, staleness, target)

    def _end(summary: dict) -> None:
        if dry_run:
            logger.info("dry run: no run record written")
            return
        _finish(summary)

    if not forecaster_available() and not dry_run:
        reason = f"forecaster unavailable: {FORECASTER_IMPORT_ERROR!r}"
        logger.error(reason)
        summary = _empty_summary(target, "skipped", reason, started)
        _stale(reason, {})
        _end(summary)
        return summary

    # 1-2. Source availability, then the input window.
    try:
        tensor, staleness = assemble_input_window(target)
    except ValueError as exc:
        # Expected on a fresh deployment with no credentials and no files.
        logger.warning("input window unavailable for %s: %s", target.isoformat(), exc)
        summary = _empty_summary(
            target, "dry_run" if dry_run else "skipped", str(exc), started
        )
        summary["staleness"] = None
        _stale(str(exc), {})
        _end(summary)
        return summary
    except Exception:  # noqa: BLE001 — anything else is a real defect
        logger.exception("input window assembly failed for %s", target.isoformat())
        summary = _empty_summary(target, "error", traceback.format_exc(), started)
        _end(summary)
        return summary

    # 3. Staleness gates.
    max_stale = int(staleness["max_staleness_days"])
    if max_stale > settings.FORECASTER_DEGRADED_DAYS:
        reason = (
            f"max staleness {max_stale}d exceeds FORECASTER_DEGRADED_DAYS="
            f"{settings.FORECASTER_DEGRADED_DAYS}; keeping the last good version"
        )
        logger.error("SIC cycle for %s: %s", target.isoformat(), reason)
        _stale(reason, staleness)
        summary = _empty_summary(
            target, "dry_run" if dry_run else "skipped_stale", reason, started
        )
        summary["staleness"] = staleness
        _end(summary)
        return summary

    degraded = max_stale > settings.FORECASTER_MAX_STALENESS_DAYS
    if degraded:
        logger.warning(
            "SIC cycle for %s is DEGRADED: max staleness %dd exceeds "
            "FORECASTER_MAX_STALENESS_DAYS=%dd",
            target.isoformat(), max_stale, settings.FORECASTER_MAX_STALENESS_DAYS,
        )

    if dry_run:
        summary = _empty_summary(target, "dry_run", "dry run — forecaster not called", started)
        summary["staleness"] = staleness
        logger.info(
            "DRY RUN %s: staleness=%s (max=%dd, degraded=%s)",
            target.isoformat(), json.dumps(staleness), max_stale, degraded,
        )
        _end(summary)
        return summary

    # 4. Inference.
    inference_started = time.perf_counter()
    try:
        output = predict(tensor)
    except Exception:  # noqa: BLE001 — CUDA OOM is retried on CPU inside predict()
        logger.exception("forecaster raised for %s", target.isoformat())
        summary = _empty_summary(target, "error", traceback.format_exc(), started)
        summary["staleness"] = staleness
        _end(summary)
        return summary
    inference_s = time.perf_counter() - inference_started

    # 5. Staleness penalty on the conformal interval. The forecaster never
    #    widens its own quantiles, so this is the only place it happens.
    penalty = settings.STALENESS_PENALTY_PER_DAY * max_stale
    if penalty > 0:
        output.interval_half_width = (
            np.asarray(output.interval_half_width, dtype=np.float32) * (1.0 + penalty)
        ).astype(np.float32)
    logger.info(
        "staleness penalty applied: %d day(s) -> %.3f (%.2f x interval half-width)",
        max_stale, penalty, 1.0 + penalty,
    )

    # 6. Display pipeline. The version is predicted here rather than read
    #    after the bump so a failed render leaves the ledger untouched.
    current = version_service.get("sic")
    next_version = (current.version if current is not None else 0) + 1
    try:
        manifest = display_pipeline.render_frames(
            output,
            target,
            version=next_version,
            staleness=staleness,
            penalty_applied=penalty,
            interval_widened=penalty > 0.0,
        )
    except Exception:  # noqa: BLE001
        logger.exception("display pipeline failed for %s", target.isoformat())
        summary = _empty_summary(target, "error", traceback.format_exc(), started)
        summary["staleness"] = staleness
        _end(summary)
        return summary

    # 7. Ledger — only on success.
    notes = "DEGRADED" if degraded else None
    version_row = version_service.bump("sic", staleness=staleness, notes=notes)

    # 8. Notify.
    publish_sync(
        CHANNEL_SIC_UPDATED,
        {
            "date": target.isoformat(),
            "version": version_row["version"],
            "degraded": degraded,
            "staleness": staleness,
            "penalty_applied": penalty,
            "published_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # 9. Log the run.
    duration = time.perf_counter() - started
    logger.info(
        "SIC cycle complete for %s: version=%s staleness_max=%dd "
        "penalty=%.3f degraded=%s inference=%.2fs total=%.2fs frames=%s",
        target.isoformat(), version_row["version"], max_stale, penalty, degraded,
        inference_s, duration, manifest.get("png_count"),
    )

    summary = {
        "target_date": target.isoformat(),
        "status": "degraded" if degraded else "published",
        "reason": None,
        "version": version_row["version"],
        "staleness": staleness,
        "penalty_applied": penalty,
        "interval_widened": penalty > 0.0,
        "degraded": degraded,
        "frames_written": int(manifest.get("png_count", 0)),
        "duration_s": round(duration, 3),
        "inference_s": round(inference_s, 3),
        "forecaster_available": True,
        "sources": source_availability(),
        "thresholds": {
            "max_staleness_days": settings.FORECASTER_MAX_STALENESS_DAYS,
            "degraded_days": settings.FORECASTER_DEGRADED_DAYS,
            "penalty_per_day": settings.STALENESS_PENALTY_PER_DAY,
        },
    }
    _end(summary)
    return summary


def _finish(summary: dict) -> None:
    """Record the run where GET /api/health can find it."""
    record_sic_run_sync(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": summary.get("status"),
            "target_date": summary.get("target_date"),
            "version": summary.get("version"),
            "reason": summary.get("reason"),
            "duration_s": summary.get("duration_s"),
        }
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{raw!r} is not an ISO date (YYYY-MM-DD)"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="python -m app.services.sic_scheduler",
        description="Run one AURORA SIC forecast cycle.",
    )
    parser.add_argument("--date", type=_parse_date, default=None,
                        help="target date, YYYY-MM-DD (default: today, UTC)")
    parser.add_argument("--dry-run", action="store_true",
                        help="assemble the input window and log staleness; "
                             "do not call the forecaster")
    args = parser.parse_args(argv)

    summary = run_sic_cycle(args.date, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, default=str))
    if summary["status"] == "error":
        return 1
    if summary["status"] == "dry_run":
        return 0
    if summary["status"] in ("skipped", "skipped_stale") and not args.dry_run:
        # Expected on an unconfigured deployment, but worth surfacing.
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    raise SystemExit(main())
