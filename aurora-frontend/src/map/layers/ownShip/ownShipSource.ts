/**
 * Own-ship geometry.
 *
 * A single feature from `vesselStore`, built from the payload's `lat`/`lon`
 * exactly as received. A position that is not finite is treated as no
 * position at all: a `0, 0` marker in the Gulf of Guinea would be worse than
 * an empty map.
 */
import { useVesselStore, type VesselStore } from '@/stores/vesselStore';
import {
  createGeoSource,
  pointFeature,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';

/** Feature property keys, read by `ownShipStyle`. */
export const OWN_SHIP_PROPS = {
  VESSEL_ID: 'vessel_id',
  HEADING: 'heading',
  COG: 'cog',
  SOG: 'sog',
  TS: 'ts',
} as const;

/** Own-ship feature, or `null` when there is no usable position yet. */
export function ownShipFeatures(state: VesselStore): GeoFeature[] | null {
  const vessel = state.data;
  if (!vessel) return null;
  if (!Number.isFinite(vessel.lon) || !Number.isFinite(vessel.lat)) return null;

  return [
    pointFeature(
      vessel.lon,
      vessel.lat,
      {
        [OWN_SHIP_PROPS.VESSEL_ID]: vessel.vessel_id,
        [OWN_SHIP_PROPS.HEADING]: vessel.heading,
        [OWN_SHIP_PROPS.COG]: vessel.cog,
        [OWN_SHIP_PROPS.SOG]: vessel.sog,
        [OWN_SHIP_PROPS.TS]: vessel.ts,
      },
      vessel.vessel_id,
    ),
  ];
}

export function createOwnShipSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncOwnShipSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useVesselStore };
