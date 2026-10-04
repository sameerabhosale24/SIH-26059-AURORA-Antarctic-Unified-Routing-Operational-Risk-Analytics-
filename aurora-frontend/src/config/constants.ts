/**
 * Tunable constants for the AURORA frontend.
 *
 * Everything here is backend-agnostic configuration. Change values here rather
 * than in component or store code.
 */

/**
 * How old a data source may be before the UI flags it as STALE, in seconds.
 *
 * Keys map to logical sources, not to store names — use `useStaleness(key)`.
 */
export const STALENESS_THRESHOLDS = {
  /** Own-ship GPS / nav data stream. */
  GPS: 5,
  /** AIS target stream. */
  AIS: 60,
  /** Weather, wave and current stream. */
  weather: 1800,
  /** Sea-ice-concentration forecast product. */
  SIC: 129600,
  /** Iceberg positions and drift cones. */
  icebergs: 172800,
  /** Computed route set. */
  route: 21600,
  /** Electronic navigational chart dataset. */
  enc: 2592000,
} as const;

export type StalenessSource = keyof typeof STALENESS_THRESHOLDS;

/**
 * Human-readable update cadence labels, shown in the UI (Part 2).
 */
export const UPDATE_CADENCE = {
  sic: 'Daily',
  route: '6 hours',
  ais: 'Real-time',
  vessel: 'Real-time',
  weather: '5 minutes',
  icebergs: 'Daily',
} as const;

export type UpdateCadenceKey = keyof typeof UPDATE_CADENCE;

/** Poll interval for `GET /api/version` — 10 minutes. */
export const VERSION_POLL_INTERVAL_MS = 600_000;

/** WebSocket exponential-backoff base delay — 1s. */
export const WS_RECONNECT_BASE_MS = 1_000;

/** WebSocket exponential-backoff cap — 30s. */
export const WS_RECONNECT_MAX_MS = 30_000;

/** Re-render cadence for `useStaleness` so STALE badges appear without a manual refresh. */
export const STALENESS_TICK_MS = 1_000;

/** Map "follow own ship" behaviour. */
export const FOLLOW_SHIP = {
  /** Minimum interval between two re-centres, in ms (debounce). */
  MIN_INTERVAL_MS: 1_000,
  /** Duration of the re-centre animation, in ms. */
  ANIMATION_MS: 300,
  /** Radius, in nautical miles, framed by the `local` projection preset. */
  LOCAL_RADIUS_NM: 200,
  /** Padding, in px, when fitting the local preset to the viewport. */
  LOCAL_PADDING: [40, 40, 40, 40],
} as const;

/** AIS target lifecycle, driven by the target's own `ts`. */
export const AIS_LIFETIME = {
  /** Past this age a target renders at reduced opacity. */
  FADE_AFTER_SECONDS: 60,
  /** Past this age a target is removed from the map entirely. */
  REMOVE_AFTER_SECONDS: 600,
} as const;

/**
 * Minimum map zoom before detail is drawn. Encodes as an OpenLayers
 * resolution: the layer appears once the view is more detailed than the
 * threshold, i.e. `resolution <= threshold`.
 */
export const ZOOM_THRESHOLDS = {
  /** Waypoint name + ETA labels. */
  WAYPOINT_LABEL: 5,
  /** Station labels — read as a view zoom level (`stationStyle.ts`). */
  STATION_LABEL: 4,
  /** AIS target names and CPA/TCPA. */
  AIS_LABEL: 6,
  /** S-57 sounding values. */
  SOUNDING_LABEL: 5,
  /** S-57 light characteristic labels. */
  LIGHT_LABEL: 5,
} as const;

/** Graticule spacing for the reference grid layer, in degrees. */
export const GRATICULE = {
  /** Minor line every N degrees. */
  INTERVAL_DEG: 5,
  /** Label every N degrees. */
  LABEL_INTERVAL_DEG: 10,
} as const;

/** Opacity applied to a layer whose data has gone stale. */
export const STALE_LAYER_OPACITY = 0.5;

/** Duration of the old→new route geometry transition, in ms. */
export const ROUTE_TRANSITION_MS = 500;

/** Fill opacity of an alarm's zone polygon. */
export const ALARM_ZONE_OPACITY = 0.25;

/**
 * CSS filter applied to the SIC raster.
 *
 * The SIC PNG is a scientific product: its colormap must stay readable, so the
 * raster is drawn unfiltered rather than hue-shifted with the chrome. Landmass
 * and water are unaffected in absolute terms, which keeps the ice edge honest.
 *
 * AURORA renders a single presentation, so the filter is simply empty.
 */
export const SIC_IMAGE_FILTER = '';

/** SIC uncertainty raster shares the SIC filter. */
export const UNCERTAINTY_IMAGE_FILTER = '';

/** Marker geometry, in pixels. */
export const MARKER_SIZES = {
  iceberg: 5,
  station: 6,
  waypoint: 5,
  alarmZone: 6,
} as const;

/** Route stroke widths, in pixels. */
export const ROUTE_WIDTH = {
  primary: 4,
  alternative: 2,
} as const;

/** Coastline and depth-contour stroke widths, in pixels. */
export const REFERENCE_WIDTH = {
  coastline: 1.5,
  depthContour: 1,
  graticule: 0.5,
} as const;
