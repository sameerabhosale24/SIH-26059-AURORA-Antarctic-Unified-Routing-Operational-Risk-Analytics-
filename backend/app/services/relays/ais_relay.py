"""AIS relay: AISStream.io WebSocket into ``ais_track``.

Same contract as the GPS relay — a long-running asyncio task, immediate
return when the key is absent, backoff on a dead socket, and a write failure
that never tears down the reader — with one difference: the subscription is
declared up front.

The subscription is a set of bounding boxes derived from the ROI rather than
a hand-typed list, so the relay cannot quietly drift away from the grid every
other field is on. Boxes are split by longitude because AISStream rejects a
box wider than a few thousand miles at these latitudes.

Only the messages that carry information AURORA stores are handled:
``PositionReport`` (where a ship is and how it is moving) and
``ShipStaticData`` (what it is called and where it is bound). Everything
else is counted and ignored rather than logged per message.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.services import ais_service
from app.utils.constants import ROI_LAT_MAX, ROI_LAT_MIN, ROI_LON_MAX, ROI_LON_MIN

logger = logging.getLogger("aurora.relay.ais")

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
#: Do not push the whole target list more often than this. AIS bursts; the
#: operator does not need one frame per vessel per second.
PUBLISH_INTERVAL_S = 5.0
#: Reconnect interval when the stream refuses or drops.
RECONNECT_MIN_S = 5
RECONNECT_MAX_S = 60


def bounding_boxes(lat_step: float = 11.0, lon_step: float = 28.0) -> list[list[list[float]]]:
    """``[ [[[south, west], [north, east]], ...] ]`` covering the whole ROI.

    Each box is a *pair of corners*, which is the shape AISStream documents —
    a flat four-number list is silently rejected. The ROI is split by
    longitude because a single box spanning it is wider than the service
    accepts at these latitudes. Derived from the ROI constants rather than
    hand-typed, so the relay cannot drift away from the grid every other
    field sits on.
    """
    south = round(ROI_LAT_MIN - lat_step / 2.0, 4)
    north = round(ROI_LAT_MAX + lat_step / 2.0, 4)
    boxes: list[list[list[float]]] = []
    west = ROI_LON_MIN - lon_step / 2.0
    while west < ROI_LON_MAX:
        east = min(west + lon_step, ROI_LON_MAX + lon_step / 2.0)
        boxes.append([[round(west, 4), south], [round(east, 4), north]])
        west += lon_step
    return boxes


def subscription() -> dict:
    """The one JSON frame AISStream expects within three seconds of connect."""
    return {
        "APIKey": get_settings().AISSTREAM_API_KEY,
        "BoundingBoxes": bounding_boxes(),
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }


def _meta_value(meta: dict, *keys: str):
    for key in keys:
        if meta.get(key) is not None:
            return meta.get(key)
    return None


def _parse_time(raw) -> datetime | None:
    """AISStream sends either an ISO timestamp or epoch seconds."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc)
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _as_float(raw) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value == value else None  # NaN guard


def _body(message: dict, key: str) -> dict:
    inner = message.get("Message")
    if isinstance(inner, dict):
        payload = inner.get(key)
        if isinstance(payload, dict):
            return payload
    return {}


def extract_position(update: dict) -> dict | None:
    """Position-report fields, or ``None`` when this message carries none."""
    meta = update.get("MetaData") or {}
    position = _body(update, "PositionReport")

    mmsi = _meta_value(meta, "MMSI", "Mmsi") or position.get("MMSI")
    lat = _as_float(position.get("Latitude"))
    lon = _as_float(position.get("Longitude"))
    if lat is None:
        lat = _as_float(_meta_value(meta, "Latitude", "latitude"))
    if lon is None:
        lon = _as_float(_meta_value(meta, "Longitude", "longitude"))
    if mmsi is None or lat is None or lon is None:
        return None
    try:
        mmsi = int(mmsi)
    except (TypeError, ValueError):
        return None

    return {
        "mmsi": mmsi,
        "lat": lat,
        "lon": lon,
        "sog": _as_float(position.get("Sog")),
        "cog": _as_float(position.get("Cog")),
        "heading": _as_float(position.get("Heading")),
        "name": (str(_meta_value(meta, "ShipName", "ship_name") or position.get("Name") or "")).strip() or None,
        "ts": _parse_time(_meta_value(meta, "Time", "time_utc", "time")) or datetime.now(timezone.utc),
    }


