/**
 * Coordinate helpers.
 *
 * Thin, typed wrappers over the projection module so that call sites never
 * build ad-hoc tuples. Everything crossing the wire with the backend is WGS84
 * degrees; everything on the map is LCC metres.
 */
import { fromLCC, lccExtent, toLCC } from '@/config/projection';
import type { Extent, Roi } from '@/types/common';

/** WGS84 degrees → LCC metres. */
export function wgs84ToLCC(lon: number, lat: number): [number, number] {
  return toLCC([lon, lat]);
}

/** LCC metres → WGS84 degrees. */
export function lccToWgs84(x: number, y: number): [number, number] {
  return fromLCC([x, y]);
}

/** Centre of a WGS84 ROI, as `[lon, lat]`. */
export function roiCenter(roi: Roi): [number, number] {
  return [(roi.lon_min + roi.lon_max) / 2, (roi.lat_min + roi.lat_max) / 2];
}

/**
 * Axis-aligned bounding box of a WGS84 ROI in LCC metres.
 * Identical to `lccExtent`; re-exported here so map code has one geo import.
 */
export function roiExtentLCC(roi: Roi): Extent {
  return lccExtent(roi);
}

/** Metres per nautical mile (exact, by definition). */
export const METRES_PER_NM = 1852;

/** Metres per kilometre. */
export const METRES_PER_KM = 1000;

/**
 * Great-circle distance in nautical miles.
 *
 * Haversine on a spherical Earth. Used only for proximity (nearest iceberg,
 * route-to-target spacing) where the ~0.5 % error of a sphere is far below the
 * uncertainty of the positions being compared — no navigation function here
 * feeds a chart symbol or a safety calculation.
 */
export function haversineNm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad;
  const dLon = (lon2 - lon1) * toRad;

  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;

  const centralAngle = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return (centralAngle * 6371 * METRES_PER_KM) / METRES_PER_NM;
}
