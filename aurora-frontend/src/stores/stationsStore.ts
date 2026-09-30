import { create } from 'zustand';
import type { Station } from '@/types/common';
import { createDataSlice, type DataStore } from './createDataStore';

/**
 * Station metadata from `GET /api/stations` (static reference data).
 *
 * The store holds the raw list; the station layer derives per-cell cached
 * fetches from it rather than re-requesting on every render.
 */
export type StationsStore = DataStore<Station[]>;

export const useStationsStore = create<StationsStore>()((set, get, api) => ({
  ...createDataSlice<Station[], StationsStore>()(set, get, api),
}));
