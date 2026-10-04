/**
 * Data synchronisation: initial REST load, WebSocket subscriptions, and the
 * version → refetch → toast chain.
 *
 * One module owns the whole boot sequence so `App` has a single effect to
 * start and a single function to stop, and so the order of operations is
 * written down in one place:
 *
 *   1. load every REST-backed store once (the empty map problem),
 *   2. connect each WebSocket channel so streams take over from the snapshot,
 *   3. subscribe to version changes and refetch only what republished.
 *
 * Nothing here ever reloads the page or clears view state — a republished
 * forecast is an update to a panel, not a reason to lose the operator's place.
 */
import {
  getAlarmsActive,
  getEncManifest,
  getIcebergsCurrent,
  getSicFrames,
  getStations,
  getVesselLatest,
  getRouteCurrent,
  getRouteHistory,
  getWeatherAtVessel,
} from '@/services/api';
import { onVersionChange } from '@/services/versionPoller';
import { preloadCoastline } from '@/map/layers/coastline/coastlineSource';
import { useAisStore } from '@/stores/aisStore';
import { useAlarmStore } from '@/stores/alarmStore';
import { useDataStore } from '@/stores/dataStore';
import { useEncStore } from '@/stores/encStore';
import { useIcebergStore } from '@/stores/icebergStore';
import { useRouteStore } from '@/stores/routeStore';
import { useSicStore } from '@/stores/sicStore';
import { useStationsStore } from '@/stores/stationsStore';
import { useVesselStore } from '@/stores/vesselStore';
import { useWeatherStore } from '@/stores/weatherStore';
import { notify } from '@/stores/toastStore';
import { toErrorMessage } from '@/stores/createDataStore';
import type { DataVersionKey } from '@/types/version';

/** Routes pulled alongside the active run so history is ready on first paint. */
const HISTORY_LIMIT = 10;

/**
 * Vessel-scoped products are fetched against the selected vessel.
 *
 * Read at call time rather than passed in, so a fetch that starts just before
 * a vessel change still resolves for the vessel the operator was looking at
 * when it began, and the reload triggered by the change supersedes it.
 */
function currentVesselId(): number | undefined {
  return useVesselStore.getState().vesselId ?? undefined;
}

/**
 * Load every REST-backed store once.
 *
 * Individual failures are recorded on the store that owns them rather than
 * failing the whole boot: a backend with no coastline still has a version
 * endpoint, and the UI has an empty state for exactly this.
 */
export async function loadInitialData(): Promise<void> {
  const results = await Promise.allSettled([
    loadVessel(),
    loadWeather(),
    loadIcebergs(),
    loadStations(),
    loadEnc(),
    loadSic(),
    loadRoute(),
    loadAlarms(),
    loadCoastline(),
  ]);

  for (const result of results) {
    if (result.status === 'rejected') {
      console.warn('[aurora] an initial load failed', result.reason);
    }
  }
}

