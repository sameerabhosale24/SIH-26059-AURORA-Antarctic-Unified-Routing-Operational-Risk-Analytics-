import { create } from 'zustand';
import type { SicFramesResponse } from '@/types/sic';
import { createDataSlice, type DataStore } from './createDataStore';

/** Forecast horizon in days. */
export type SicHorizon = 1 | 2 | 3;

/**
 * SIC frame manifest plus the operator's horizon selection.
 *
 * `version` mirrors `data.version` for quick cache-busting reads; it is null
 * until a manifest has been fetched.
 */
export interface SicStore extends DataStore<SicFramesResponse> {
  version: number | null;
  selectedHorizon: SicHorizon;
  setHorizon(horizon: SicHorizon): void;
  /** Sync `version` from a freshly fetched manifest. */
  setManifest(manifest: SicFramesResponse): void;
}

export const useSicStore = create<SicStore>()((set, get, api) => ({
  ...createDataSlice<SicFramesResponse, SicStore>()(set, get, api),

  version: null,
  selectedHorizon: 1,

  setHorizon: (selectedHorizon) => set({ selectedHorizon }),

  setManifest: (manifest) => set({ data: manifest, version: manifest.version, lastUpdated: Date.now(), error: null }),
}));
