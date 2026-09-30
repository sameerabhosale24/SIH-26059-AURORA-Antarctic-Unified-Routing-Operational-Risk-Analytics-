import { create } from 'zustand';
import type { DataVersion } from '@/types/version';
import type { WsStatus } from '@/services/websocket';

/** Health of the REST API as observed by the client. */
export type ApiStatus = 'ok' | 'degraded' | 'down';

export interface DataStoreState {
  /** Latest `/api/version` snapshot, or null before the first success. */
  versions: DataVersion | null;
  /** Sticky until the next successful call: the API is assumed down at boot. */
  apiStatus: ApiStatus;
  /** Per-channel WebSocket state, keyed by channel name (`vessel`, `ais`, …). */
  wsStatus: Record<string, WsStatus>;
  setVersions(versions: DataVersion): void;
  setApiStatus(status: ApiStatus): void;
  setWsStatus(channel: string, status: WsStatus): void;
}

export const useDataStore = create<DataStoreState>()((set) => ({
  versions: null,
  apiStatus: 'down',
  wsStatus: {},

  setVersions: (versions) => set({ versions, apiStatus: 'ok' }),
  setApiStatus: (apiStatus) => set({ apiStatus }),
  setWsStatus: (channel, status) =>
    set((state) => ({ wsStatus: { ...state.wsStatus, [channel]: status } })),
}));

/**
 * Aggregate the per-channel states into one badge for the status overlay.
 * Any error wins over connecting, which wins over any open channel.
 */
export function aggregateWsStatus(statuses: Record<string, WsStatus>): WsStatus {
  const values = Object.values(statuses);

  if (values.length === 0) return 'closed';
  if (values.includes('error')) return 'error';
  if (values.includes('connecting')) return 'connecting';
  if (values.includes('open')) return 'open';
  return 'closed';
}
