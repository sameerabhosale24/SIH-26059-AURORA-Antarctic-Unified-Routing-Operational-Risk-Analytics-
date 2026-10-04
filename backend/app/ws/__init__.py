"""WebSocket channels: ``/ws/vessel``, ``/ws/ais``, ``/ws/alarms``,
``/ws/weather`` and ``/ws/route``.

Every channel behaves identically, because the console's five stores are
built identically:

1. accept,
2. send the channel's current value so a freshly opened tab is not blank,
3. subscribe to the matching Redis channel and forward every event,
4. stay open until the client goes away.

The sockets are deliberately unauthenticated. The frontend opens them with
``new WebSocket(url)`` — there is no header, no query string and no
subprotocol in which a bearer token could travel, and a token placed in
the URL would be written to every proxy log that touches it. The
consequence is stated plainly rather than papered over: these five streams
are deployment-wide, not per-operator, and they carry the own-ship
telemetry of ``OWN_SHIP_VESSEL_ID``. The REST endpoints beside them are
scoped; these are not.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.redis.client import get_redis_client
from app.redis.pubsub import (
    CHANNEL_AIS,
    CHANNEL_ALARM,
    CHANNEL_ROUTE,
    CHANNEL_VESSEL,
    CHANNEL_WEATHER,
    read_channel,
)

logger = logging.getLogger("aurora.ws")

#: Path segment → Redis channel. Adding a stream means adding one entry.
CHANNELS: dict[str, str] = {
    "vessel": CHANNEL_VESSEL,
    "ais": CHANNEL_AIS,
    "alarms": CHANNEL_ALARM,
    "weather": CHANNEL_WEATHER,
    "route": CHANNEL_ROUTE,
}

#: Service restarted with an empty Redis: report abnormal closure so the
#: client's backoff reconnects, rather than sitting on a dead subscription.
CLOSE_GOING_AWAY = 1011


def _seed(name: str) -> Any | None:
    """Current value straight from the database, when Redis has no cache.

    The cache is written *before* an event is published, so it is normally
    the freshest thing available. This only covers the case where the cache
    is gone entirely — a flush, a redeploy — and the operator has just
    opened a tab that would otherwise sit empty while the data is sitting
    in Postgres the whole time.

    Reads happen on a worker thread: these are the same synchronous
    services the REST layer calls, and blocking the event loop would stall
    every other socket.
    """
    from app.services import alarm_service, ais_service, route_service, vessel_service
    from app.services.weather_poller import sample_at_vessel

    own = get_settings().OWN_SHIP_VESSEL_ID

    if name == "vessel":
        row = vessel_service.latest_state(own)
        return vessel_service.serialize_state(row) if row is not None else None
    if name == "ais":
        return {"targets": ais_service.latest_targets()}
    if name == "weather":
        return sample_at_vessel(own)
    if name == "route":
        return route_service.latest_run(own)
    if name == "alarms":
        alarms = alarm_service.list_alarms(vessel_id=own, limit=1)
        return alarms[0] if alarms else None
    return None


async def _current(name: str, channel: str) -> Any | None:
    """What a newly connected client should be told first."""
    cached = await read_channel(channel)
    if cached is not None:
        return cached
    return await asyncio.to_thread(_seed, name)


async def _forward(pubsub, websocket: WebSocket, channel: str) -> None:
    """Relay every published event until Redis or the socket fails."""
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8", errors="replace")
            if isinstance(data, str):
                await websocket.send_text(data)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — a broken broker must end the socket
        logger.warning("subscription to %s ended", channel, exc_info=True)
        with suppress(Exception):
            await websocket.close(code=CLOSE_GOING_AWAY)


async def _drain(websocket: WebSocket) -> None:
    """Wait for the client to say something, or to go away.

    The console never sends a frame, so this returns only on disconnect.
    It exists purely so the handler can race it against the forwarder and
    notice whichever finishes first.
    """
    while True:
        await websocket.receive_text()


async def _serve(websocket: WebSocket, name: str, channel: str) -> None:
    await websocket.accept()
    logger.debug("ws/%s connected", name)

    try:
        current = await _current(name, channel)
        if current is not None:
            await websocket.send_json(current)

        pubsub = get_redis_client().pubsub()
        await pubsub.subscribe(channel)
    except Exception:  # noqa: BLE001 — cannot serve a stream we cannot join
        logger.exception("ws/%s could not start", name)
        with suppress(Exception):
            await websocket.close(code=CLOSE_GOING_AWAY)
        return

    forward = asyncio.create_task(_forward(pubsub, websocket, channel))
    drain = asyncio.create_task(_drain(websocket))
    try:
        await asyncio.wait({forward, drain}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        # The connection is being torn down from underneath us — by a client
        # that vanished or by application shutdown. Falling through to the
        # cleanup below is the whole response; swallowing it here stops a
        # cancelled handler from abandoning a live Redis subscription.
        logger.debug("ws/%s cancelled while serving", name)
    finally:
        forward.cancel()
        drain.cancel()
        try:
            await asyncio.gather(forward, drain, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        try:
            await asyncio.wait_for(pubsub.unsubscribe(channel), timeout=5)
            # ``aclose`` on redis-py 5+, ``close`` before that; either way
            # the subscription must not outlive the socket it was serving.
            close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
            if close is not None:
                await asyncio.wait_for(close(), timeout=5)
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            logger.debug("ws/%s could not release its subscription", name)
        logger.debug("ws/%s disconnected", name)


def register(app: FastAPI) -> None:
    """Attach one WebSocket route per entry in :data:`CHANNELS`."""
    for path_name, redis_channel in CHANNELS.items():
        # A fresh closure per iteration: a shared one would capture the loop
        # variable and every socket would end up serving the same channel.
        def make_handler(key: str, broker_channel: str):
            async def handler(websocket: WebSocket) -> None:
                await _serve(websocket, key, broker_channel)

            handler.__name__ = f"ws_{key}"
            return handler

        app.websocket(f"/ws/{path_name}")(make_handler(path_name, redis_channel))
