/**
 * Map container.
 *
 * Fetches the region of interest, builds the LCC map, then registers every
 * entry in the `LAYERS` registry. Each layer owns its own store subscription,
 * so this component never needs to know which store a given layer reads — it
 * only arbitrates the things that are genuinely map-wide:
 *
 *  - visibility and opacity from `uiStore` (via `isLayerVisible`/`layerOpacity`);
 *  - portrayal on a display-mode change;
 *  - projection presets, including the rebuild the raster layers need because
 *    their `imageExtent` is expressed in view-projection units;
 *  - follow-ship;
 *  - a 1 Hz tick for the layers that opt into it.
 *
 * If the ROI cannot be fetched the component renders an explicit empty state.
 * It does not retry aggressively: the version poller and the API health signal
 * are responsible for bringing the app back once the backend is reachable.
 */
import { useEffect, useRef, useState } from 'react';
import type Map from 'ol/Map';

import { getPalette } from '@/config/palettes';
import { getRoi } from '@/services/api';
import { useUiStore } from '@/stores/uiStore';
import { useVesselStore } from '@/stores/vesselStore';
import {
  applyProjectionPreset,
  clearMap,
  createMap,
  getLayerGroup,
  setFollowShip,
  setMapBackground,
} from './mapSetup';
import { LAYERS, isLayerVisible, layerOpacity } from './layers';
import { isSourceStale } from '@/hooks/useStaleness';
import { STALE_LAYER_OPACITY } from '@/config/constants';
import type { AuroraLayer, AuroraOlLayer } from './layers/types';

type MapState = 'loading' | 'ready' | 'unavailable';

const EMPTY_STATE_MESSAGE = 'Map unavailable — waiting for backend configuration';

/** Cadence for layers that recompute age-dependent feature properties. */
const TICK_MS = 1_000;

/** Per-layer bookkeeping held for the lifetime of the map. */
interface Entry {
  def: AuroraLayer;
  /** The layer this entry currently wants to show. */
  current: AuroraOlLayer | null;
  /** The layer actually present in the OpenLayers group. */
  attached: AuroraOlLayer | null;
  /** Most recent state pushed by the layer's subscription. */
  lastState: unknown;
  unsub: () => void;
}

