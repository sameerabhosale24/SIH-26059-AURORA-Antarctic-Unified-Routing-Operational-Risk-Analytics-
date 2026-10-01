"""Redis pub/sub and small run-status keys.

Two entry points on purpose. APScheduler runs its jobs on worker threads
with no event loop, so the scheduler needs a synchronous publisher; the
FastAPI side is async and should not block its loop on a socket write.
Both talk to the same broker with the same payload encoding.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from app.config import get_settings

logger = logging.getLogger("aurora.pubsub")

CHANNEL_SIC_UPDATED = "sic.updated"
CHANNEL_ALARM = "alarm.created"

#: Last completed SIC cycle, for GET /api/health.
LAST_SIC_RUN_KEY = "aurora:sic:last_run"

_sync_client: SyncRedis | None = None


def get_sync_redis() -> SyncRedis:
    global _sync_client
    if _sync_client is None:
        _sync_client = SyncRedis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _sync_client


def _encode(payload: Any) -> str:
    return json.dumps(payload, default=str)


def publish_sync(channel: str, payload: Any) -> bool:
    """Publish from a scheduler thread. Returns False when Redis is down.

    A dead broker must never abort a job that has already done its useful
    work — the database is the source of truth; the event is a hint.
    """
    try:
        get_sync_redis().publish(channel, _encode(payload))
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not publish to %s (redis unavailable?)", channel, exc_info=True)
        return False


async def publish(channel: str, payload: Any) -> bool:
    """Publish from the async application side."""
    from app.redis.client import get_redis_client

    try:
        await get_redis_client().publish(channel, _encode(payload))
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not publish to %s (redis unavailable?)", channel, exc_info=True)
        return False


def record_sic_run_sync(summary: dict) -> bool:
    try:
        get_sync_redis().set(LAST_SIC_RUN_KEY, _encode(summary))
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not record the last SIC run", exc_info=True)
        return False


def read_sic_run_sync() -> dict | None:
    try:
        raw = get_sync_redis().get(LAST_SIC_RUN_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("could not read the last SIC run", exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:  # pragma: no cover — corrupt value, degrade gracefully
        logger.warning("last SIC run record is not valid JSON")
        return None


async def read_sic_run() -> dict | None:
    from app.redis.client import get_redis_client

    try:
        raw = await get_redis_client().get(LAST_SIC_RUN_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("could not read the last SIC run", exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:  # pragma: no cover
        return None
