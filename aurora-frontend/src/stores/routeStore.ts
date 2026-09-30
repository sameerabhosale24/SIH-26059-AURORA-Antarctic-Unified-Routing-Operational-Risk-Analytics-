import { create } from 'zustand';

import { routeWs } from '@/services/websocket';
import type { RouteRun } from '@/types/route';
import { createDataSlice, type DataStore } from './createDataStore';
import { notify } from './toastStore';
import { bindStatus, pickRecord, rejectFrame } from './wsBinding';

/**
 * The active route run plus recent history.
 *
 * `history` is newest-first and capped by the caller; it is deliberately
 * separate from `data` so refreshing the active route never discards the
 * history the operator is comparing against.
 *
 * A pushed run raises the "review alternatives" toast: a new optimum is a
 * decision the operator has to make, not a silent background update.
 */
export interface RouteStore extends DataStore<RouteRun> {
  history: RouteRun[];
  setHistory(runs: RouteRun[]): void;
  init(): () => void;
}

const CHANNEL = 'route';

function countRoutes(run: RouteRun): number {
  return Array.isArray(run.routes) ? run.routes.length : 0;
}

export const useRouteStore = create<RouteStore>()((set, get, api) => ({
  ...createDataSlice<RouteRun, RouteStore>()(set, get, api),

  history: [],

  setHistory: (history) => set({ history }),

  init: () => {
    const offMessage = routeWs.onMessage((payload) => {
      const run = pickRecord<RouteRun>(payload, ['route_run', 'run', 'route']);

      if (!run || typeof run.id !== 'number') {
        rejectFrame(CHANNEL, payload);
        return;
      }

      const previous = get().data;
      get().set(run);

      // First run is not an update — the panel shows it either way, and a
      // toast on boot would be noise.
      if (previous && previous.id !== run.id) {
        const alternatives = Math.max(0, countRoutes(run) - 1);
        notify('Route updated', 'info', `Review ${alternatives} alternative${alternatives === 1 ? '' : 's'}`);
      }
    });

    const offStatus = bindStatus(CHANNEL, (handler) => routeWs.onStatus(handler));
    routeWs.connect();

    return () => {
      offMessage();
      offStatus();
      routeWs.close();
    };
  },
}));
