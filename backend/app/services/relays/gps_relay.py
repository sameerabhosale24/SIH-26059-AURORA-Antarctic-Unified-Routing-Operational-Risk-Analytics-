"""Own-ship GPS relay: NMEA 0183 over TCP into ``vessel_state``.

A relay, not a job. It opens one socket, parses sentences as they arrive,
writes a telemetry row for each accepted fix and publishes it on
``vessel.updated``, then reopens the socket when the feed drops.

Parsing rules, in order of importance:

* a sentence with a bad checksum is discarded — a garbled position is worse
  than a missing one, because a missing one is visibly missing;
* ``$--RMC`` is the sentence of record (position, speed, course and date);
  GGA supplies position and time when only that is being broadcast, VTG
  supplies speed and course, HDT supplies heading when a heading sensor
  exists;
* nothing is invented. There is no draft, UKC or fuel in NMEA, so those
  columns stay ``NULL`` rather than being copied from the blueprint, where
  they would read as a live measurement of a configured number.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import get_settings
from app.services import vessel_service

logger = logging.getLogger("aurora.relay.gps")

#: Never write more often than this, even if the feed runs faster.
MIN_WRITE_INTERVAL_S = 1.0
#: A fix whose position falls outside this box is a parser bug, not a ship.
MAX_LAT, MAX_LON = 90.0, 180.0


@dataclass
class Fix:
    """Accumulated state from the sentences seen since the last flush."""

    lat: float | None = None
    lon: float | None = None
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    ts: datetime | None = None
    dirty: bool = field(default=False)

    @property
    def complete(self) -> bool:
        return (
            self.lat is not None
            and self.lon is not None
            and self.ts is not None
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def checksum_ok(line: str) -> bool:
    """True when the sentence carries no checksum, or carries a valid one."""
    if "*" not in line:
        return True  # some gateways strip it; the payload is still usable
    payload, _, digest = line.rpartition("*")
    payload = payload.lstrip("$")
    try:
        expected = int(digest.strip()[:2], 16)
    except ValueError:
        return False
    total = 0
    for char in payload:
        total ^= ord(char)
    return total == expected


def parse_dm(raw: str, degrees_length: int) -> float | None:
    """``ddmm.mmmm`` / ``dddmm.mmmm`` plus a hemisphere to signed degrees."""
    raw = raw.strip()
    if len(raw) <= degrees_length:
        return None
    try:
        whole = float(raw[:degrees_length])
        minutes = float(raw[degrees_length:])
    except ValueError:
        return None
    value = whole + minutes / 60.0
    if not math.isfinite(value):
        return None
    return value


def parse_float(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_nmea_time(raw: str) -> str | None:
    """``hhmmss.ss`` -> ``"hh:mm:ss"``, or ``None`` when unusable."""
    raw = (raw or "").strip()
    if len(raw) < 6:
        return None
    try:
        hours = int(raw[0:2])
        minutes = int(raw[2:4])
        seconds = float(raw[4:])
    except ValueError:
        return None
    if not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 61):
        return None
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d}"


def parse_nmea_date(raw: str) -> str | None:
    """``ddmmyy`` -> ``"YYYY-MM-DD"``. Two-digit years use the NMEA window
    1980-2079, which is what every receiver in service implements."""
    raw = (raw or "").strip()
    if len(raw) != 6:
        return None
    try:
        day = int(raw[0:2])
        month = int(raw[2:4])
        year = int(raw[4:6]) + 2000
        if year >= 2080:
            year -= 100
    except ValueError:
        return None
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _utc_from(date_part: str | None, time_part: str | None) -> datetime | None:
    if time_part is None:
        return None
    if date_part is None:
        # No date in this sentence. The time is still real, so stamp it with
        # today rather than dropping the fix — but say so in the log once.
        date_part = datetime.now(timezone.utc).date().isoformat()
    try:
        stamp = datetime.fromisoformat(f"{date_part}T{time_part}+00:00")
    except ValueError:
        return None
    return stamp


def apply_sentence(fix: Fix, line: str) -> Fix:
    """Fold one NMEA sentence into ``fix``. Returns the same object."""
    line = line.strip()
    if not line.startswith("$") or not checksum_ok(line):
        return fix

    body = line[1:].split("*", 1)[0]
    parts = body.split(",")
    if len(parts) < 2:
        return fix
    sentence = parts[0]
    if len(sentence) < 5:
        return fix
    kind = sentence[-3:]

    if kind == "RMC" and len(parts) >= 10:
        if parts[2].strip().upper() == "V":
            return fix  # receiver reports the fix void
        lat = _hemisphere(parts[3], parts[4], 2)
        lon = _hemisphere(parts[5], parts[6], 3)
        if lat is not None and lon is not None:
            fix.lat, fix.lon = lat, lon
            fix.ts = _utc_from(parse_nmea_date(parts[9]), parse_nmea_time(parts[1]))
        fix.sog = parse_float(parts[7])
        fix.cog = parse_float(parts[8])
        fix.dirty = True

    elif kind == "GGA" and len(parts) >= 6:
        quality = parse_float(parts[6])
        if quality is not None and quality <= 0:
            return fix  # no fix
        lat = _hemisphere(parts[2], parts[3], 2)
        lon = _hemisphere(parts[4], parts[5], 3)
        if lat is not None and lon is not None:
            fix.lat, fix.lon = lat, lon
            if fix.ts is None:
                fix.ts = _utc_from(None, parse_nmea_time(parts[1]))
            fix.dirty = True

    elif kind == "VTG" and len(parts) >= 8:
        fix.cog = parse_float(parts[1])
        fix.sog = parse_float(parts[5])
        fix.dirty = True

    elif kind == "HDT" and len(parts) >= 2:
        heading = parse_float(parts[1])
        if heading is not None:
            fix.heading = heading % 360.0
            fix.dirty = True

    return fix


def _hemisphere(raw: str, hemi: str, degrees_length: int) -> float | None:
    value = parse_dm(raw, degrees_length)
    if value is None:
        return None
    hemi = (hemi or "").strip().upper()
    if hemi in ("S", "W"):
        value = -value
    elif hemi not in ("N", "E"):
        return None
    return value


def fix_is_sane(fix: Fix) -> bool:
    """Reject parser output before it reaches the database."""
    if fix.lat is None or fix.lon is None:
        return False
    if not (abs(fix.lat) <= MAX_LAT and abs(fix.lon) <= MAX_LON):
        return False
    if fix.sog is not None and fix.sog < 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Relay
# ---------------------------------------------------------------------------
def store_fix(fix: Fix) -> bool:
    """Write one fix. Returns False when it was rejected or the write failed."""
    if not fix.complete or not fix_is_sane(fix):
        logger.warning("discarding an incomplete or implausible fix: %s", fix)
        return False
    row = vessel_service.write_state(
        vessel_id=get_settings().OWN_SHIP_VESSEL_ID,
        lat=float(fix.lat),
        lon=float(fix.lon),
        sog=fix.sog,
        cog=fix.cog,
        heading=fix.heading,
        source="gps",
        ts=fix.ts,
    )
    if row is None:
        return False
    logger.debug(
        "fix stored: %.5f,%.5f sog=%s cog=%s ts=%s",
        fix.lat, fix.lon, fix.sog, fix.cog, fix.ts,
    )
    return True


async def _stream(host: str, port: int) -> None:
    """Read one connection until it ends or the task is cancelled."""
    logger.info("GPS relay connecting to %s:%s", host, port)
    reader, writer = await asyncio.open_connection(host, port)
    logger.info("GPS relay connected to %s:%s", host, port)

    fix = Fix()
    last_write = 0.0
    loop = asyncio.get_running_loop()
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                logger.warning("GPS relay: peer closed the connection")
                return
            try:
                line = raw.decode("ascii", errors="ignore")
            except Exception:  # pragma: no cover — decode above never raises
                continue
            fix = apply_sentence(fix, line)
            if not fix.dirty or not fix.complete:
                continue
            now = loop.time()
            if now - last_write < MIN_WRITE_INTERVAL_S:
                continue
            if store_fix(fix):
                last_write = now
                fix.dirty = False
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 — the peer may already be gone
            pass


async def run_gps_relay() -> None:
    """Long-running task: connect, stream, reconnect with a fixed backoff.

    Returns immediately and logs when the relay is not configured, so the
    application lifespan can start it unconditionally.
    """
    settings = get_settings()
    host, port = settings.GPS_HOST, settings.GPS_PORT
    if not host or not port:
        logger.info("GPS relay not started: GPS_HOST/GPS_PORT are not set")
        return

    backoff = max(int(settings.RELAY_RECONNECT_SECONDS), 1)
    while True:
        try:
            await _stream(str(host), int(port))
        except asyncio.CancelledError:
            logger.info("GPS relay stopped")
            raise
        except Exception:  # noqa: BLE001 — a dead feed is retried, never fatal
            logger.exception("GPS relay failed; reconnecting in %ss", backoff)
        await asyncio.sleep(backoff)
