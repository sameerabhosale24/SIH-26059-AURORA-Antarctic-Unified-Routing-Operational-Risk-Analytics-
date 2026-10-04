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
  /**
   * Issue date of the newest frame in the manifest (`YYYY-MM-DD`), or `null`
   * before the first successful fetch.
   *
   * Kept alongside the frames rather than derived at every read site so the
   * status bar and the horizon panel label the same day the map is drawing.
   */
  currentDate: string | null;
  selectedHorizon: SicHorizon;
  setHorizon(horizon: SicHorizon): void;
  /** Sync `version` and `currentDate` from a freshly fetched manifest. */
  setManifest(manifest: SicFramesResponse): void;
}

/** Newest issue date in a manifest, or `null` when it publishes no frames. */
function newestDate(manifest: SicFramesResponse): string | null {
  let newest: string | null = null;
  for (const frame of manifest.frames) {
    if (newest === null || frame.date > newest) newest = frame.date;
  }
  return newest;
}

export const useSicStore = create<SicStore>()((set, get, api) => ({
  ...createDataSlice<SicFramesResponse, SicStore>()(set, get, api),

  version: null,
  currentDate: null,
  selectedHorizon: 1,

  setHorizon: (selectedHorizon) => set({ selectedHorizon }),

  setManifest: (manifest) =>
    set({
      data: manifest,
      version: manifest.version,
      currentDate: newestDate(manifest),
      lastUpdated: Date.now(),
      error: null,
    }),
}));
