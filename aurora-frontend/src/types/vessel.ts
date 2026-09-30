/**
 * Own-ship state, pushed at 1 Hz over `WS /ws/vessel`.
 *
 * `vessel_id`, `ts`, `lat` and `lon` are always present (a position is the
 * payload). Every derived/optional measurement is `| null` and the UI must
 * render an em dash — never `0` — when it is null.
 */
export interface VesselState {
  vessel_id: string;
  ts: string;
  lat: number;
  lon: number;
  /** Speed over ground, knots. */
  sog: number | null;
  /** Course over ground, degrees true. */
  cog: number | null;
  /** Heading, degrees true. */
  heading: number | null;
  /** Rate of turn, degrees/min. */
  rot: number | null;
  /** Draught, metres. */
  draft: number | null;
  /** Under-keel clearance, metres. */
  ukc: number | null;
  fuel_remaining: number | null;
  /** Engine load, percent. */
  engine_load: number | null;
  /** True wind speed, m/s. */
  wind_speed: number | null;
  /** True wind direction, degrees true (direction wind is coming FROM). */
  wind_dir: number | null;
  source: 'gps' | 'manual' | 'estimated';
}
