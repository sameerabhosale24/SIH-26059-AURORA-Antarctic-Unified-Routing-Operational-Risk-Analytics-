/**
 * Stations the frontend contributes itself.
 *
 * `GET /api/stations` returns *research* stations — the facilities the backend
 * tracks as reference data. Cape Town is the corridor's origin, not a research
 * station, so it lives here instead: the console must be able to show the whole
 * Cape Town → station corridor even against a backend that has never heard of
 * the port.
 *
 * The list is merged into the store's stations at feature-build time (see
 * `stationSource.ts`) rather than written into the store, so nothing here can
 * be mistaken for a payload that came off the wire.
 */
import type { Station } from '@/types/common';

/** The corridor's South African origin. */
export const CAPE_TOWN: Station = {
  id: 'cape-town',
  name: 'Cape Town',
  country: 'ZA',
  lat: -33.9253,
  lon: 18.4239,
};

/** Client-side stations, keyed by id in the merge against the backend list. */
export const CLIENT_STATIONS: readonly Station[] = [CAPE_TOWN];
