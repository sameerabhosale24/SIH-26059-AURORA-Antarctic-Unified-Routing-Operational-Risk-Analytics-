/**
 * Sea-ice-concentration (SIC) forecast frames.
 *
 * Frames are pre-rendered PNGs served by the backend. `frame_extent` is
 * already expressed in LCC metres — the frontend must use it verbatim as the
 * OpenLayers `imageExtent` and must not recompute it.
 */
export interface SicFrameMeta {
  /** ISO date, `YYYY-MM-DD`. */
  date: string;
  /** Forecast horizon in days from `date`. */
  horizon: 1 | 2 | 3;
  version: number;
  frame_url: string;
  /** `[minX, minY, maxX, maxY]` in LCC metres. */
  frame_extent: [number, number, number, number];
  /** URL of the matching uncertainty (90% interval) PNG, same extent. */
  interval_url: string | null;
}

/** Response of `GET /api/sic/frames`. */
export interface SicFramesResponse {
  version: number;
  frames: SicFrameMeta[];
}
