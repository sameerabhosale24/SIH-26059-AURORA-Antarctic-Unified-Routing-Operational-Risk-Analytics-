/**
 * Station geometry.
 *
 * Stations are static reference metadata from `GET /api/stations`, held in
 * `stationsStore`. Nothing here is fetched: the layer only translates the
 * store's list into features, so a missing list is a missing layer rather than
 * a set of placeholder markers.
 */
import type { StationsStore } from '@/stores/stationsStore';
import { createGeoSource, pointFeature, replaceFeatures, type GeoFeature, type GeoVectorSource } from '../shared';
/** Feature property keys, read by `stationStyle`. */
export const STATION_PROPS = {
  NAME: 'name',
  COUNTRY: 'country',
} as const;

/** Station features, or `null` when the backend has published none. */
export function stationFeatures(state: StationsStore): GeoFeature[] | null {
  const stations = state.data;
  if (!stations || stations.length === 0) return null;

  return stations.map((station) =>
    pointFeature(
      station.lon,
      station.lat,
      { [STATION_PROPS.NAME]: station.name, [STATION_PROPS.COUNTRY]: station.country },
      station.id,
    ),
  );
}

/** A source holding the station features. */
export function createStationSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

/** Overwrite an existing source in place, so the renderer batch survives. */
export function syncStationSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}
