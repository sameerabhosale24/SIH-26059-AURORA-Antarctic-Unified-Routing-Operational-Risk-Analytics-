/**
 * Display formatters.
 *
 * Rule for the whole app: missing data renders as an em dash (`—`).
 * A zero is a real measurement and must never be used to mean "unknown".
 */

/** Placeholder for absent data. Never replace this with `0`. */
export const EM_DASH = '—';

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Fixed-decimal number, or `—` when null/undefined/NaN/Infinity.
 */
export function fmtNum(v: number | null | undefined, digits = 1): string {
  if (!isFiniteNumber(v)) return EM_DASH;
  return v.toFixed(digits);
}

/**
 * Signed fixed-decimal number (e.g. `+2.4`), or `—`.
 */
export function fmtSigned(v: number | null | undefined, digits = 1): string {
  if (!isFiniteNumber(v)) return EM_DASH;
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}`;
}

/**
 * Latitude/longitude in signed degrees with hemisphere letter, or `—`.
 *
 * `lat` is rendered `DD° MM.mmm'S'`-free on purpose: navigators read absolute
 * degrees here, so output is compact (`61.2345°S`).
 */
export function fmtCoord(v: number | null | undefined, axis: 'lat' | 'lon' = 'lon'): string {
  if (!isFiniteNumber(v)) return EM_DASH;

  const hemisphere =
    axis === 'lat' ? (v < 0 ? 'S' : 'N') : v < 0 ? 'W' : v === 0 ? '' : 'E';

  return `${Math.abs(v).toFixed(4)}°${hemisphere}`;
}

/**
 * Latitude/longitude pair from separate components, or `—` if either is absent.
 */
export function fmtPosition(
  lat: number | null | undefined,
  lon: number | null | undefined,
): string {
  if (!isFiniteNumber(lat) || !isFiniteNumber(lon)) return EM_DASH;
  return `${fmtCoord(lat, 'lat')} ${fmtCoord(lon, 'lon')}`;
}

/**
 * True bearing in degrees (`045°T`), normalised to 0..359, or `—`.
 *
 * Bearings are unsigned compass angles with no hemisphere, so they cannot go
 * through `fmtCoord` — which would turn `350` into `350°N` and `045` into
 * `45°E`.
 */
export function fmtBearing(v: number | null | undefined): string {
  if (!isFiniteNumber(v)) return EM_DASH;
  const normalised = ((v % 360) + 360) % 360;
  return `${normalised.toFixed(0).padStart(3, '0')}°T`;
}

/**
 * UTC clock time (`HH:MM:SSZ`), or `—`.
 *
 * Alarms, positions and forecast rows are all UTC; the UI never renders local
 * time for operational data.
 */
export function fmtTime(iso: string | null | undefined): string {
  const date = toDate(iso);
  if (!date) return EM_DASH;
  return `${date.toISOString().slice(11, 19)}Z`;
}

/**
 * Full UTC timestamp (`YYYY-MM-DD HH:MM:SSZ`), or `—`.
 */
export function fmtDateTime(iso: string | null | undefined): string {
  const date = toDate(iso);
  if (!date) return EM_DASH;
  return `${date.toISOString().slice(0, 10)} ${date.toISOString().slice(11, 19)}Z`;
}

/**
 * Compact UTC calendar day (`MM-DD`), or `—`.
 */
export function fmtDate(iso: string | null | undefined): string {
  const date = toDate(iso);
  if (!date) return EM_DASH;
  return date.toISOString().slice(5, 10);
}

/**
 * Human-readable age: `5s ago`, `3m ago`, `2h ago`, `1d ago`.
 * Negative or null ages render as `—`.
 */
export function fmtAge(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds) || seconds < 0) return EM_DASH;

  const s = Math.floor(seconds);

  if (s < 60) return `${s}s ago`;

  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  return `${Math.floor(hours / 24)}d ago`;
}

/**
 * Duration in seconds as a compact length: `45s`, `12m`, `3h 20m`, `2d 4h`.
 */
export function fmtDuration(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds) || seconds < 0) return EM_DASH;

  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;

  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes}m`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rem = minutes % 60;
    return rem === 0 ? `${hours}h` : `${hours}h ${rem}m`;
  }

  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours === 0 ? `${days}d` : `${days}d ${remHours}h`;
}

function toDate(iso: string | null | undefined): Date | null {
  if (typeof iso !== 'string' || iso.trim() === '') return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}
