import { create } from 'zustand';
import type { Iceberg } from '@/types/iceberg';
import { createDataSlice, type DataStore } from './createDataStore';

/**
 * Latest iceberg positions with drift cones, fetched from
 * `GET /api/icebergs/current`.
 */
export type IcebergStore = DataStore<Iceberg[]>;

export const useIcebergStore = create<IcebergStore>()((set, get, api) => ({
  ...createDataSlice<Iceberg[], IcebergStore>()(set, get, api),
}));
