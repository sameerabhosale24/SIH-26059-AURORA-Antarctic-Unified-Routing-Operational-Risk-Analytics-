/**
 * A single weather / wave / ocean-current observation at a point in space
 * and time, pushed over `WS /ws/weather` (5 min cadence).
 *
 * Every measurement is `| null`; the UI renders an em dash, never `0`.
 */
export interface WeatherPoint {
  ts: string;
  lat: number;
  lon: number;
  wind_speed: number | null;
  /** Direction wind is coming FROM, degrees true. */
  wind_dir: number | null;
  wave_height: number | null;
  wave_dir: number | null;
  current_speed: number | null;
  current_dir: number | null;
  air_temp: number | null;
  source: string;
}
