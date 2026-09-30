import type { LineString } from 'geojson';

/** A named waypoint along a route. */
export interface Waypoint {
  id: number;
  seq: number;
  lat: number;
  lon: number;
  name: string | null;
  /** ISO 8601 ETA, or null when the optimiser could not produce one. */
  eta: string | null;
}

/**
 * One candidate route. The backend returns primary and alternative routes in
 * the same array; `is_recommended` marks the AI-recommended one.
 */
export interface Route {
  id: number;
  route_run_id: number;
  label: string;
  /** WGS84 line geometry. */
  geometry: LineString;
  distance_nm: number;
  eta: string;
  /** Fuel estimate, tonnes. */
  fuel_estimate_t: number;
  /** Normalised 0..1 risk score; higher is worse. */
  risk_score: number;
  is_recommended: boolean;
  waypoints: Waypoint[];
}

/** One routing run: a set of candidate routes computed at a point in time. */
export interface RouteRun {
  id: number;
  vessel_id: string;
  run_ts: string;
  /** Input data versions the run was computed against (sic/weather/icebergs). */
  input_version: Record<string, number>;
  status: 'optimal' | 'infeasible' | 'degraded';
  routes: Route[];
}
