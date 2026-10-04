"""Scheduled background jobs.

Six jobs, in two groups.

Data in (PART 1):

* ``sic_daily``          03:00 UTC — forecast cycle, iceberg ingest, version bump
* ``thickness_weekly``   Monday 04:00 UTC — CS2SMOS thickness ingest
* ``freshness_check``    every hour — staleness audit and alarms

Operational out (PART 2):

* ``route_optimize``     at ``ROUTE_JOB_HOURS`` — re-plan the own ship's route
* ``alarm_pass``         every ``ALARM_POLL_SECONDS`` — evaluate the alarm rules
* ``cleanup_daily``      at ``CLEANUP_JOB_HOUR`` — retention and disk report

Every job follows the same shape: log start, do the work, log end with
duration and status, update ``data_version`` **only on success**, and never
write fabricated data. A source that is unavailable is skipped, not fatal —
the point of the ledger is that the rest of the system can always tell what
actually happened.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.adapters import ADAPTERS
from app.config import get_settings

logger = logging.getLogger("aurora.scheduler")

SIC_JOB_ID = "sic_daily"
THICKNESS_JOB_ID = "thickness_weekly"
FRESHNESS_JOB_ID = "freshness_check"
ROUTE_JOB_ID = "route_optimize"
ALARM_JOB_ID = "alarm_pass"
CLEANUP_JOB_ID = "cleanup_daily"

_scheduler: BackgroundScheduler | None = None


@contextmanager
def _job_context(name: str):
    """Log start, duration and status for one job invocation."""
    started = time.perf_counter()
    logger.info("job %s started", name)
    status = "ok"
    try:
        yield
    except Exception as exc:  # noqa: BLE001 — a job must never kill the scheduler
        status = f"error: {exc}"
        logger.exception("job %s failed", name)
        raise
    finally:
        logger.info(
            "job %s finished: status=%s duration=%.2fs",
            name, status, time.perf_counter() - started,
        )


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _fetch_records(name: str, day: date) -> list | None:
    """Fetch from ``name``, returning ``None`` when it is not configured."""
    adapter = ADAPTERS.get(name)
    if adapter is None:
        logger.warning("job skipped: unknown adapter %r", name)
        return None
    if not adapter.is_configured():
        logger.warning("adapter %s not configured", name)
        return None
    return await adapter.fetch_if_available(day)


def _write_icebergs(records: list[dict]) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from geoalchemy2.elements import WKTElement

    from app.models import IcebergPosition

    if not records:
        return 0

    inserted = 0
    with _sync_session() as session:
        for record in records:
            ts = datetime.fromisoformat(str(record["ts"]))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            statement = (
                pg_insert(IcebergPosition)
                .values(
                    ts=ts,
                    iceberg_id=str(record["iceberg_id"]),
                    geom=WKTElement(
                        f"POINT({float(record['lon'])} {float(record['lat'])})", srid=4326
                    ),
                    length_km=record.get("length_km"),
                    drift_bearing=record.get("drift_bearing"),
                    drift_speed_kt=record.get("drift_speed_kt"),
                    source=record.get("source"),
                )
                .on_conflict_do_nothing(index_elements=["ts", "iceberg_id"])
            )
            result = session.execute(statement)
            inserted += int(result.rowcount or 0)
        session.commit()
    return inserted


def _sync_session():
    from app.services import version_service

    return version_service.open_session()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def job_sic_daily() -> dict:
    """03:00 UTC — forecast cycle plus the daily iceberg ingest."""
    from app.services import version_service
    from app.services.sic_scheduler import run_sic_cycle

    day = _today()
    summary: dict = {}
    with _job_context(SIC_JOB_ID):
        # Fetch start, not fetch end: a download that died halfway must not
        # leave a truncated file behind for the next run to treat as
        # complete, and a failure to clean must never stop the fetch.
        from app.services.storage_manager import ensure_raw_temp_clean

        ensure_raw_temp_clean()

        summary = run_sic_cycle(day)

        # Iceberg ingest is independent of the forecast: a bad forecast day
        # must not cost us the observations.
        try:
            import asyncio

            records = asyncio.run(_fetch_records("byu_scp", day))
        except Exception:  # noqa: BLE001
            logger.exception("iceberg fetch failed; skipping the ingest")
            records = None

        if records is None:
            logger.warning("iceberg ingest skipped (source unavailable)")
        else:
            try:
                written = _write_icebergs(records)
                version_service.bump(
                    "icebergs",
                    source_ts=datetime.now(timezone.utc),
                    notes=f"{written} rows upserted of {len(records)} parsed",
                )
                logger.info("icebergs: wrote %d new row(s)", written)
            except Exception:  # noqa: BLE001
                logger.exception("iceberg write failed; data_version not bumped")

    return summary


def job_thickness_weekly() -> dict:
    """Monday 04:00 UTC — fetch CS2SMOS and store the regridded thickness."""
    from app.services import version_service
    from app.services.field_storage import write_field

    day = _today()
    result: dict = {"status": "skipped"}
    with _job_context(THICKNESS_JOB_ID):
        adapter = ADAPTERS.get("cs2smos")
        if adapter is None or not adapter.is_configured():
            logger.warning("adapter cs2smos not configured")
            return result

        try:
            import asyncio

            raw = asyncio.run(adapter.fetch_if_available(day))
        except Exception:  # noqa: BLE001
            logger.exception("CS2SMOS fetch failed; skipping this week")
            return {"status": "fetch_error"}

        if raw is None:
            logger.warning("thickness ingest skipped (source unavailable)")
            return result

        try:
            grid = adapter.regrid(raw)
        except Exception:  # noqa: BLE001
            logger.exception("CS2SMOS regrid failed; data_version not bumped")
            return {"status": "regrid_error"}

        write_field("ice_thickness", day, grid)
        version_service.bump(
            "ice_thickness",
            source_ts=datetime.now(timezone.utc),
            notes=f"weekly ingest for {day.isoformat()}",
        )
        result = {"status": "ok", "date": day.isoformat(), "shape": list(grid.shape)}
        logger.info("ice_thickness updated for %s", day.isoformat())

    return result


def job_freshness_check() -> dict:
    """Every hour — audit every source and alarm when one has gone stale."""
    from app.services import version_service
    from app.services.sic_scheduler import create_alarm

    settings = get_settings()
    threshold = settings.FORECASTER_MAX_STALENESS_DAYS
    now = datetime.now(timezone.utc)
    report: dict = {"checked_at": now.isoformat(), "threshold_days": threshold, "sources": {}}

    with _job_context(FRESHNESS_JOB_ID):
        rows = version_service.get_all()
        for source, key in version_service.SOURCE_VERSION_KEYS.items():
            row = rows.get(key)
            if row is None:
                report["sources"][source] = {"status": "missing_row"}
                continue
            if row.version <= 0:
                # Never fetched. That is normal while credentials are absent
                # and must not alarm on every hour of a fresh deployment.
                report["sources"][source] = {"status": "never_fetched"}
                continue

            updated = row.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = int((now - updated).total_seconds() // 86400)
            status = "fresh" if age_days <= threshold else "stale"
            report["sources"][source] = {
                "status": status,
                "age_days": age_days,
                "version": row.version,
            }
            if status == "stale" and not _recent_stale_alarm(source):
                create_alarm(
                    severity="warning",
                    type="forecast_stale",
                    message=(
                        f"data source {source!r} is {age_days} day(s) old, "
                        f"past the {threshold}-day threshold"
                    ),
                    payload={"source": source, "age_days": age_days, "version": row.version},
                )

        stale = [
            name for name, info in report["sources"].items() if info.get("status") == "stale"
        ]
        logger.info(
            "freshness check: %d source(s) stale of %d — %s",
            len(stale), len(report["sources"]), stale or "none",
        )

    report["stale"] = stale
    return report


def _recent_stale_alarm(source: str) -> bool:
    """True when an unacknowledged stale alarm for ``source`` already exists.

    Without this the hourly job writes 24 identical alarms a day until
    someone acknowledges the first one.
    """
    from sqlalchemy import select

    from app.models import Alarm

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with _sync_session() as session:
        existing = session.execute(
            select(Alarm.id)
            .where(Alarm.type == "forecast_stale")
            .where(Alarm.acked_at.is_(None))
            .where(Alarm.ts >= cutoff)
            .limit(50)
        ).scalars().all()
        for alarm_id in existing:
            alarm = session.get(Alarm, alarm_id)
            payload = alarm.payload if alarm is not None else None
            if isinstance(payload, dict) and payload.get("source") == source:
                return True
    return False


def job_route_optimize() -> dict:
    """At each configured planning hour — re-plan the own ship's route.

    One run per hour, not a stream: the inputs are fields that change on a
    schedule of their own (SIC daily, ERA5 and CMEMS on their own cycles),
    and replanning faster than the inputs move would only produce routes
    that differ by noise. ``optimize`` persists the run and publishes it,
    so this job's job is to pick the ship and to log what came back.
    """
    from app.services import route_optimizer

    settings = get_settings()
    vessel_id = settings.OWN_SHIP_VESSEL_ID
    with _job_context(ROUTE_JOB_ID):
        run = route_optimizer.optimize(vessel_id, datetime.now(timezone.utc))
        summary = {
            "id": getattr(run, "id", None),
            "vessel_id": run.vessel_id,
            "status": run.status,
            "routes": len(run.routes or []),
            "notes": run.notes,
        }
        logger.info(
            "route pass: vessel %s status=%s routes=%d",
            vessel_id, run.status, summary["routes"],
        )
        return summary


def job_alarm_pass() -> dict:
    """Every ``ALARM_POLL_SECONDS`` — evaluate every rule over every ship.

    The pass is idempotent by design: a rule that is still true does not
    raise a second alarm, because :func:`app.services.alarm_engine` checks
    for an existing one first. That is what makes a short interval safe —
    running it sixty times an hour costs a query, not sixty alarms.
    """
    from app.services.alarm_engine import run_pass

    with _job_context(ALARM_JOB_ID):
        return run_pass()


def job_cleanup() -> dict:
    """At ``CLEANUP_JOB_HOUR`` — apply retention and report disk usage.

    Two calls in one job because they answer the same question: how much
    space this deployment is using and whether it is still under the
    configured warning lines. The report is returned so it reaches the
    scheduler log; the numbers are also available live from
    ``GET /api/health``.
    """
    from app.services.storage_manager import cleanup_raw_temp, cleanup_sic_frames, report_disk_usage

    with _job_context(CLEANUP_JOB_ID):
        frames = cleanup_sic_frames()
        temp = cleanup_raw_temp()
        usage = report_disk_usage()
        over = usage.get("over_warn") or []
        if over:
            logger.warning("disk usage over the warning line for: %s", ", ".join(over))
        return {"frames": frames, "raw_temp": temp, "usage": usage}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def create_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        job_sic_daily,
        CronTrigger(hour=settings.DAILY_JOB_HOUR, minute=0),
        id=SIC_JOB_ID,
        name="SIC forecast cycle (daily)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        job_thickness_weekly,
        CronTrigger(day_of_week="mon", hour=4, minute=0),
        id=THICKNESS_JOB_ID,
        name="Ice thickness ingest (weekly)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=6 * 3600,
    )
    scheduler.add_job(
        job_freshness_check,
        CronTrigger(minute=0),
        id=FRESHNESS_JOB_ID,
        name="Source freshness check (hourly)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )

    hours = settings.route_job_hours
    scheduler.add_job(
        job_route_optimize,
        CronTrigger(hour=",".join(str(h) for h in hours), minute=0),
        id=ROUTE_JOB_ID,
        name="Route optimization (planning hours)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        job_alarm_pass,
        IntervalTrigger(seconds=max(int(settings.ALARM_POLL_SECONDS), 10)),
        id=ALARM_JOB_ID,
        name="Alarm evaluation (interval)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        job_cleanup,
        CronTrigger(hour=settings.CLEANUP_JOB_HOUR, minute=0),
        id=CLEANUP_JOB_ID,
        name="Retention and disk report (daily)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("scheduler already running")
        return _scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info(
        "scheduler started with jobs: %s",
        [job.id for job in _scheduler.get_jobs()],
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")
    except Exception:  # noqa: BLE001 — shutdown must not block process exit
        logger.exception("scheduler shutdown failed")
    finally:
        _scheduler = None


def scheduler_running() -> bool:
    return _scheduler is not None and bool(_scheduler.running)


def next_sic_run() -> str | None:
    if _scheduler is None:
        return None
    try:
        job = _scheduler.get_job(SIC_JOB_ID)
    except Exception:  # noqa: BLE001
        return None
    if job is None or job.next_run_time is None:
        return None
    next_run = job.next_run_time
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)
    return next_run.isoformat()