export function MapView(): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<MapState>('loading');
  const [map, setMap] = useState<Map | null>(null);

  const entriesRef = useRef<Entry[]>([]);
  const syncRef = useRef<(() => void) | null>(null);

  const displayMode = useUiStore((selector) => selector.displayMode);
  const projection = useUiStore((selector) => selector.projection);
  const followShip = useUiStore((selector) => selector.followShip);
  const layerVisibility = useUiStore((selector) => selector.layerVisibility);
  const layerOpacityState = useUiStore((selector) => selector.layerOpacity);
  const vessel = useVesselStore((selector) => selector.data);

  /* ---------------------------------------------------------------- *
   * 1. Map lifetime
   * ---------------------------------------------------------------- */
  useEffect(() => {
    let disposed = false;
    let created: Map | null = null;

    void (async () => {
      try {
        const roi = await getRoi();

        if (disposed) return;

        if (!containerRef.current) {
          setState('unavailable');
          return;
        }

        created = createMap(containerRef.current, roi);
        setMap(created);
        setState('ready');
      } catch (cause) {
        // One attempt, one log. Retrying here would hammer an unknown backend
        // and duplicate the version poller's recovery path.
        console.error('Failed to fetch ROI', cause);
        if (!disposed) setState('unavailable');
      }
    })();

    return () => {
      disposed = true;
      if (created) {
        created.dispose();
        clearMap();
      }
    };
  }, []);

  /* ---------------------------------------------------------------- *
   * 2. Layer registration
   * ---------------------------------------------------------------- */
  useEffect(() => {
    if (!map) return;

    const group = getLayerGroup(map);
    // `LayerGroup` has no add/removeLayer — its children live in a Collection.
    const stack = group.getLayers();

    const sync = (entry: Entry): void => {
      const changed = entry.current !== entry.attached;

      if (changed) {
        if (entry.attached) stack.remove(entry.attached);

        if (entry.current) {
          stack.push(entry.current);
          // Layers are built with the day palette. Bring one in line with the
          // active mode at the moment it is attached, so a night-mode operator
          // never sees a single day-bright frame.
          entry.def.restyle(entry.current, getPalette(useUiStore.getState().displayMode));
        }

        entry.attached = entry.current;
      }

      const layer = entry.current;
      if (!layer) return;

      const ui = useUiStore.getState();
      layer.setVisible(isLayerVisible(entry.def.id, ui));

      // A layer whose source has gone stale is dimmed rather than hidden: the
      // operator needs to see *what* is old, and the health dot says *how* old.
      const fade =
        entry.def.stalenessKey && isSourceStale(entry.def.stalenessKey)
          ? STALE_LAYER_OPACITY
          : 1;

      layer.setOpacity(layerOpacity(entry.def.id, ui) * fade);
    };

    const syncAll = (): void => {
      for (const entry of entriesRef.current) sync(entry);
    };

    const applyState = (entry: Entry, storeState: unknown): void => {
      entry.lastState = storeState;
      entry.current = entry.def.update(entry.current, storeState);
      sync(entry);
    };

    const entries: Entry[] = LAYERS.map((def) => {
      const entry: Entry = {
        def,
        current: def.createLayer(map),
        attached: null,
        lastState: undefined,
        unsub: () => undefined,
      };

      // Subscribing fires immediately with the store's current state, which is
      // how a layer that had no data at mount picks it up without MapView
      // knowing which store it was waiting for.
      entry.unsub = def.subscribe((storeState) => applyState(entry, storeState));

      return entry;
    });

    entriesRef.current = entries;
    syncRef.current = syncAll;
    syncAll();

    return () => {
      syncRef.current = null;

      for (const entry of entries) {
        entry.unsub();
        if (entry.attached) stack.remove(entry.attached);
      }

      entriesRef.current = [];
    };
  }, [map]);

  /* ---------------------------------------------------------------- *
   * 3. Visibility and opacity
   * ---------------------------------------------------------------- */
  useEffect(() => {
    syncRef.current?.();
  }, [layerVisibility, layerOpacityState]);

  /* ---------------------------------------------------------------- *
   * 4. Display mode — restyle only, never refetch
   * ---------------------------------------------------------------- */
  useEffect(() => {
    if (!map) return;

    const palette = getPalette(displayMode);

    // The empty canvas has no layer to restyle, so it is painted directly.
    setMapBackground(map, palette.background);

    for (const entry of entriesRef.current) {
      if (entry.attached) entry.def.restyle(entry.attached, palette);
    }
  }, [map, displayMode]);

  /* ---------------------------------------------------------------- *
   * 5. Projection preset
   *
   * Raster layers bake the view projection into `imageExtent`, so they are
   * re-run through `update` to pick up the new one. Vector layers are
   * unaffected: their geometries are lon/lat and the user projection handles
   * the rest, which is exactly why it was declared.
   * ---------------------------------------------------------------- */
  useEffect(() => {
    if (!map) return;

    applyProjectionPreset(map, projection, vessel ? [vessel.lon, vessel.lat] : null);

    for (const entry of entriesRef.current) {
      if (entry.lastState === undefined) continue;
      entry.current = entry.def.update(entry.current, entry.lastState);
    }

    syncRef.current?.();
  }, [map, projection]);

  /* ---------------------------------------------------------------- *
   * 6. Follow own ship
   *
   * Debounce lives in `setFollowShip`, so tracking a 1 Hz GPS stream here is
   * safe.
   * ---------------------------------------------------------------- */
  useEffect(() => {
    if (!map) return;

    const position: [number, number] | null = vessel ? [vessel.lon, vessel.lat] : null;
    setFollowShip(map, position, followShip);
  }, [map, followShip, vessel]);

  /* ---------------------------------------------------------------- *
   * 7. Time-dependent layers and the stale fade
   * ---------------------------------------------------------------- */
  useEffect(() => {
    // Plain record rather than a `Map` — `Map` in this file is OpenLayers'.
    const fadeState: Record<string, boolean> = {};

    const staleNow = (def: AuroraLayer): boolean =>
      Boolean(def.stalenessKey && isSourceStale(def.stalenessKey));

    const timer = window.setInterval(() => {
      let dirty = false;

      for (const entry of entriesRef.current) {
        // Crossing into (or out of) staleness changes opacity without any
        // store event, so it has to be detected here rather than in `sync`.
        const stale = staleNow(entry.def);
        if (fadeState[entry.def.id] !== stale) {
          fadeState[entry.def.id] = stale;
          dirty = true;
        }

        if (!entry.def.recomputeOnTick || entry.lastState === undefined) continue;
        entry.current = entry.def.update(entry.current, entry.lastState);
        dirty = true;
      }

      if (dirty) syncRef.current?.();
    }, TICK_MS);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="relative h-full w-full overflow-hidden bg-aurora-bg">
      {state === 'ready' ? null : (
        <div className="absolute inset-0 flex items-center justify-center p-6">
          <p
            className={
              state === 'loading'
                ? 'text-sm tracking-wide text-aurora-muted'
                : 'text-sm tracking-wide text-aurora-warn'
            }
            role="status"
          >
            {state === 'loading' ? 'Loading region of interest…' : EMPTY_STATE_MESSAGE}
          </p>
        </div>
      )}

      {/* The container is always mounted so OpenLayers owns the element for the
          map's whole lifetime; the empty state is overlaid on top of it. */}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}

export { EMPTY_STATE_MESSAGE as MAP_UNAVAILABLE_MESSAGE };
