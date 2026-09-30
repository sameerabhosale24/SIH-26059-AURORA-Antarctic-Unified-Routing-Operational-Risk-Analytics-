/**
 * Iceberg drift-cone geometry.
 *
 * The cone is a WGS84 GeoJSON polygon supplied by the backend together with
 * its containment probability. Where the backend has not computed a cone, the
 * iceberg contributes no cone geometry — this layer never extrapolates a
 * direction from `drift_bearing` alone, because a bearing without a spread is
 * not a forecast.
 *
 * A second fetch of the iceberg list must not re-derive anything: the polygons
 * are used verbatim.
 */
import Feature from 'ol/Feature';
import Polygon from 'ol/geom/Polygon';

import { useIcebergStore, type IcebergStore } from '@/stores/icebergStore';
import { createGeoSource, replaceFeatures, type GeoFeature, type GeoVectorSource } from '../shared';

/** Feature property keys, read by `icebergDriftStyle`. */
export const DRIFT_PROPS = {
  ID: 'id',
  PROBABILITY: 'probability',
  BEARING: 'bearing',
  SPEED_KT: 'speed_kt',
} as const;

/** Drift-cone features, or `null` when no iceberg has a computed cone. */
export function icebergDriftFeatures(state: IcebergStore): GeoFeature[] | null {
  const icebergs = state.data;
  if (!icebergs || icebergs.length === 0) return null;

  const features: GeoFeature[] = [];
  for (const iceberg of icebergs) {
    const cone = iceberg.drift_cone;
    if (!cone || cone.coordinates.length === 0) continue;

    const feature = new Feature({ geometry: new Polygon(cone.coordinates) });
    feature.set(DRIFT_PROPS.ID, iceberg.id);
    feature.set(DRIFT_PROPS.PROBABILITY, iceberg.drift_cone_probability);
    feature.set(DRIFT_PROPS.BEARING, iceberg.drift_bearing);
    feature.set(DRIFT_PROPS.SPEED_KT, iceberg.drift_speed_kt);
    feature.setId(`${iceberg.id}:drift`);

    features.push(feature);
  }

  return features.length > 0 ? features : null;
}

export function createDriftSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncDriftSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useIcebergStore };
