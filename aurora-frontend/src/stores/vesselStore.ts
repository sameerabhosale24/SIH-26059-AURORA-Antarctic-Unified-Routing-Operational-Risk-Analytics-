import { create } from 'zustand';

import { vesselWs } from '@/services/websocket';
import type { VesselState } from '@/types/vessel';
import type { Vessel } from '@/types/ship';
import { createDataSlice, type DataStore } from './createDataStore';
import { bindStatus, pickRecord, rejectFrame } from './wsBinding';

/**
 * Own-ship state, fed by `WS /ws/vessel`, plus the blueprint of the vessel the
 * operator has selected.
 *
 * Two facts, one store, because the operator thinks of them as "my ship": the
 * live telemetry (`data`) and the static limits it must be measured against
 * (`blueprint`). `vesselId` is the id in the URL — `null` only while a route
 * guard has not resolved it yet, after which a map view must show its blocking
 * overlay rather than plot anything.
 *
 * `init()` connects the channel exactly once per app lifetime and returns a
 * disposer; it is safe to call again after a dispose because `connect()` is
 * idempotent.
 */
export interface VesselStore extends DataStore<VesselState> {
  /** Id from the route. `null` before the first `setVessel`. */
  vesselId: number | null;
  /** Static ship record for `vesselId`. `null` until fetched. */
  blueprint: Vessel | null;

  setVessel(id: number, blueprint: Vessel): void;
  /** Detach from the current vessel — sign-out or returning to the fleet. */
  clearVessel(): void;

  init(): () => void;
}

const CHANNEL = 'vessel';

export const useVesselStore = create<VesselStore>()((set, get, api) => ({
  ...createDataSlice<VesselState, VesselStore>()(set, get, api),

  vesselId: null,
  blueprint: null,

  setVessel: (id, blueprint) => {
    const previous = get().vesselId;
    const changed = previous !== id;

    // Changing ship invalidates everything derived from the old one: telemetry,
    // staleness, and the timestamps the fresh-data store stamps on arrival.
    if (changed) get().clear();

    set({ vesselId: id, blueprint });
  },

  clearVessel: () => {
    get().clear();
    set({ vesselId: null, blueprint: null });
  },

  init: () => {
    const offMessage = vesselWs.onMessage((payload) => {
      const state = pickRecord<VesselState>(payload, ['vessel', 'state', 'latest']);

      if (!state || typeof state.lat !== 'number' || typeof state.lon !== 'number') {
        rejectFrame(CHANNEL, payload);
        return;
      }

      get().set(state);
    });

    const offStatus = bindStatus(CHANNEL, (handler) => vesselWs.onStatus(handler));
    vesselWs.connect();

    return () => {
      offMessage();
      offStatus();
      vesselWs.close();
    };
  },
}));
