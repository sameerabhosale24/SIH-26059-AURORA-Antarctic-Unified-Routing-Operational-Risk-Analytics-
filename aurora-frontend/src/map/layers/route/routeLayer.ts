/**
 * Primary route layer — the recommended track and its waypoints.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useRouteStore, type RouteStore } from '@/stores/routeStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { createRouteSource, primaryRouteFeatures, syncRouteSource } from './routeSource';
import { getRouteStyle, startRouteTransition } from './routeStyle';

type RouteLayer = VectorLayer<GeoFeature>;

function isRouteLayer(layer: AuroraOlLayer | null): layer is RouteLayer {
  return layer instanceof VectorLayer;
}

/**
 * Stop any reveal still running on a previous route layer.
 *
 * Held at module scope because the transition's deadline lives there too —
 * two concurrent reveals would fight over the same style-function clock.
 */
let stopTransition: (() => void) | null = null;

/**
 * Run id the reveal was last started for.
 *
 * `update` fires on every route-store change, including ones that leave the
 * route identical; only a different run is a new line worth revealing.
 */
let lastRunId: number | null = null;

function startTransition(layer: RouteLayer, runId: number | null): void {
  if (runId === lastRunId && stopTransition) return;

  lastRunId = runId;
  stopTransition?.();
  stopTransition = startRouteTransition(layer);
}

function build(state: RouteStore): RouteLayer | null {
  const features = primaryRouteFeatures(state);
  if (!features) return null;

  const layer = new VectorLayer<GeoFeature>({
    source: createRouteSource(features),
    style: getRouteStyle(getPalette()),
    zIndex: 65,
  });

  startTransition(layer, state.data?.id ?? null);

  return layer;
}

export const route: AuroraLayer = {
  id: 'route',
  title: 'Recommended route',
  category: 'route',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'route',

  createLayer: () => build(useRouteStore.getState()),

  update: (layer, state) => {
    const store = state as RouteStore;
    const features = primaryRouteFeatures(store);
    if (!features) return null;

    if (!layer || !isRouteLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncRouteSource(source, features);
    else layer.setSource(createRouteSource(features));

    startTransition(layer, store.data?.id ?? null);

    return layer;
  },

  restyle: (layer, palette) => {
    if (isRouteLayer(layer)) layer.setStyle(getRouteStyle(palette));
  },

  subscribe: (onChange) => useRouteStore.subscribe((state) => onChange(state)),
};
