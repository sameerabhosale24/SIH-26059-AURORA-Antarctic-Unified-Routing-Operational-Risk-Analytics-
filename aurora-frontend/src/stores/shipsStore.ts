/**
 * The fleet: every vessel blueprint the signed-in operator may use.
 *
 * One collection, loaded on demand by the ships pages — the map views do not
 * subscribe to it. Live telemetry lives in `vesselStore`; this store owns only
 * the static records, so an in-flight edit cannot blank the map.
 */
import { create } from 'zustand';

import {
  createVessel,
  deleteVessel,
  getVessel,
  getVessels,
  updateVessel,
} from '@/services/api';
import type { Vessel, VesselBlueprint, VesselPatch } from '@/types/ship';

export interface ShipsStore {
  list: Vessel[];
  loading: boolean;
  error: string | null;
  loadedAt: number | null;

  /** Load (or reload) the fleet. Concurrent callers share one request. */
  fetchShips(force?: boolean): Promise<void>;
  /** One vessel by id, bypassing `list` — the detail page may be deep-linked. */
  fetchShip(id: number): Promise<Vessel | null>;
  createShip(blueprint: VesselBlueprint): Promise<Vessel | null>;
  patchShip(id: number, patch: VesselPatch): Promise<Vessel | null>;
  removeShip(id: number): Promise<boolean>;
  /** Drop the cache — called on sign-out so the next operator sees their own. */
  reset(): void;
}

let inflight: Promise<void> | null = null;

export const useShipsStore = create<ShipsStore>()((set, get) => ({
  list: [],
  loading: false,
  error: null,
  loadedAt: null,

  fetchShips: async (force = false) => {
    if (inflight) return inflight;
    if (get().loading) return;

    if (!force && get().loadedAt !== null && get().error === null) return;

    set({ loading: true, error: null });

    inflight = (async () => {
      try {
        const list = await getVessels();
        set({ list, loading: false, error: null, loadedAt: Date.now() });
      } catch (cause) {
        set({ loading: false, error: toMessage(cause) });
      } finally {
        inflight = null;
      }
    })();

    return inflight;
  },

  fetchShip: async (id) => {
    try {
      const vessel = await getVessel(id);

      // Deep link must not leave the fleet list stale: fold it in.
      set((state) => ({
        list: state.list.some((v) => v.id === id)
          ? state.list.map((v) => (v.id === id ? vessel : v))
          : [...state.list, vessel],
      }));

      return vessel;
    } catch (cause) {
      set({ error: toMessage(cause) });
      return null;
    }
  },

  createShip: async (blueprint) => {
    set({ loading: true, error: null });

    try {
      const vessel = await createVessel(blueprint);
      set((state) => ({
        list: [...state.list, vessel],
        loading: false,
        error: null,
        loadedAt: Date.now(),
      }));
      return vessel;
    } catch (cause) {
      set({ loading: false, error: toMessage(cause) });
      return null;
    }
  },

  patchShip: async (id, patch) => {
    try {
      const vessel = await updateVessel(id, patch);
      set((state) => ({
        list: state.list.map((v) => (v.id === id ? vessel : v)),
        error: null,
      }));
      return vessel;
    } catch (cause) {
      set({ error: toMessage(cause) });
      return null;
    }
  },

  removeShip: async (id) => {
    try {
      await deleteVessel(id);
      set((state) => ({ list: state.list.filter((v) => v.id !== id), error: null }));
      return true;
    } catch (cause) {
      set({ error: toMessage(cause) });
      return false;
    }
  },

  reset: () => set({ list: [], loading: false, error: null, loadedAt: null }),
}));

function toMessage(cause: unknown): string {
  if (cause && typeof cause === 'object' && 'status' in cause) {
    const status = (cause as { status?: unknown }).status;
    if (status === 401) return 'Session expired. Sign in again.';
    if (status === 403) return 'This operator may not manage that vessel.';
    if (status === 404) return 'That vessel no longer exists.';
  }
  if (cause instanceof TypeError) return 'Cannot reach the AURORA backend. Is it running?';
  if (cause instanceof Error) return cause.message;
  return 'Request failed.';
}
