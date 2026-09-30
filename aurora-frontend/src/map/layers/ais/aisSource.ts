/**
 * AIS target geometry.
 *
 * Targets arrive as a complete list on every `WS /ws/ais` frame — there are no
 * deltas to merge. Expired targets are dropped here rather than styled away:
 * keeping a target in the source that is no longer displayed would leave it in
 * `forEachFeatureAtPixel` and in the target list's spatial queries.
 *
 * Age is captured when the feature is built. A subsequent WS frame rebuilds it,
 * and MapView's staleness tick re-runs the update so a quiet channel still
 * ages its targets out.
 */
import { AIS_LIFETIME } from '@/config/constants';
import { useAisStore, type AisStore } from '@/stores/aisStore';
import {
  ageSeconds,
  createGeoSource,
  pointFeature,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';

/** Feature property keys, read by `aisStyle`. */
export const AIS_PROPS = {
  MMSI: 'mmsi',
  NAME: 'name',
  RISK: 'risk',
  SOG: 'sog',
  COG: 'cog',
  CPA_NM: 'cpa_nm',
  TCPA_MIN: 'tcpa_min',
  TS: 'ts',
  AGE_S: 'age_s',
} as const;

/** AIS features, or `null` when no live target remains. */
export function aisFeatures(state: AisStore, now = Date.now()): GeoFeature[] | null {
  const targets = state.data;
  if (!targets || targets.length === 0) return null;

  const features: GeoFeature[] = [];
  for (const target of targets) {
    const age = ageSeconds(target.ts, now);
    if (age !== null && age > AIS_LIFETIME.REMOVE_AFTER_SECONDS) continue;

    features.push(
      pointFeature(
        target.lon,
        target.lat,
        {
          [AIS_PROPS.MMSI]: target.mmsi,
          [AIS_PROPS.NAME]: target.name,
          [AIS_PROPS.RISK]: target.risk,
          [AIS_PROPS.SOG]: target.sog,
          [AIS_PROPS.COG]: target.cog,
          [AIS_PROPS.CPA_NM]: target.cpa_nm,
          [AIS_PROPS.TCPA_MIN]: target.tcpa_min,
          [AIS_PROPS.TS]: target.ts,
          [AIS_PROPS.AGE_S]: age,
        },
        target.mmsi,
      ),
    );
  }

  return features.length > 0 ? features : null;
}

export function createAisSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncAisSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useAisStore };
