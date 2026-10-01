"""BYU Sea Ice Change Program iceberg listings.

Unlike every other adapter this one produces records, not a grid: an
iceberg is a point with an identity, and forcing it onto the SIC grid would
destroy the one thing we need — which iceberg is where. The rows go
straight into ``iceberg_position`` with their native lat/lon.

``regrid`` therefore raises. There is no right answer for "the grid
version of an iceberg", and a silently empty array would look exactly like
"no icebergs", which is the most dangerous possible ambiguity in this
system.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from typing import Any

from app.adapters.base import DataSource
from app.config import get_settings

DEFAULT_URL = "https://scp.byu.edu/iceberg_listings/recent_icebergs.php"


class _TableParser(HTMLParser):
    """Extract rows from the first HTML table on the page."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_table = 0
        self._table_count = 0
        self._captured_tables = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._in_table += 1
            self._table_count += 1
            if self._table_count > 1 and self._captured_tables >= 1:
                self._in_table = -1  # stop after the first populated table
        elif tag == "tr" and self._in_table == 1:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._in_table > 0:
                self._in_table -= 1
            if self._in_table == 1 and self._row:
                self.rows.append(self._row)
                self._row = None
                self._captured_tables += 1
                self._in_table = -1
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(_clean(" ".join(self._cell)))
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _to_float(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def _find_column(headers: list[str], *needles: str) -> int | None:
    for index, header in enumerate(headers):
        lowered = header.lower()
        if any(needle in lowered for needle in needles):
            return index
    return None


class BYUSCPAdapter(DataSource):
    name = "byu_scp"
    label = "BYU SCP (icebergs)"

    def version_key(self) -> str:
        return "icebergs"

    def is_configured(self) -> bool:
        return bool(get_settings().BYU_SCP_URL)

    async def fetch(self, day: date) -> Any:
        self._require_configured()
        settings = get_settings()
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for the BYU SCP adapter") from exc

        url = settings.BYU_SCP_URL or DEFAULT_URL
        self.logger.info("scraping icebergs from %s", url)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            body = response.text

        return self.parse(body, url=url, as_of=day)

    def parse(self, body: str, *, url: str, as_of: date | None = None) -> list[dict]:
        """Turn the page into iceberg records. CSV first, then an HTML table."""
        rows, _is_csv = self._rows_from_csv(body)
        if not rows:
            rows = self._rows_from_html(body)
        if len(rows) < 2:
            raise ValueError(
                f"could not find a populated table at {url}; the page layout "
                "may have changed"
            )

        headers = [h.lower() for h in rows[0]]
        id_col = _find_column(headers, "id", "name", "label")
        lat_col = _find_column(headers, "lat")
        lon_col = _find_column(headers, "lon", "lng", "long")
        length_col = _find_column(headers, "length", "size")
        if lat_col is None or lon_col is None:
            raise ValueError(
                f"no latitude/longitude columns recognised in headers {headers}"
            )

        if as_of is not None:
            stamp = datetime.combine(as_of, time(0, 0), tzinfo=timezone.utc).isoformat()
        else:
            stamp = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []
        for number, row in enumerate(rows[1:], start=1):
            if len(row) <= max(lat_col, lon_col):
                continue
            lat = _to_float(row[lat_col])
            lon = _to_float(row[lon_col])
            if lat is None or lon is None:
                self.logger.debug("skipping unparseable row %d: %r", number, row)
                continue
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                self.logger.debug("skipping out-of-range row %d: (%s, %s)", number, lat, lon)
                continue
            identifier = row[id_col] if id_col is not None and id_col < len(row) else None
            records.append(
                {
                    "iceberg_id": identifier or f"{as_of or 'unknown'}-{number}",
                    "lat": lat,
                    "lon": lon,
                    "length_km": _to_float(row[length_col]) if length_col is not None else None,
                    "source": url,
                    "ts": stamp,
                }
            )
        self.logger.info("parsed %d iceberg records", len(records))
        return records

    @staticmethod
    def _rows_from_csv(body: str) -> tuple[list[list[str]], bool]:
        stripped = body.lstrip()
        if "," not in stripped.split("\n", 1)[0]:
            return [], False
        try:
            reader = csv.reader(io.StringIO(stripped))
            rows = [[_clean(cell) for cell in row] for row in reader]
        except csv.Error:
            return [], False
        rows = [row for row in rows if any(cell for cell in row)]
        return rows, True

    @staticmethod
    def _rows_from_html(body: str) -> list[list[str]]:
        parser = _TableParser()
        parser.feed(body)
        return parser.rows

    def regrid(self, raw: Any) -> np.ndarray:
        raise NotImplementedError(
            "BYU SCP icebergs are native lat/lon points and are never "
            "regridded; write them to the iceberg_position table instead"
        )
