/**
 * ENC chart layer.
 *
 * Assembles `encSource` (data) and `encStyle` (portrayal) into an AuroraLayer.
 *
 * Parsing is asynchronous, so `createLayer` returns immediately with a layer
 * whose source is still empty and attaches the parsed features when the
 * `.000` files resolve. The layer object itself stays stable across
 * refreshes, so `setSource` never tears down OL's renderer batch.
 *
 * A rebuild is skipped when neither the cell list nor the dataset version has
 * changed — an unrelated store write (like a timestamp refresh) must not
 * re-assemble the chart.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useEncStore, type EncStore } from '@/stores/encStore';
import type { EncCell } from '@/types/enc';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { createGeoSource, type GeoFeature } from '../shared';
import { buildEncSource } from './encSource';
import { getEncStyle } from './encStyle';

type EncVectorLayer = VectorLayer<GeoFeature>;

/** Supersedes an in-flight build whenever a newer one starts. */
let buildToken = 0;

/** Cell list and version currently attached to the layer, for change detection. */
let attachedCells: EncCell[] | null = null;
let attachedVersion: number | null = null;

function asEncLayer(layer: AuroraOlLayer | null): EncVectorLayer | null {
  return layer instanceof VectorLayer ? (layer as EncVectorLayer) : null;
}

function hasData(state: EncStore): boolean {
  const cells = state.data?.cells;
  return cells !== undefined && cells.length > 0;
}

/**
 * Fetch, parse and attach the chart.
 *
 * Leaves the layer empty on failure: an absent chart is preferable to a wrong
 * one, and the data-health dot already reports the ENC source as missing.
 */
async function refresh(layer: EncVectorLayer, cells: EncCell[], version: number): Promise<void> {
  const token = ++buildToken;

  const source = await buildEncSource(cells, version);

  if (token !== buildToken) return;

  layer.setSource(source);
  attachedCells = cells;
  attachedVersion = version;
}

function buildLayer(state: EncStore): EncVectorLayer {
  const cells = state.data?.cells ?? [];
  const version = state.data?.version ?? 0;

  const layer = new VectorLayer<GeoFeature>({
    source: createGeoSource(),
    style: getEncStyle(getPalette()),
    // Bottom of the reference stack: everything else is drawn over the chart,
    // never the other way round.
    zIndex: 20,
  });

  // Recorded up front so the subscription's immediate `update` for this same
  // manifest is recognised as a no-op instead of starting a second parse.
  attachedCells = cells;
  attachedVersion = version;

  void refresh(layer, cells, version);
  return layer;
}

export const encLayer: AuroraLayer = {
  id: 'enc',
  title: 'ENC Chart',
  category: 'base',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'enc',

  createLayer(): AuroraOlLayer | null {
    const state = useEncStore.getState();
    if (!hasData(state)) return null;
    return buildLayer(state);
  },

  update(layer, state): AuroraOlLayer | null {
    const storeState = state as EncStore;

    if (!hasData(storeState)) {
      buildToken += 1;
      attachedCells = null;
      attachedVersion = null;
      return null;
    }

    const cells = storeState.data?.cells ?? [];
    const version = storeState.data?.version ?? 0;

    const existing = asEncLayer(layer);
    if (!existing) return buildLayer(storeState);

    // Reference equality: the manifest is replaced wholesale on each fetch, so
    // an unchanged array identity means an unchanged cell list.
    if (cells === attachedCells && version === attachedVersion) return existing;

    void refresh(existing, cells, version);
    return existing;
  },

  restyle(layer, palette): void {
    const existing = asEncLayer(layer);
    if (existing) existing.setStyle(getEncStyle(palette));
  },

  subscribe(onChange): () => void {
    onChange(useEncStore.getState());
    return useEncStore.subscribe((state) => onChange(state));
  },
};
