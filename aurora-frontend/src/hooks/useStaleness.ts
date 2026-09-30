/**
 * Staleness for any data source.
 *
 * Re-evaluates every `STALENESS_TICK_MS` so a source crosses into STALE on its
 * own — no manual refresh, no polling of the backend.
 *
 * The distinction the UI depends on:
 *  - `isMissing` — we have never received this data. Render an empty state,
 *    red health dot.
 *  - `isStale`   — we have data but it is older than the threshold. Render it
 *    faded with a yellow STALE badge.
 */
import { useEffect, useMemo, useReducer } from 'react';
import { STALENESS_THRESHOLDS, STALENESS_TICK_MS, type StalenessSource } from '@/config/constants';
import { useAisStore } from '@/stores/aisStore';
import { useEncStore } from '@/stores/encStore';
import { useIcebergStore } from '@/stores/icebergStore';
import { useRouteStore } from '@/stores/routeStore';
import { useSicStore } from '@/stores/sicStore';
import { useVesselStore } from '@/stores/vesselStore';
import { useWeatherStore } from '@/stores/weatherStore';

export interface StalenessResult {
  /** Data exists but is older than its threshold. */
  isStale: boolean;
  /** No data has ever been received for this source. */
  isMissing: boolean;
  /** Age of the payload in seconds, or null when there is no payload. */
  ageSeconds: number | null;
  /** Threshold applied, in seconds. */
  thresholdSeconds: number;
  /** Epoch ms of the last successful payload, or null. */
  lastUpdated: number | null;
}

/** Force a re-render on a fixed cadence so `Date.now()` is re-read. */
function useTick(intervalMs: number): number {
  const [tick, bump] = useReducer((n: number) => n + 1, 0);

  useEffect(() => {
    const id = setInterval(bump, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return tick;
}

/**
 * Synchronous staleness check, for callers that cannot use a hook.
 *
 * The map's render loop needs this — OpenLayers layer opacity is set from a
 * plain function, outside React's render cycle — so it reads the stores'
 * current state directly. The React hook above and this function share the
 * same thresholds and the same arrival timestamps, which is what keeps a
 * fading layer and its health dot in agreement.
 */
export function isSourceStale(key: StalenessSource): boolean {
  const source = readSource(key);

  if (source.data === null || source.lastUpdated === null) return false;

  return Date.now() - source.lastUpdated > STALENESS_THRESHOLDS[key] * 1000;
}

/** Current payload and arrival time for one source, straight from its store. */
function readSource(key: StalenessSource): { data: unknown; lastUpdated: number | null } {
  switch (key) {
    case 'GPS': {
      const state = useVesselStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
    case 'AIS': {
      const state = useAisStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
    case 'weather': {
      const state = useWeatherStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
    case 'SIC': {
      const state = useSicStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
    case 'icebergs': {
      const state = useIcebergStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
    case 'route': {
      const state = useRouteStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
    case 'enc': {
      const state = useEncStore.getState();
      return { data: state.data, lastUpdated: state.lastUpdated };
    }
  }
}

export function useStaleness(key: StalenessSource): StalenessResult {
  const tick = useTick(STALENESS_TICK_MS);

  // Every store is subscribed unconditionally — a conditional hook call would
  // break the rules of hooks. Selectors return primitives or stable
  // references so Zustand's identity check never loops.
  const vesselData = useVesselStore((s) => s.data);
  const vesselUpdated = useVesselStore((s) => s.lastUpdated);

  const aisData = useAisStore((s) => s.data);
  const aisUpdated = useAisStore((s) => s.lastUpdated);

  const weatherData = useWeatherStore((s) => s.data);
  const weatherUpdated = useWeatherStore((s) => s.lastUpdated);

  const sicData = useSicStore((s) => s.data);
  const sicUpdated = useSicStore((s) => s.lastUpdated);

  const icebergData = useIcebergStore((s) => s.data);
  const icebergUpdated = useIcebergStore((s) => s.lastUpdated);

  const routeData = useRouteStore((s) => s.data);
  const routeUpdated = useRouteStore((s) => s.lastUpdated);

  const encData = useEncStore((s) => s.data);
  const encUpdated = useEncStore((s) => s.lastUpdated);

  return useMemo(() => {
    const sources = {
      GPS: { data: vesselData, lastUpdated: vesselUpdated },
      AIS: { data: aisData, lastUpdated: aisUpdated },
      weather: { data: weatherData, lastUpdated: weatherUpdated },
      SIC: { data: sicData, lastUpdated: sicUpdated },
      icebergs: { data: icebergData, lastUpdated: icebergUpdated },
      route: { data: routeData, lastUpdated: routeUpdated },
      enc: { data: encData, lastUpdated: encUpdated },
    } satisfies Record<StalenessSource, { data: unknown; lastUpdated: number | null }>;

    const source = sources[key];
    const thresholdSeconds = STALENESS_THRESHOLDS[key];
    const isMissing = source.data === null;

    if (isMissing || source.lastUpdated === null) {
      return { isStale: false, isMissing: true, ageSeconds: null, thresholdSeconds, lastUpdated: null };
    }

    // `tick` is in the dependency list on purpose: it is the clock that drives
    // this recomputation.
    const now = Date.now();
    const ageSeconds = Math.max(0, (now - source.lastUpdated) / 1000);

    return {
      isStale: ageSeconds > thresholdSeconds,
      isMissing: false,
      ageSeconds,
      thresholdSeconds,
      lastUpdated: source.lastUpdated,
    };
  }, [
    tick,
    key,
    vesselData,
    vesselUpdated,
    aisData,
    aisUpdated,
    weatherData,
    weatherUpdated,
    sicData,
    sicUpdated,
    icebergData,
    icebergUpdated,
    routeData,
    routeUpdated,
    encData,
    encUpdated,
  ]);
}
