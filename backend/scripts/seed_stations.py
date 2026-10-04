"""Publish station reference data for the map.

    python scripts/seed_stations.py [--force]

Writes ``data/stations.json``, which ``GET /api/stations`` serves verbatim.
Stations are reference metadata — a name, a flag and a position — not a
measurement, so seeding them is the one place AURORA writes coordinates
that did not come from a sensor.

Only stations that matter to an AURORA voyage are listed: everything
inside the ROI the map draws, plus Cape Town, which is the departure port
the optimiser starts from and sits just outside the ROI. Every coordinate
is the published position of the real facility; nothing is interpolated,
derived or averaged.

Idempotent: an existing file is reported and left alone unless ``--force``
is given, so rerunning cannot silently overwrite a station list an
operator has edited.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_BACKEND))

from app.services.field_storage import storage_root  # noqa: E402

FILENAME = "stations.json"

#: ``(id, name, country, lat, lon)``
#:
#: Every entry inside the ROI except Cape Town, which is the supply port the
#: route optimiser departs from and is included because an operator looking
#: for "where does this voyage start" should find it in the same list.
STATIONS: tuple[tuple[str, str, str, float, float], ...] = (
    ("maitri", "Maitri", "India", -70.7664, 11.7339),
    ("bharati", "Bharati", "India", -69.3970, 76.2470),
    ("novolazarevskaya", "Novolazarevskaya", "Russia", -70.7667, 11.8333),
    ("progress", "Progress", "Russia", -69.3750, 76.3833),
    ("syowa", "Syowa", "Japan", -69.0033, 39.5833),
    ("neumayer", "Neumayer III", "Germany", -70.6500, -8.2667),
    ("troll", "Troll", "Norway", -72.0167, 2.5333),
    ("san-martin", "San Martin", "Argentina", -68.1333, -67.1333),
    ("rothera", "Rothera", "United Kingdom", -67.5667, -68.1333),
    ("esperanza", "Esperanza", "Argentina", -63.4000, -57.0000),
    ("marambio", "Marambio", "Argentina", -64.2333, -56.7167),
    ("cape-town", "Cape Town", "South Africa", -33.9250, 18.4238),
)


def records() -> list[dict]:
    return [
        {"id": station_id, "name": name, "country": country, "lat": lat, "lon": lon}
        for station_id, name, country, lat, lon in STATIONS
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write data/stations.json")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing stations file instead of leaving it alone",
    )
    args = parser.parse_args(argv)

    path = storage_root() / FILENAME
    if path.exists() and not args.force:
        print(f"Stations file already exists: {path} (use --force to overwrite)")
        return 0

    payload = records()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(payload)} station(s) to {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — report and exit non-zero
        print(f"Seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