def extract_static(update: dict) -> dict | None:
    """Static-data fields plus a position, or ``None`` when unlocatable."""
    meta = update.get("MetaData") or {}
    static = _body(update, "ShipStaticData")
    if not static:
        return None

    mmsi = _meta_value(meta, "MMSI", "Mmsi") or static.get("MMSI")
    lat = _as_float(_meta_value(meta, "Latitude", "latitude"))
    lon = _as_float(_meta_value(meta, "Longitude", "longitude"))
    if mmsi is None or lat is None or lon is None:
        # A static message without a position would create a row with no
        # location, which is history AURORA has no way to place.
        return None
    try:
        mmsi = int(mmsi)
    except (TypeError, ValueError):
        return None

    voyage = static.get("VoyageData") or {}
    ship_type = static.get("ShipType")
    name = static.get("Name") or _meta_value(meta, "ShipName", "ship_name")
    return {
        "mmsi": mmsi,
        "lat": lat,
        "lon": lon,
        "name": (str(name or "")).strip() or None,
        "ship_type": str(ship_type) if ship_type is not None else None,
        "destination": str(voyage.get("Destination") or "").strip() or None,
        "ts": _parse_time(_meta_value(meta, "Time", "time_utc", "time")) or datetime.now(timezone.utc),
    }


class _Publisher:
    """Rate-limits the full-list push without dropping the last state."""

    def __init__(self, interval: float = PUBLISH_INTERVAL_S) -> None:
        self._interval = interval
        self._last = 0.0
        self._pending = False

    def mark(self) -> None:
        self._pending = True

    def flush(self, force: bool = False) -> bool:
        if not self._pending:
            return False
        now = time.monotonic()
        if not force and now - self._last < self._interval:
            return False
        self._last = now
        self._pending = False
        try:
            return ais_service.publish_targets()
        except Exception:  # noqa: BLE001 — a dead broker must not stop the feed
            logger.warning("could not publish AIS targets", exc_info=True)
            return False


async def handle_message(update: dict, publisher: _Publisher) -> bool:
    """Persist one AISStream update. Returns True when something was stored."""
    if not isinstance(update, dict):
        return False
    message_type = update.get("MessageType")

    if message_type == "PositionReport":
        payload = extract_position(update)
        if payload is None:
            return False
        written = ais_service.write_target(**payload)
    elif message_type == "ShipStaticData":
        payload = extract_static(update)
        if payload is None:
            return False
        written = ais_service.write_target(**payload)
    else:
        return False

    if written:
        publisher.mark()
    return written


async def _stream() -> None:
    import websockets

    logger.info("AIS relay connecting to %s", STREAM_URL)
    # permessage-deflate: AISStream serves full message bandwidth only when
    # compression is negotiated.
    async with websockets.connect(
        STREAM_URL, max_size=8 * 1024 * 1024, compression="deflate",
        open_timeout=10, ping_interval=20, ping_timeout=20,
    ) as socket:
        frame = subscription()
        await socket.send(json.dumps(frame))
        logger.info(
            "AIS relay subscribed: %d bounding box(es)",
            len(frame["BoundingBoxes"]),
        )
        publisher = _Publisher()
        # Push whatever the API would already return, so a channel that
        # connects before the first message has something honest to show.
        publisher.mark()
        publisher.flush(force=True)

        while True:
            raw = await socket.recv()
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            try:
                update = json.loads(raw)
            except ValueError:
                logger.warning("AIS relay received a non-JSON frame; dropped")
                continue
            try:
                await handle_message(update, publisher)
            except Exception:  # noqa: BLE001 — one bad message is not a outage
                logger.exception("AIS relay could not process a message")
            publisher.flush()


async def run_ais_relay() -> None:
    """Long-running task: connect, stream, reconnect with capped backoff."""
    settings = get_settings()
    key = settings.AISSTREAM_API_KEY
    if not key:
        logger.info("AIS relay not started: AISSTREAM_API_KEY is not set")
        return

    delay = RECONNECT_MIN_S
    while True:
        try:
            await _stream()
            delay = RECONNECT_MIN_S
        except asyncio.CancelledError:
            logger.info("AIS relay stopped")
            raise
        except Exception:  # noqa: BLE001 — the stream drops routinely
            logger.warning(
                "AIS relay disconnected; reconnecting in %ss", delay, exc_info=True
            )
        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX_S)
