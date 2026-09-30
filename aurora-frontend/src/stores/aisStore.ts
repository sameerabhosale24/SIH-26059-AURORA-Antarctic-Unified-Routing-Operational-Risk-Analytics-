import { create } from 'zustand';

import { aisWs } from '@/services/websocket';
import type { AisTarget } from '@/types/ais';
import { createDataSlice, type DataStore } from './createDataStore';
import { bindStatus, pickList, rejectFrame } from './wsBinding';

/**
 * All known AIS targets, fed by `WS /ws/ais`.
 *
 * Each message replaces the full list — the backend does not send deltas, so
 * there is no merge step and no partially-applied frame.
 */
export interface AisStore extends DataStore<AisTarget[]> {
  init(): () => void;
}

const CHANNEL = 'ais';

export const useAisStore = create<AisStore>()((set, get, api) => ({
  ...createDataSlice<AisTarget[], AisStore>()(set, get, api),

  init: () => {
    const offMessage = aisWs.onMessage((payload) => {
      const targets = pickList<AisTarget>(payload, ['targets', 'data']);

      if (!targets) {
        rejectFrame(CHANNEL, payload);
        return;
      }

      get().set(targets);
    });

    const offStatus = bindStatus(CHANNEL, (handler) => aisWs.onStatus(handler));
    aisWs.connect();

    return () => {
      offMessage();
      offStatus();
      aisWs.close();
    };
  },
}));