async function loadVessel(): Promise<void> {
  try {
    useVesselStore.getState().set(await getVesselLatest());
  } catch (cause) {
    useVesselStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadWeather(): Promise<void> {
  try {
    useWeatherStore.getState().set(await getWeatherAtVessel(currentVesselId()));
  } catch (cause) {
    useWeatherStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadIcebergs(): Promise<void> {
  try {
    useIcebergStore.getState().set(await getIcebergsCurrent());
  } catch (cause) {
    useIcebergStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadStations(): Promise<void> {
  try {
    useStationsStore.getState().set(await getStations());
  } catch (cause) {
    useStationsStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadEnc(): Promise<void> {
  try {
    useEncStore.getState().set(await getEncManifest());
  } catch (cause) {
    useEncStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadSic(): Promise<void> {
  try {
    const manifest = await getSicFrames();
    if (manifest) useSicStore.getState().setManifest(manifest);
  } catch (cause) {
    useSicStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadRoute(): Promise<void> {
  try {
    const [current, history] = await Promise.all([
      getRouteCurrent(currentVesselId()),
      getRouteHistory(HISTORY_LIMIT),
    ]);

    const store = useRouteStore.getState();
    store.set(current);
    store.setHistory(history);
  } catch (cause) {
    useRouteStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadAlarms(): Promise<void> {
  try {
    useAlarmStore.getState().set(await getAlarmsActive(currentVesselId()));
  } catch (cause) {
    useAlarmStore.getState().setError(toErrorMessage(cause));
  }
}

async function loadCoastline(): Promise<void> {
  await preloadCoastline();
}

/**
 * Refetch the store affected by one republished product, then raise a toast.
 *
 * Toasts are informational: the data is already visible in its panel, so the
 * message only needs to say *that* something moved, not what it now reads.
 */
async function refetchChanged(key: DataVersionKey): Promise<void> {
  try {
    switch (key) {
      case 'sic': {
        const manifest = await getSicFrames();
        if (manifest) useSicStore.getState().setManifest(manifest);
        notify('SIC forecast updated', 'success');
        break;
      }

      case 'icebergs': {
        useIcebergStore.getState().set(await getIcebergsCurrent());
        notify('Iceberg positions updated', 'success');
        break;
      }

      case 'weather': {
        useWeatherStore.getState().set(await getWeatherAtVessel(currentVesselId()));
        notify('Weather updated', 'success');
        break;
      }

      case 'enc': {
        useEncStore.getState().set(await getEncManifest());
        notify('Chart cells updated', 'success');
        break;
      }

      case 'currents':
        // No currents store exists yet — the product is published but nothing
        // on the client consumes it. Logged rather than toasted so the gap is
        // visible without inventing a UI for data no panel reads.
        console.info('[aurora] currents republished; no consumer store yet');
        break;
    }
  } catch (cause) {
    console.warn(`[aurora] refetch after ${key} republish failed`, cause);
    notify(`${key} refresh failed`, 'warn', toErrorMessage(cause));
  }
}

/**
 * Start the whole data path.
 *
 * Called only while an operator is signed in (see `App`): every request here
 * carries the bearer token, and starting it at boot would fire an
 * unauthenticated wave that a real backend answers with 401.
 *
 * @returns a disposer that unsubscribes from version and vessel changes and
 *          closes every WebSocket channel this call opened.
 */
export function initDataSync(): () => void {
  void loadInitialData();

  const offChannels = [
    useVesselStore.getState().init(),
    useAisStore.getState().init(),
    useWeatherStore.getState().init(),
    useRouteStore.getState().init(),
    useAlarmStore.getState().init(),
  ];

  let booted = false;

  const offVersion = onVersionChange((version, changed) => {
    // The version poll is the app's only proof of life from the REST API, so
    // it is also what clears the "API down" badge the store starts with. It
    // has to run before the first-load guard below: that guard skips the
    // refetch wave, not the status.
    useDataStore.getState().setVersions(version);

    // The first poll has no previous snapshot, so it reports every key as
    // changed. Those stores were just loaded above; re-deriving that as five
    // toasts would greet the operator with noise instead of data.
    if (!booted) {
      booted = true;
      return;
    }

    for (const key of changed) void refetchChanged(key);
  });

  // Selecting a different vessel re-scopes route, alarms and weather. Their
  // stores were showing the previous ship's answer a moment ago; without this
  // they would keep showing it until the next version poll.
  const offVessel = useVesselStore.subscribe((state, previous) => {
    if (state.vesselId === previous.vesselId) return;

    if (state.vesselId === null) {
      useRouteStore.getState().clear();
      useAlarmStore.getState().clear();
      useWeatherStore.getState().clear();
      return;
    }

    void loadRoute();
    void loadAlarms();
    void loadWeather();
  });

  return () => {
    offVessel();
    offVersion();
    for (const off of offChannels) off();
  };
}
