/**
 * A single AIS target.
 *
 * Pushed over `WS /ws/ais`. CPA/TCPA and the derived `risk` band are computed
 * backend-side and included in the payload — the frontend never recomputes
 * collision risk.
 */
export interface AisTarget {
  mmsi: number;
  name: string | null;
  ship_type: string | null;
  lat: number;
  lon: number;
  /** Speed over ground, knots. */
  sog: number | null;
  /** Course over ground, degrees true. */
  cog: number | null;
  heading: number | null;
  destination: string | null;
  ts: string;
  /** Closest point of approach, nautical miles. */
  cpa_nm: number | null;
  /** Time to closest point of approach, minutes. */
  tcpa_min: number | null;
  risk: 'none' | 'low' | 'medium' | 'high' | null;
}
