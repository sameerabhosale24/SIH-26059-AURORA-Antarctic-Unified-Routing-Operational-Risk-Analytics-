"""
One async Redis client for the whole process.

Created lazily so importing the app never opens a socket, and shared because
`redis.asyncio` connections are multiplexed — one client is both correct and
cheaper than one per request.
"""

from redis.asyncio import Redis

from app.config import get_settings

_client: Redis | None = None


def get_redis_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _client


async def get_redis() -> Redis:
    """FastAPI dependency handing out the shared client."""
    return get_redis_client()
