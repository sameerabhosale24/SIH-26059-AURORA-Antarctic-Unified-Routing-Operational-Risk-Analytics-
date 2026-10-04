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
CHANNEL_ROUTE = "route.updated"
CHANNEL_VESSEL = "vessel.updated"
CHANNEL_AIS = "ais.updated"
CHANNEL_WEATHER = "weather.updated"

#: Last completed SIC cycle, for GET /api/health.
LAST_SIC_RUN_KEY = "aurora:sic:last_run"

#: Cache key for the most recent payload on each channel, so a WebSocket
#: that connects between two events has something honest to show instead
#: of nothing. ``None`` means "no data yet", never an empty guess.
CHANNEL_CACHE_KEYS: dict[str, str] = {
    CHANNEL_SIC_UPDATED: "aurora:sic:current",
    CHANNEL_ALARM: "aurora:alarm:current",
    CHANNEL_ROUTE: "aurora:route:current",
    CHANNEL_VESSEL: "aurora:vessel:current",
    CHANNEL_AIS: "aurora:ais:current",
    CHANNEL_WEATHER: "aurora:weather:current",
}

_sync_client: SyncRedis | None = None


def get_sync_redis() -> SyncRedis:
    global _sync_client
    if _sync_client is None:
        _sync_client = SyncRedis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _sync_client


def _encode(payload: Any) -> str:
    return json.dumps(payload, default=str)


def _cache_key(channel: str) -> str | None:
    return CHANNEL_CACHE_KEYS.get(channel)


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


def publish_cached_sync(channel: str, payload: Any) -> bool:
    """Cache ``payload`` as the channel's current value, then publish it.

    The cache write comes first on purpose: a client that connects right
    after the event must read the same numbers the event carried, not an
    older snapshot or an empty frame.
    """
    key = _cache_key(channel)
    encoded = _encode(payload)
    client = get_sync_redis()
    try:
        if key:
            client.set(key, encoded)
        client.publish(channel, encoded)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not publish to %s (redis unavailable?)", channel, exc_info=True)
        return False


def read_channel_sync(channel: str) -> Any | None:
    """Cached payload for ``channel``, or ``None`` when there is none yet."""
    key = _cache_key(channel)
    if not key:
        return None
    try:
        raw = get_sync_redis().get(key)
    except Exception:  # noqa: BLE001
        logger.warning("could not read the cached payload for %s", channel, exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:  # pragma: no cover — corrupt value, degrade gracefully
        logger.warning("cached payload for %s is not valid JSON", channel)
        return None


async def publish(channel: str, payload: Any) -> bool:
    """Publish from the async application side."""
    from app.redis.client import get_redis_client

    try:
        await get_redis_client().publish(channel, _encode(payload))
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not publish to %s (redis unavailable?)", channel, exc_info=True)
        return False


async def publish_cached(channel: str, payload: Any) -> bool:
    """Async twin of :func:`publish_cached_sync`."""
    from app.redis.client import get_redis_client

    key = _cache_key(channel)
    encoded = _encode(payload)
    try:
        client = get_redis_client()
        if key:
            await client.set(key, encoded)
        await client.publish(channel, encoded)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not publish to %s (redis unavailable?)", channel, exc_info=True)
        return False


async def read_channel(channel: str) -> Any | None:
    """Async twin of :func:`read_channel_sync`."""
    from app.redis.client import get_redis_client

    key = _cache_key(channel)
    if not key:
        return None
    try:
        raw = await get_redis_client().get(key)
    except Exception:  # noqa: BLE001
        logger.warning("could not read the cached payload for %s", channel, exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:  # pragma: no cover
        return None


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
