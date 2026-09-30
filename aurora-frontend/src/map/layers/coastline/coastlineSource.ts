/**
 * Coastline acquisition.
 *
 * `GET /api/coastline` is fetched exactly once per session and the decoded
 * features are held at module level. The coastline is reference material — it
 * does not stream, so there is no reason to re-request it or to put it in a
 * store that the version poller refreshes.
 *
 * A `null` (before the first success) means "not loaded yet". An empty array
 * means "the backend has no coastline". Both produce an absent layer; neither
 * is ever replaced by a synthetic outline.
 */
import GeoJSON from 'ol/format/GeoJSON';

import { getCoastline } from '@/services/api';
import { createGeoSource, replaceFeatures, type GeoFeature, type GeoVectorSource } from '../shared';

type Listener = (features: GeoFeature[] | null) => void;

let decoded: GeoFeature[] | null = null;
let cachedSource: GeoVectorSource | null = null;
let inflight: Promise<GeoFeature[] | null> | null = null;
const listeners = new Set<Listener>();

function announce(): void {
  for (const listener of listeners) listener(decoded);
}

/** Features decoded so far, or `null` when the first fetch has not settled. */
export function coastlineFeatures(): GeoFeature[] | null {
  return decoded;
}

/** Fetch the coastline once, memoising both success and failure. */
function load(): Promise<GeoFeature[] | null> {
  if (decoded !== null) return Promise.resolve(decoded);
  if (inflight) return inflight;

  inflight = getCoastline()
    .then((collection) => {
      // `null` from the client means "no data yet"; an empty collection means
      // the same to this layer, but `[]` lets us stop asking.
      decoded = collection === null ? [] : (new GeoJSON().readFeatures(collection) as GeoFeature[]);
      cachedSource = null;
      inflight = null;
      announce();
      return decoded;
    })
    .catch((cause) => {
      console.warn('[aurora] coastline could not be loaded', cause);
      inflight = null;
      return decoded;
    });

  return inflight;
}

/**
 * The cached coastline source, or `null` while unloaded or empty.
 *
 * Built once and reused so a store notification does not re-parse GeoJSON or
 * churn the renderer's feature batches.
 */
export function coastlineSource(): GeoVectorSource | null {
  if (cachedSource) return cachedSource;

  const features = decoded;
  if (!features || features.length === 0) return null;

  const source = createGeoSource();
  replaceFeatures(source, features);
  cachedSource = source;
  return source;
}

/**
 * Kick off the fetch without subscribing.
 *
 * Called at boot so a backend that publishes its coastline late is still
 * asked, rather than waiting for the operator to pan the map.
 */
export function preloadCoastline(): Promise<GeoFeature[] | null> {
  return load();
}

/**
 * Subscribe to coastline availability.
 *
 * Fires immediately with whatever is already loaded, then once more when the
 * fetch settles — which is how the layer appears without MapView having to
 * know that a fetch was pending underneath it.
 */
export function subscribeCoastline(onChange: Listener): () => void {
  listeners.add(onChange);
  onChange(decoded);
  void load();

  return () => {
    listeners.delete(onChange);
  };
}
