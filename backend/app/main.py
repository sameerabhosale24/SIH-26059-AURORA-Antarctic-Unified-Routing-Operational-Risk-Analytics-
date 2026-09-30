"""
AURORA backend application.

Auth and vessel management only — SIC, routing, WebSocket relays and data
source adapters arrive later and will mount on the same app.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, vessels
from app.config import get_settings
from app.db.session import engine
from app.redis.client import get_redis_client

logger = logging.getLogger("aurora")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()


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

    PostgreSQL is fatal: nothing here works without it. Redis is advisory
    for now — nothing in auth needs it — so a dead broker degrades the health
    report instead of taking the API down.
    """
    if not await _ping_db():
        raise RuntimeError(f"Cannot reach PostgreSQL at {settings.DATABASE_URL}")

    if not await _ping_redis():
        logger.warning("Redis is not reachable at %s", settings.REDIS_URL)

    yield

    await engine.dispose()


app = FastAPI(
    title="AURORA API",
    version="0.1.0",
    description="Authentication and vessel management for the AURORA console.",
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


@app.get("/api/health", tags=["health"])
async def health() -> dict:
    db_ok = await _ping_db()
    redis_ok = await _ping_redis()
    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "db": db_ok,
        "redis": redis_ok,
    }
