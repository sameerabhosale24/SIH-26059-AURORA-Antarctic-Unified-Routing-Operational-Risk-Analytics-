"""Reads and bumps the ``data_version`` ledger.

Deliberately synchronous. The consumers are APScheduler worker threads
(:func:`bump`, from the daily jobs) and the health endpoint, which calls
these through ``asyncio.to_thread``. Driving the *async* engine from a
freshly-created event loop per job would rebind pooled connections to a
different loop on every run, so the scheduler path uses its own sync engine
instead.

Two invariants the rest of the system relies on:

* ``version`` only ever increases, and only after a *successful* ingest.
  A failed run leaves the row untouched, so an unchanged version always
  means "nothing new happened".
* ``version == 0`` means "seeded, never fetched". Health reports
  ``last_fetch: null`` for those rows rather than the seed timestamp,
  because reporting the migration time as a fetch time would be a lie.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import VERSION_KEYS, DataVersion

logger = logging.getLogger("aurora.version")

_engine: Engine | None = None
_session_factory: sessionmaker | None = None

#: Keys that are fed by an adapter, mapped to the source that produces them.
SOURCE_VERSION_KEYS = {
    "nsidc": "sic",
    "era5": "weather",
    "cmems": "currents",
    "cs2smos": "ice_thickness",
    "ibcso": "bathymetry",
    "byu_scp": "icebergs",
}


def get_sync_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        # Same database, sync driver. The +asyncpg suffix is the only thing
        # that differs, and deriving it here keeps a single DATABASE_URL.
        url = get_settings().DATABASE_URL.replace("+asyncpg", "+psycopg2")
        _engine = create_engine(url, pool_pre_ping=True)
        _session_factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def _session() -> Session:
    get_sync_engine()
    assert _session_factory is not None
    return _session_factory()


def open_session() -> Session:
    """A fresh sync session the caller is responsible for closing.

    Shared by the scheduler and the SIC cycle so every write in a job goes
    through one engine.
    """
    return _session()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def get(key: str, session: Session | None = None) -> DataVersion | None:
    if session is not None:
        return session.get(DataVersion, key)
    with _session() as owned:
        return owned.get(DataVersion, key)


def get_all(session: Session | None = None) -> dict[str, DataVersion]:
    owned = session or _session()
    rows = owned.execute(select(DataVersion).order_by(DataVersion.key)).scalars().all()
    return {row.key: row for row in rows}


def last_fetch_for(key: str | None) -> str | None:
    """ISO timestamp of the last successful ingest, or ``None``.

    ``None`` covers both "never fetched" and "unknown key" — the health
    endpoint cannot tell the difference and should not pretend it can.
    """
    if not key:
        return None
    return last_fetch_map([key]).get(key)


def last_fetch_map(keys: Iterable[str]) -> dict[str, str | None]:
    """One query for every key health needs, instead of one query per source."""
    wanted = [key for key in keys if key]
    result: dict[str, str | None] = {key: None for key in wanted}
    if not wanted:
        return result
    try:
        with _session() as session:
            rows = (
                session.execute(select(DataVersion).where(DataVersion.key.in_(wanted)))
                .scalars()
                .all()
            )
    except Exception:  # noqa: BLE001 — health must never fail on a read
        logger.exception("could not read data_version for %s", wanted)
        return result
    for row in rows:
        result[row.key] = _iso(row.updated_at) if row.version > 0 else None
    return result


def bump(
    key: str,
    *,
    source_ts: datetime | None = None,
    staleness: dict | None = None,
    notes: str | None = None,
) -> dict:
    """Increment ``key`` and return the resulting row as a plain dict.

    The increment is done in SQL (``version = version + 1``) so two
    schedulers racing on the same key cannot lose an update.
    """
    if key not in VERSION_KEYS:
        raise ValueError(f"unknown data_version key {key!r}; expected one of {VERSION_KEYS}")

    now = datetime.now(timezone.utc)
    with _session() as session:
        row = session.execute(
            update(DataVersion)
            .where(DataVersion.key == key)
            .values(
                version=DataVersion.version + 1,
                updated_at=now,
                source_ts=source_ts,
                staleness=staleness,
                notes=notes,
            )
            .returning(DataVersion)
        ).scalar_one_or_none()

        if row is None:
            # A row should exist from the migration seed; if the database was
            # built some other way, create it rather than losing the bump.
            logger.warning("data_version row %r missing; inserting it", key)
            session.execute(
                insert(DataVersion).values(
                    key=key, version=1, updated_at=now,
                    source_ts=source_ts, staleness=staleness, notes=notes,
                )
            )
            row = session.get(DataVersion, key)

        payload = {
            "key": row.key,
            "version": row.version,
            "updated_at": _iso(row.updated_at),
            "source_ts": _iso(row.source_ts),
            "staleness": row.staleness,
            "notes": row.notes,
        }
        session.commit()

    logger.info("data_version[%s] -> %s", key, payload["version"])
    return payload
