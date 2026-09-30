/**
 * ENC data acquisition.
 *
 * Pipeline: fetch `.000` → `parseS57(buffer)` → `toGeoJSON(dataset)` → OL
 * features. Parsing is delegated entirely to `@s57-parser/s57`; nothing here
 * interprets S-57 records itself.
 *
 * Two caches, because the cost is very unevenly distributed:
 *  - parsed records per cell URL — a manifest refetch, a palette change or a
 *    re-mount must not re-download or re-parse a chart;
 *  - the in-flight promise per cell URL — a burst of callers shares one fetch.
 */
import { parseS57, toGeoJSON } from '@s57-parser/s57';

import Feature from 'ol/Feature';
import LineString from 'ol/geom/LineString';
import MultiPoint from 'ol/geom/MultiPoint';
import Point from 'ol/geom/Point';
import Polygon from 'ol/geom/Polygon';
import type Geometry from 'ol/geom/Geometry';

import type { EncCell, EncFeatureRecord } from '@/types/enc';
import { createGeoSource, type GeoFeature, type GeoVectorSource } from '../shared';

/** Prefix used by the parser for S-57 attributes: `ATTL_<code>`. */
const ATTL_PREFIX = 'ATTL_';

/**
 * Feature property keys the portrayal style reads.
 * Exported so the style and the source cannot drift apart.
 */
export const ENC_PROPS = {
  /** Chart cell id, for tracing a feature back to its `.000` file. */
  CELL_ID: 'cellId',
  /** S-57 record id (RCID) — the stable within-cell feature identifier. */
  RCID: 'rcid',
  /** S-57 object class code (OBJL), e.g. 42 = DEPARE. */
  OBJL: 'objl',
  /** Parsed S-57 attributes as `ATTL_<code>` string keys. */
  ATTRS: 'attrs',
} as const;

/** Parsed cells, keyed by versioned cell URL. */
const parsedCache = new Map<string, EncFeatureRecord[]>();

/** In-flight loads, keyed by versioned cell URL. */
const inFlight = new Map<string, Promise<EncFeatureRecord[]>>();

/**
 * Append a cache-busting version query.
 *
 * Keeps browsers and proxies from serving a stale `.000` after the backend
 * republishes it. Left untouched if the URL already carries a query, since the
 * backend then owns its own cache policy.
 */
export function withVersion(url: string, version: number | null): string {
  if (version === null || url.includes('?')) return url;
  return `${url}?v=${version}`;
}

/** Drop every cached cell. Used when the ENC dataset is republished wholesale. */
export function clearEncCache(): void {
  parsedCache.clear();
}

/** Number of cells currently held in the parse cache. */
export function encCacheSize(): number {
  return parsedCache.size;
}

/**
 * Fetch and parse one chart cell.
 *
 * Returns `[]` on any failure: the cell is logged and skipped, never replaced
 * with placeholder geometry.
 */
function loadCell(cell: EncCell, version: number | null): Promise<EncFeatureRecord[]> {
  const url = withVersion(cell.url, version);

  const cached = parsedCache.get(url);
  if (cached) return Promise.resolve(cached);

  const pending = inFlight.get(url);
  if (pending) return pending;

  const task = (async (): Promise<EncFeatureRecord[]> => {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const collection = toGeoJSON(parseS57(await response.arrayBuffer()));

      const records: EncFeatureRecord[] = [];

      for (const feature of collection.features) {
        if (!feature.geometry) continue;

        records.push({
          cellId: cell.id,
          rcid: asNumber(feature.properties.RCID, -1),
          objl: asNumber(feature.properties.OBJL, -1),
          attributes: toAttributeMap(feature.properties),
          geometry: feature.geometry,
        });
      }

      parsedCache.set(url, records);
      return records;
    } catch (cause) {
      console.error(`[aurora] ENC cell "${cell.name}" failed to load; skipping it`, cause);
      return [];
    } finally {
      inFlight.delete(url);
    }
  })();

  inFlight.set(url, task);
  return task;
}

/**
 * Build an OL vector source for a set of ENC cells.
 *
 * @returns `null` when there are no cells, or when every cell failed — an
 *          absent chart is preferable to a wrong one, and in both cases the
 *          layer draws nothing.
 */
export async function buildEncSource(
  cells: EncCell[],
  version: number | null,
): Promise<GeoVectorSource | null> {
  if (cells.length === 0) return null;

  const records = (await Promise.all(cells.map((cell) => loadCell(cell, version)))).flat();
  if (records.length === 0) return null;

  const features: GeoFeature[] = [];
  for (const record of records) {
    if (!record.geometry) continue;

    const geometry = toOlGeometry(record.geometry);
    if (!geometry) continue;

    const feature = new Feature({ geometry });
    feature.set(ENC_PROPS.CELL_ID, record.cellId);
    feature.set(ENC_PROPS.RCID, record.rcid);
    feature.set(ENC_PROPS.OBJL, record.objl);
    feature.set(ENC_PROPS.ATTRS, record.attributes);
    feature.setId(`${record.cellId}:${record.rcid}`);

    features.push(feature);
  }

  if (features.length === 0) return null;

  // No `projection` option: coordinates are WGS84 and OpenLayers' user
  // projection turns them into view-projection metres at render time.
  return withFeatures(features);
}

function withFeatures(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  source.addFeatures(features);
  return source;
}

/**
 * Construct OL geometry from the parser's coordinate arrays.
 * @returns `null` for geometry this portrayal path cannot draw.
 */
function toOlGeometry(geometry: NonNullable<EncFeatureRecord['geometry']>): Geometry | null {
  switch (geometry.type) {
    case 'Point':
      return new Point(geometry.coordinates);
    case 'MultiPoint':
      return new MultiPoint(geometry.coordinates.map((coordinate) => coordinate));
    case 'LineString':
      return new LineString(geometry.coordinates);
    case 'Polygon':
      return new Polygon(geometry.coordinates.map((ring) => ring));
    case 'GeometryCollection':
      // Nested collections are not emitted by the parser for chart objects and
      // would need per-child styling; skipped rather than approximated.
      return null;
  }
}

/** Extract `ATTL_<code>` properties back into the `Map` the renderer expects. */
function toAttributeMap(properties: Record<string, unknown>): Map<number, string> {
  const attributes = new Map<number, string>();

  for (const [key, value] of Object.entries(properties)) {
    if (!key.startsWith(ATTL_PREFIX)) continue;

    const code = Number(key.slice(ATTL_PREFIX.length));
    if (!Number.isFinite(code)) continue;

    attributes.set(code, String(value));
  }

  return attributes;
}

function asNumber(value: unknown, fallback: number): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}
