"""One-off proof that NSIDC, CMEMS and ERA5 fetch + regrid to the SIC grid.

Throwaway. Not wired into the scheduler, writes no database rows, and it
never fabricates a field: a source that fails is reported verbatim and its
file is simply not written.

Usage::

    python scripts/test_fetch_one_day.py --date 2026-09-25
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from datetime import date, timedelta

import numpy as np

from app.adapters import ERA5Adapter, CMEMSAdapter, NSIDCAdapter
from app.services.field_storage import write_field

CREDENTIAL_HINTS = {
    "nsidc": (
        "NSIDC_USERNAME / NSIDC_PASSWORD in backend/.env",
        "If NSIDC returns 401, the Earthdata application authorization is "
        "missing: authorize your apps at "
        "urs.earthdata.nasa.gov/profile -> Applications.",
    ),
    "cmems": (
        "CMEMS_USERNAME / CMEMS_PASSWORD in backend/.env",
        "If CMEMS returns 401, the credentials are wrong: check "
        "marine.copernicus.eu.",
    ),
    "era5": (
        "CDSAPI_URL / CDSAPI_KEY in backend/.env",
        "If CDS returns 403, the API key is wrong or the licence is not "
        "accepted: accept the ERA5 licence at cds.climate.copernicus.eu.",
    ),
}


def _status_of(exc: BaseException) -> int | None:
    """HTTP status code carried by the exception, when there is one."""
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    text = str(exc)
    for candidate in (401, 403, 404, 429, 500):
        if str(candidate) in text:
            return candidate
    return None


def _report_stats(label: str, array: np.ndarray, path) -> None:
    finite = array[np.isfinite(array)]
    print(f"[{label}] path:      {path}")
    print(f"[{label}] shape:     {array.shape}  dtype: {array.dtype}")
    if finite.size:
        print(
            f"[{label}] min/max/mean: {float(finite.min()):.6g} / "
            f"{float(finite.max()):.6g} / {float(finite.mean()):.6g}"
        )
    else:
        print(f"[{label}] min/max/mean: all-NaN ({finite.size} finite values)")
    print(f"[{label}] NaN count: {int(np.isnan(array).sum())} / {array.size}")
    if array.ndim == 3:
        for channel, frame in enumerate(array):
            ch = frame[np.isfinite(frame)]
            if ch.size:
                print(
                    f"[{label}]   ch{channel}: min {float(ch.min()):.6g} "
                    f"max {float(ch.max()):.6g} mean {float(ch.mean()):.6g} "
                    f"NaN {int(np.isnan(frame).sum())}"
                )
            else:
                print(f"[{label}]   ch{channel}: all-NaN")


async def _run(label: str, adapter, storage_name: str, day: date) -> bool:
    """Fetch, regrid, write. True when a file landed on disk."""
    credentials, hint = CREDENTIAL_HINTS[label]
    if not adapter.is_configured():
        print(f"[{label}] SKIPPED — not configured; credential missing: {credentials}")
        return False

    print(f"[{label}] fetching {day.isoformat()} ...")
    try:
        raw = await adapter.fetch(day)
        array = adapter.regrid(raw)
    except NotImplementedError:
        print(f"[{label}] SKIPPED — NotImplementedError; credential missing: {credentials}")
        return False
    except BaseException as exc:  # noqa: BLE001 — report, never fabricate
        status = _status_of(exc)
        print(f"[{label}] FAILED — {type(exc).__name__}: {exc}")
        if status is not None:
            print(f"[{label}] HTTP status: {status}")
            print(f"[{label}] {hint}")
        traceback.print_exc()
        return False

    path = write_field(storage_name, day, array)
    _report_stats(label, array, path)
    return True


async def main(date_arg: str | None) -> int:
    day = date.fromisoformat(date_arg) if date_arg else (date.today() - timedelta(days=1))
    era5_day = day - timedelta(days=5)

    print(f"request date:   {day.isoformat()}")
    print(f"ERA5T date:     {era5_day.isoformat()}  (date - 5 days, 5-day lag)")
    print("")

    # Each source is independent: a failure in one is reported verbatim and
    # the next is still attempted, so the report says exactly which sources
    # work. Whichever files succeed are written; nothing else runs after.
    results = {
        "nsidc": await _run("nsidc", NSIDCAdapter(), "sic", day),
        "cmems": await _run("cmems", CMEMSAdapter(), "currents", day),
        "era5": await _run("era5", ERA5Adapter(), "weather", era5_day),
    }

    print("")
    print("=== summary ===")
    for label, ok in results.items():
        print(f"{label}: {'OK' if ok else 'FAILED'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.date)))
