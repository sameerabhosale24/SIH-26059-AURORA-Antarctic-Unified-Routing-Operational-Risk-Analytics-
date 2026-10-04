"""AURORA backend application.

Auth and vessel management, the REST resources the map reads (reference
data, versions, SIC frames, telemetry, routes, icebergs, weather, alarms),
the data-infrastructure jobs behind them, five WebSocket channels, the
real-time relays, and the single health endpoint that exposes all of it.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import ws
from app.api import (
    alarms,
    auth,
    icebergs,
    reference,
    route,
    sic,
    telemetry,
    vessels,
    version,
    weather,
)
from app.config import get_settings
from app.db.session import engine
from app.redis.client import get_redis_client
from app.redis.pubsub import read_sic_run
from app.schedulers.scheduler import next_sic_run, scheduler_running, start_scheduler, stop_scheduler

logger = logging.getLogger("aurora")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()


def _probe_forecaster() -> bool:
    """Import the forecaster and decide whether its artifacts resolve.

    Failure here is not fatal: the backend still serves auth, vessels and
    health, and the SIC scheduler skips its runs. What matters is that the
    operator can see the difference through GET /api/health.
    """
    try:
        from forecaster import predict  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        logger.warning("forecaster import failed; SIC runs will be skipped: %s", exc)
        return False

    # The vendored package defaults to <package>/artifacts, which is correct
    # regardless of the working directory. Only export a configured path when
    # it actually resolves, so a relative default never shadows a working one.
    configured = Path(settings.SIC_ARTIFACTS_PATH)
    candidates = [configured, (Path.cwd() / configured).resolve(), configured.resolve()]
    for candidate in candidates:
        if candidate.is_dir():
            os.environ.setdefault("SIC_ARTIFACTS_PATH", str(candidate))
            break
    return True


async def _ping_db() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 — the status endpoint reports, it never raises
        logger.exception("PostgreSQL ping failed")
        return False


async def _ping_redis() -> bool:
    try:
        return bool(await get_redis_client().ping())
    except Exception:  # noqa: BLE001
        logger.exception("Redis ping failed")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Verify the backing services before the first request is accepted.

    PostgreSQL is fatal: nothing here works without it. Redis and the
    forecaster are advisory — a dead broker or a missing artifact set
    degrades the health report instead of taking the API down.
    """
    if not await _ping_db():
        raise RuntimeError(f"Cannot reach PostgreSQL at {settings.DATABASE_URL}")

    if not await _ping_redis():
        logger.warning("Redis is not reachable at %s", settings.REDIS_URL)

    forecaster_ok = _probe_forecaster()
    app.state.forecaster_ok = forecaster_ok

    start_scheduler()

    # The three continuous streams. Each guards its own configuration and
    # returns immediately when the deployment has no endpoint to connect
    # to, so an unconfigured backend starts nothing and logs why.
    from app.services.relays import ais_relay, gps_relay
    from app.services.weather_poller import run_weather_poller

    app.state.streams = [
        asyncio.create_task(gps_relay.run_gps_relay(), name="gps_relay"),
        asyncio.create_task(ais_relay.run_ais_relay(), name="ais_relay"),
        asyncio.create_task(run_weather_poller(), name="weather_poller"),
    ]

    yield

    for task in app.state.streams:
        task.cancel()
    await asyncio.gather(*app.state.streams, return_exceptions=True)

    stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title="AURORA API",
    version="0.2.0",
    description="AURORA console: auth, vessels, data infrastructure and health.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(vessels.router)

# Reference data first: the map cannot draw anything without the ROI, the
# coastline, the stations or the chart manifest, and none of it depends on
# a sensor or on who is asking.
app.include_router(reference.router)
app.include_router(version.router)
app.include_router(sic.router)
app.include_router(icebergs.router)

# Operational data. Every one of these scopes to the caller's own vessel.
app.include_router(telemetry.router)
app.include_router(route.router)
app.include_router(weather.router)
app.include_router(alarms.router)

# The five push channels. Unauthenticated by design — see app.ws.
ws.register(app)


@app.get("/api/health", tags=["health"])
async def health() -> dict:
    """Full system status: backing services, sources, scheduler, forecaster."""
    from app.adapters import health_snapshot

    db_ok = await _ping_db()
    redis_ok = await _ping_redis()

    forecaster_ok = bool(getattr(app.state, "forecaster_ok", False))
    if not forecaster_ok:
        # Re-probe cheaply so a transient startup failure can recover.
        forecaster_ok = _probe_forecaster()
        app.state.forecaster_ok = forecaster_ok

    sources = await asyncio.to_thread(health_snapshot)
    disk = await asyncio.to_thread(_report_disk_usage)
    last_run = await read_sic_run()

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "db": db_ok,
        "redis": redis_ok,
        "forecaster": forecaster_ok,
        "sources": sources,
        "disk": disk,
        "scheduler": {
            "running": scheduler_running(),
            "next_sic_run": next_sic_run(),
            "last_sic_run": last_run,
        },
    }


def _report_disk_usage() -> dict:
    """Storage report, isolated so a filesystem error cannot fail /api/health."""
    from app.services.storage_manager import report_disk_usage

    try:
        return report_disk_usage()
    except Exception:  # noqa: BLE001 — health reports, it never raises
        logger.exception("disk usage report failed")
        return {}
