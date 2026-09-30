import type { Polygon } from 'geojson';

/**
 * A tracked iceberg with its forecast drift cone.
 *
 * `drift_cone` is a WGS84 GeoJSON polygon; null when the backend has not
 * computed a cone for this iceberg.
 */
export interface Iceberg {
  id: string;
  ts: string;
  lat: number;
  lon: number;
  /** Major axis length, kilometres. */
  length_km: number | null;
  /** Drift bearing, degrees true. */
  drift_bearing: number | null;
  /** Drift speed, knots. */
  drift_speed_kt: number | null;
  source: string;
  drift_cone: Polygon | null;
  /** Containment probability of `drift_cone`, 0..1. */
  drift_cone_probability: number | null;
}
