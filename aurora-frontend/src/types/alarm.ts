/**
 * An operational alarm.
 *
 * Alarms arrive over `WS /ws/alarms` and are acked via
 * `POST /api/alarms/{id}/ack`.
 */
export interface Alarm {
  id: number;
  ts: string;
  vessel_id: string;
  severity: 'critical' | 'warning' | 'caution';
  type: 'ukc' | 'collision' | 'ice' | 'iceberg' | 'off_course' | 'forecast_stale';
  message: string;
  /** Alarm location; null for vessel-wide or data-quality alarms. */
  lat: number | null;
  lon: number | null;
  /** Alarm-type-specific context from the backend. */
  payload: Record<string, unknown>;
  acked_at: string | null;
  acked_by: string | null;
}
