import { create } from 'zustand';
import type { EncManifest } from '@/types/enc';
import { createDataSlice, type DataStore } from './createDataStore';

/**
 * ENC cell manifest.
 *
 * The manifest is small and cheap to refetch; the expensive artefact is the
 * parsed geometry, which `encSource` caches by cell URL so a refetch of the
 * manifest does not re-download or re-parse every `.000` file.
 */
export type EncStore = DataStore<EncManifest>;

export const useEncStore = create<EncStore>()((set, get, api) => ({
  ...createDataSlice<EncManifest, EncStore>()(set, get, api),
}));
