/**
 * Station geometry.
 *
 * Stations are static reference metadata from `GET /api/stations`, held in
 * `stationsStore`, plus the client-side entries in `config/stations.ts`. Nothing
 * here is fetched: the layer only translates the two lists into features, so a
 * missing backend list is a missing layer rather than a set of placeholder
 * markers.
 */
import { CLIENT_STATIONS } from '@/config/stations';
import type { StationsStore } from '@/stores/stationsStore';
import type { Station } from '@/types/common';
import { createGeoSource, pointFeature, replaceFeatures, type GeoFeature, type GeoVectorSource } from '../shared';

/** Feature property keys, read by `stationStyle` and `stationInteraction`. */
export const STATION_PROPS = {
  KIND: 'kind',
  NAME: 'name',
  COUNTRY: 'country',
  LAT: 'lat',
  LON: 'lon',
} as const;

/** Marker value identifying a station feature among the other vector layers. */
export const STATION_KIND = 'station';

/**
 * Backend stations plus the client-side ones, without duplicates.
 *
 * A client-side entry wins an id collision: it is the more specific record
 * (Cape Town's coordinates and country code are authored for this console).
 */
export function mergeStations(stations: Station[] | null): Station[] {
  const backend = stations ?? [];
  const clientIds = new Set(CLIENT_STATIONS.map((station) => station.id));

  return [...CLIENT_STATIONS, ...backend.filter((station) => !clientIds.has(station.id))];
}

/** Station features, or `null` when neither source has published one. */
export function stationFeatures(state: StationsStore): GeoFeature[] | null {
  const stations = mergeStations(state.data);
  if (stations.length === 0) return null;

  return stations.map((station) =>
    pointFeature(
      station.lon,
      station.lat,
      {
        [STATION_PROPS.KIND]: STATION_KIND,
        [STATION_PROPS.NAME]: station.name,
        [STATION_PROPS.COUNTRY]: station.country,
        [STATION_PROPS.LAT]: station.lat,
        [STATION_PROPS.LON]: station.lon,
      },
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
