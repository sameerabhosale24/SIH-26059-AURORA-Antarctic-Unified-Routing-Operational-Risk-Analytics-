/**
 * Graticule geometry.
 *
 * Meridians and parallels are generated every {@link GRATICULE.INTERVAL_DEG}
 * degrees over the full geographic domain. The domain is not a site coordinate
 * — it is the extent in which a graticule is defined — so nothing here is
 * hardcoded from the ROI, and a backend ROI change needs no edit.
 *
 * Lines are sampled every 5° of their free axis. That is dense enough that a
 * parallel still draws as a smooth circle under the polar preset (the user
 * projection reprojects each vertex) without carrying tens of thousands of
 * points.
 *
 * Labels are separate point features so `gridStyle` can pick a different
 * portrayal for them: one every {@link GRATICULE.LABEL_INTERVAL_DEG} degrees,
 * repeated along the line at 40° intervals so at least one is in frame
 * wherever the operator is looking.
 */
import Feature from 'ol/Feature';
import LineString from 'ol/geom/LineString';
import Point from 'ol/geom/Point';

import { GRATICULE } from '@/config/constants';
import { createGeoSource, type GeoFeature, type GeoVectorSource } from '../shared';

/** Feature property keys, read by `gridStyle`. */
export const GRID_PROPS = {
  KIND: 'kind',
  VALUE: 'value',
  TEXT: 'text',
} as const;

export type GridFeatureKind = 'line' | 'label';

const DOMAIN_LON: [number, number] = [-180, 180];
const DOMAIN_LAT: [number, number] = [-90, 90];

/** Latitudes at which each labelled meridian repeats its label. */
const MERIDIAN_LABEL_LATS = [-80, -40, 0, 40, 80];

/** Longitudes at which each labelled parallel repeats its label. */
const PARALLEL_LABEL_LONS = [-160, -120, -80, -40, 0, 40, 80, 120, 160];

function formatLongitude(value: number): string {
  if (value === 0) return '0°';
  return `${Math.abs(value)}°${value > 0 ? 'E' : 'W'}`;
}

function formatLatitude(value: number): string {
  if (value === 0) return '0°';
  return `${Math.abs(value)}°${value > 0 ? 'N' : 'S'}`;
}

function step(from: number, to: number, size: number): number[] {
  const values: number[] = [];
  for (let value = from; value <= to; value += size) values.push(value);
  return values;
}

function lineFeature(
  coordinates: Array<[number, number]>,
  kind: GridFeatureKind,
  value: number,
): Feature<LineString> {
  const feature = new Feature({ geometry: new LineString(coordinates) });
  feature.set(GRID_PROPS.KIND, kind);
  feature.set(GRID_PROPS.VALUE, value);
  return feature;
}

function labelFeature(
  lon: number,
  lat: number,
  kind: GridFeatureKind,
  value: number,
  text: string,
): Feature<Point> {
  const feature = new Feature({ geometry: new Point([lon, lat]) });
  feature.set(GRID_PROPS.KIND, kind);
  feature.set(GRID_PROPS.VALUE, value);
  feature.set(GRID_PROPS.TEXT, text);
  return feature;
}

let cached: GeoFeature[] | null = null;

/**
 * The graticule features, or `null` when spacing is disabled.
 *
 * Built once: the grid is static, so a store notification must never cause it
 * to be regenerated.
 */
export function gridFeatures(): GeoFeature[] | null {
  if (cached) return cached;

  const spacing = GRATICULE.INTERVAL_DEG;
  if (!Number.isFinite(spacing) || spacing <= 0) return null;

  const labelSpacing = GRATICULE.LABEL_INTERVAL_DEG;
  const features: GeoFeature[] = [];

  for (const lon of step(DOMAIN_LON[0], DOMAIN_LON[1] - spacing, spacing)) {
    const points: Array<[number, number]> = step(DOMAIN_LAT[0], DOMAIN_LAT[1], spacing).map(
      (lat) => [lon, lat] as [number, number],
    );
    features.push(lineFeature(points, 'line', lon));

    if (lon % labelSpacing === 0) {
      for (const lat of MERIDIAN_LABEL_LATS) {
        features.push(labelFeature(lon, lat, 'label', lon, formatLongitude(lon)));
      }
    }
  }

  for (const lat of step(DOMAIN_LAT[0] + spacing, DOMAIN_LAT[1] - spacing, spacing)) {
    const points: Array<[number, number]> = step(DOMAIN_LON[0], DOMAIN_LON[1], spacing).map(
      (lon) => [lon, lat] as [number, number],
    );
    features.push(lineFeature(points, 'line', lat));

    if (lat % labelSpacing === 0) {
      for (const lon of PARALLEL_LABEL_LONS) {
        features.push(labelFeature(lon, lat, 'label', lat, formatLatitude(lat)));
      }
    }
  }

  cached = features;
  return cached;
}

/** A reusable source holding the graticule, or `null` when it is disabled. */
export function gridSource(): GeoVectorSource | null {
  const features = gridFeatures();
  if (!features || features.length === 0) return null;

  const source = createGeoSource();
  source.addFeatures(features);
  return source;
}
