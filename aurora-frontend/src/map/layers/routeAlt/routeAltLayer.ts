/**
 * Alternative-route layer.
 *
 * Below the primary route so the recommended track is never overdrawn.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useRouteStore, type RouteStore } from '@/stores/routeStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import {
  alternativeRouteFeatures,
  createAlternativeSource,
  syncAlternativeSource,
} from './routeAltSource';
import { getAlternativeRouteStyle } from './routeAltStyle';

type RouteAltLayer = VectorLayer<GeoFeature>;

function isRouteAltLayer(layer: AuroraOlLayer | null): layer is RouteAltLayer {
  return layer instanceof VectorLayer;
}

function build(state: RouteStore): RouteAltLayer | null {
  const features = alternativeRouteFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createAlternativeSource(features),
    style: getAlternativeRouteStyle(getPalette('day')),
    zIndex: 55,
  });
}

export const routeAlt: AuroraLayer = {
  id: 'routeAlt',
  title: 'Alternative routes',
  category: 'route',
  defaultVisible: true,
  defaultOpacity: 0.9,
  stalenessKey: 'route',

  createLayer: () => build(useRouteStore.getState()),

  update: (layer, state) => {
    const store = state as RouteStore;
    const features = alternativeRouteFeatures(store);
    if (!features) return null;

    if (!layer || !isRouteAltLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncAlternativeSource(source, features);
    else layer.setSource(createAlternativeSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isRouteAltLayer(layer)) layer.setStyle(getAlternativeRouteStyle(palette));
  },

  subscribe: (onChange) => useRouteStore.subscribe((state) => onChange(state)),
};
