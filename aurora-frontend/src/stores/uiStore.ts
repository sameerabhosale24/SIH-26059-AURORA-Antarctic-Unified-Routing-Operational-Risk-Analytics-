import { create } from 'zustand';
import type { DisplayMode } from '@/config/palettes';

/** Application modes. Exactly one is active at a time. */
export type UiMode = 'operational' | 'planning' | 'analysis' | 'settings';

/** Named map projections/presets selectable from the projection switcher. */
export type UiProjection = 'corridor' | 'local' | 'polar';

export interface UiStoreState {
  mode: UiMode;
  projection: UiProjection;
  /**
   * Bridge-lighting display mode. Drives both the S-52 chart palette and the
   * UI chrome variant. Changing it re-styles layers only — it never refetches.
   */
  displayMode: DisplayMode;
  followShip: boolean;
  /** Layer id → visible. Populated by Part 2's LayerManager. */
  layerVisibility: Record<string, boolean>;
  /** Layer id → opacity in 0..1. */
  layerOpacity: Record<string, number>;
  /** Whether the DataFreshness drawer is open. */
  freshnessOpen: boolean;
  setMode(mode: UiMode): void;
  setProjection(projection: UiProjection): void;
  setDisplayMode(mode: DisplayMode): void;
  setFollowShip(followShip: boolean): void;
  toggleLayer(id: string): void;
  setOpacity(id: string, value: number): void;
  toggleFreshness(): void;
}

/** Opacity is clamped here so a bad slider value can never blank a layer. */
function clampOpacity(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(1, Math.max(0, value));
}

export const useUiStore = create<UiStoreState>()((set) => ({
  mode: 'operational',
  projection: 'corridor',
  displayMode: 'day',
  followShip: false,
  layerVisibility: {},
  layerOpacity: {},
  freshnessOpen: false,

  setMode: (mode) => set({ mode }),
  setProjection: (projection) => set({ projection }),
  setDisplayMode: (displayMode) => set({ displayMode }),
  setFollowShip: (followShip) => set({ followShip }),

  toggleLayer: (id) =>
    set((state) => ({
      layerVisibility: { ...state.layerVisibility, [id]: !state.layerVisibility[id] },
    })),

  setOpacity: (id, value) =>
    set((state) => ({
      layerOpacity: { ...state.layerOpacity, [id]: clampOpacity(value) },
    })),

  toggleFreshness: () => set((state) => ({ freshnessOpen: !state.freshnessOpen })),
}));
