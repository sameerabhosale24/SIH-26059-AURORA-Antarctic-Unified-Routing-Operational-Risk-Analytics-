/**
 * Reference-corridor geometry.
 *
 * Two great-circle tracks from Cape Town — one to Maitri, one to Bharati —
 * plus the SIC region-of-interest rectangle and its caption. This is a *visual
 * reference*: it answers "which way are we going, and where does the forecast
 * actually cover?". The computed A* route is a different layer entirely and
 * never reads anything from here.
 *
 * Nothing is fetched. The endpoints come from the client-side Cape Town entry
 * and from `stationsStore`; the rectangle comes from the ROI the map was built
 * with (the same one the SIC raster is framed on).
 */
import Feature from 'ol/Feature';
import LineString from 'ol/geom/LineString';

import { CAPE_TOWN } from '@/config/stations';
import type { StationsStore } from '@/stores/stationsStore';
import type { Roi } from '@/types/common';
import {
  createGeoSource,
  pointFeature,
  polygonFeature,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';

/** Feature property keys, read by `corridorStyle`. */
export const CORRIDOR_PROPS = {
  KIND: 'kind',
  TEXT: 'text',
} as const;

export type CorridorKind = 'line' | 'roi' | 'label';

/** Caption drawn on the ROI's top edge. */
export const ROI_LABEL = 'SIC forecast coverage';

/** Segments interpolated along each great circle. */
const SEGMENTS = 64;

/** Cape Town's position, as the corridor's origin. */
export const CAPE_TOWN_POSITION: [number, number] = [CAPE_TOWN.lon, CAPE_TOWN.lat];

/**
 * Endpoints used until `stationsStore` has the real list.
 *
 * The two Indian stations are fixed facilities; the values match
 * `GET /api/stations` so a corridor drawn before the list lands is not redrawn
 * into a different shape afterwards.
 */
const FALLBACK_MAITRI: [number, number] = [11.7339, -70.7664];
const FALLBACK_BHARATI: [number, number] = [76.247, -69.397];

export interface CorridorEndpoints {
  maitri: [number, number];
  bharati: [number, number];
}

/** Resolve the corridor's far endpoints from the station list, with fallbacks. */
export function resolveEndpoints(state: StationsStore): CorridorEndpoints {
  const stations = state.data ?? [];

  const position = (id: string, fallback: [number, number]): [number, number] => {
    const match = stations.find((station) => station.id === id);
    return match ? [match.lon, match.lat] : fallback;
  };

  return {
    maitri: position('maitri', FALLBACK_MAITRI),
    bharati: position('bharati', FALLBACK_BHARATI),
  };
}

const TO_RAD = Math.PI / 180;
const TO_DEG = 180 / Math.PI;

type Vector3 = [number, number, number];

function unitVector([lon, lat]: [number, number]): Vector3 {
  const lambda = lon * TO_RAD;
  const phi = lat * TO_RAD;
  const cosPhi = Math.cos(phi);
  return [cosPhi * Math.cos(lambda), cosPhi * Math.sin(lambda), Math.sin(phi)];
}

/**
 * Points along the great circle from `from` to `to`.
 *
 * Slerp on the unit sphere: the corridor runs a third of the way around the
 * globe, so a straight line in lon/lat would bow visibly away from the track a
 * vessel actually steers.
 */
export function greatCircle(
  from: [number, number],
  to: [number, number],
  segments = SEGMENTS,
): Array<[number, number]> {
  const p = unitVector(from);
  const q = unitVector(to);

  let dot = p[0] * q[0] + p[1] * q[1] + p[2] * q[2];
  dot = Math.max(-1, Math.min(1, dot));

  const omega = Math.acos(dot);
  const sinOmega = Math.sin(omega);
  const interpolable = sinOmega > 1e-9;

  const points: Array<[number, number]> = [];

  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;

    let x: number;
    let y: number;
    let z: number;

    if (interpolable) {
      const a = Math.sin((1 - t) * omega) / sinOmega;
      const b = Math.sin(t * omega) / sinOmega;
      x = a * p[0] + b * q[0];
      y = a * p[1] + b * q[1];
      z = a * p[2] + b * q[2];
    } else {
      // Coincident (or antipodal) endpoints: lerp is the safe degenerate case.
      x = p[0] + (q[0] - p[0]) * t;
      y = p[1] + (q[1] - p[1]) * t;
      z = p[2] + (q[2] - p[2]) * t;
    }

    const lon = Math.atan2(y, x) * TO_DEG;
    const lat = Math.asin(Math.max(-1, Math.min(1, z))) * TO_DEG;
    points.push([lon, lat]);
  }

  return points;
}

function lineFeature(from: [number, number], to: [number, number]): GeoFeature {
  const feature = new Feature({
    geometry: new LineString(greatCircle(from, to)),
  });
  feature.set(CORRIDOR_PROPS.KIND, 'line' satisfies CorridorKind);
  return feature;
}

/** Closed lon/lat ring of a ROI, in `[lon, lat]` pairs. */
function roiRing(roi: Roi): Array<[number, number]> {
  return [
    [roi.lon_min, roi.lat_min],
    [roi.lon_max, roi.lat_min],
    [roi.lon_max, roi.lat_max],
    [roi.lon_min, roi.lat_max],
    [roi.lon_min, roi.lat_min],
  ];
}

/** The corridor's features for a given ROI and pair of far endpoints. */
export function corridorFeatures(
  roi: Roi,
  endpoints: CorridorEndpoints,
): GeoFeature[] {
  const roiFeature = polygonFeature(roiRing(roi), {
    [CORRIDOR_PROPS.KIND]: 'roi' satisfies CorridorKind,
  });

  const labelFeature = pointFeature(
    (roi.lon_min + roi.lon_max) / 2,
    roi.lat_max,
    {
      [CORRIDOR_PROPS.KIND]: 'label' satisfies CorridorKind,
      [CORRIDOR_PROPS.TEXT]: ROI_LABEL,
    },
    'sic-roi-label',
  );

  return [
    lineFeature(CAPE_TOWN_POSITION, endpoints.maitri),
    lineFeature(CAPE_TOWN_POSITION, endpoints.bharati),
    roiFeature,
    labelFeature,
  ];
}

/** A source holding the corridor features. */
export function createCorridorSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

/** Overwrite an existing source in place, so the renderer batch survives. */
export function syncCorridorSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}
