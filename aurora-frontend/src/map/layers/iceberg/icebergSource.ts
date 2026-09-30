/**
 * Iceberg position geometry.
 *
 * Positions come from `GET /api/icebergs/current` via `icebergStore`. The
 * drift cone lives in `icebergDriftSource` — the two layers are split so the
 * operator can show hazard positions with the cones hidden.
 */
import { useIcebergStore, type IcebergStore } from '@/stores/icebergStore';
import {
  createGeoSource,
  pointFeature,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';

/** Feature property keys, read by `icebergStyle`. */
export const ICEBERG_PROPS = {
  ID: 'id',
  SIZE_KM: 'length_km',
  TS: 'ts',
} as const;

/** Iceberg position features, or `null` when the backend reports none. */
export function icebergFeatures(state: IcebergStore): GeoFeature[] | null {
  const icebergs = state.data;
  if (!icebergs || icebergs.length === 0) return null;

  return icebergs.map((iceberg) =>
    pointFeature(
      iceberg.lon,
      iceberg.lat,
      {
        [ICEBERG_PROPS.ID]: iceberg.id,
        [ICEBERG_PROPS.SIZE_KM]: iceberg.length_km,
        [ICEBERG_PROPS.TS]: iceberg.ts,
      },
      iceberg.id,
    ),
  );
}

export function createIcebergSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncIcebergSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useIcebergStore };
