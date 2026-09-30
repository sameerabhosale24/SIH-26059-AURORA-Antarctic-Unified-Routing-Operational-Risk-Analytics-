import type { GeoJSON } from 'geojson';

/**
 * Shared/domain types that are not tied to a single data stream.
 */

/** A named facility (research station, port, or supply point). */
export interface Station {
  id: string;
  name: string;
  country: string;
  lat: number;
  lon: number;
}

/**
 * Region of interest in WGS84 degrees, supplied by the backend.
 * Never hardcoded in the frontend — always fetched from `GET /api/roi`.
 */
export interface Roi {
  lon_min: number;
  lat_min: number;
  lon_max: number;
  lat_max: number;
}

/** `[minX, minY, maxX, maxY]`. In LCC metres for raster frames. */
export type Extent = [number, number, number, number];

export type { GeoJSON };
