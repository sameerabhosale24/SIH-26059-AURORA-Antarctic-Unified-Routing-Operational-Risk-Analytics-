/**
 * Shared helpers for layer sources and styles.
 *
 * ## Coordinate handling
 *
 * All vector geometries in this project are stored as WGS84 lon/lat.
 * OpenLayers does **not** reproject features automatically by default — it
 * would expect view-projection coordinates. AURORA instead declares WGS84 as
 * OpenLayers' *user projection* (see `declareUserProjection` in
 * `config/projection.ts`, called from `registerLccProjection`).
 *
 * With a user projection set, OL transforms user coordinates to the view
 * projection at render time (`renderer/VectorLayer.js`), which buys three
 * things:
 *   - layers are authored once in lon/lat and never re-authored;
 *   - switching the projection preset (corridor ↔ polar) rebuilds no layer;
 *   - map events, `MousePosition` and `ol.View`'s public methods all come back
 *     as lon/lat already.
 *
 * Never transform features into LCC yourself — that would double-transform.
 */
import Feature from 'ol/Feature';
import Point from 'ol/geom/Point';
import Polygon from 'ol/geom/Polygon';
import type Geometry from 'ol/geom/Geometry';
import type { Extent } from 'ol/extent';
import type Projection from 'ol/proj/Projection';
import VectorSource from 'ol/source/Vector';

/** The feature type every AURORA vector layer stores. */
export type GeoFeature = Feature<Geometry>;

/** The vector source type every AURORA vector layer uses. */
export type GeoVectorSource = VectorSource<GeoFeature>;

/** Parse an ISO timestamp into epoch ms, or null when unusable. */
export function parseTime(iso: string | null | undefined): number | null {
  if (typeof iso !== 'string' || iso === '') return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Age in seconds of a producer timestamp.
 * @returns null when the timestamp is missing or unparseable, so the caller
 *          renders an unknown age rather than a fabricated one.
 */
export function ageSeconds(iso: string | null | undefined, now = Date.now()): number | null {
  const ms = parseTime(iso);
  if (ms === null) return null;
  return Math.max(0, (now - ms) / 1000);
}

/**
 * A vector source that never drops features from a viewport query.
 *
 * `ol/renderer/canvas/VectorLayer` culls with `getFeaturesInExtent(
 * toUserExtent(viewExtent))`, and `toUserExtent` → `transformExtent` projects
 * only the *four corners* of the view rectangle. Under AURORA's wide LCC view
 * that corner-only box is rotated against the parallels: it reaches barely
 * ~63°S while the viewport itself shows water down to ~78°S, so every
 * Antarctic feature — stations, coastline, the southern graticule — is culled
 * before it is ever drawn.
 *
 * The canvas clips to the viewport anyway, so reporting the full feature set
 * costs only overdraw, and hit detection gets a complete candidate list too.
 * Every AURORA source is small and static within a frame, so there is no
 * spatial index worth keeping for this trade-off.
 */
class UnculledVectorSource<T extends Feature<Geometry>> extends VectorSource<T> {
  getFeaturesInExtent(_extent: Extent, _projection?: Projection): T[] {
    return this.getFeatures();
  }
}

/** A fresh, empty vector source holding WGS84 geometries. */
export function createGeoSource(): GeoVectorSource {
  return new UnculledVectorSource<GeoFeature>();
}

/** A point feature carrying arbitrary attributes, in WGS84 degrees. */
export function pointFeature(
  lon: number,
  lat: number,
  properties: Record<string, unknown>,
  id?: string | number,
): Feature<Point> {
  const feature = new Feature({ geometry: new Point([lon, lat]) });
  for (const [key, value] of Object.entries(properties)) feature.set(key, value);
  if (id !== undefined) feature.setId(id);
  return feature;
}

/** A polygon feature from a GeoJSON-style ring array, in WGS84 degrees. */
export function polygonFeature(
  ring: Array<[number, number]>,
  properties: Record<string, unknown>,
  id?: string | number,
): Feature<Polygon> {
  const feature = new Feature({ geometry: new Polygon([ring]) });
  for (const [key, value] of Object.entries(properties)) feature.set(key, value);
  if (id !== undefined) feature.setId(id);
  return feature;
}

/**
 * Replace a source's features in place.
 *
 * Keeps the same source object so OpenLayers does not tear down and rebuild
 * its renderer batch — important for the 1 Hz own-ship and AIS streams.
 */
export function replaceFeatures(source: GeoVectorSource, features: GeoFeature[]): void {
  source.clear(true);
  if (features.length > 0) source.addFeatures(features);
}

const RGB_PATTERN = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/;

/**
 * Apply an alpha to a CSS colour.
 *
 * Palette colours arrive from `rgbToCSS` as `rgb(r, g, b)`. Anything that is
 * not that exact shape (a hex value, a named colour) is returned untouched —
 * a translucent halo is a nicety, and losing it beats losing the colour.
 */
export function withAlpha(color: string, alpha: number): string {
  const match = RGB_PATTERN.exec(color);
  if (!match) return color;

  const [, r, g, b] = match;
  if (r === undefined || g === undefined || b === undefined) return color;

  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
