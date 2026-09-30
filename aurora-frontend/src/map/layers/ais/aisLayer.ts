/**
 * AIS layer — traffic targets.
 *
 * Risk, CPA and TCPA are all backend-computed; this layer only places and
 * portrays them.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useAisStore, type AisStore } from '@/stores/aisStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { aisFeatures, createAisSource, syncAisSource } from './aisSource';
import { getAisStyle } from './aisStyle';

type AisLayer = VectorLayer<GeoFeature>;

function isAisLayer(layer: AuroraOlLayer | null): layer is AisLayer {
  return layer instanceof VectorLayer;
}

function build(state: AisStore): AisLayer | null {
  const features = aisFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createAisSource(features),
    style: getAisStyle(getPalette('day')),
    zIndex: 85,
  });
}

export const ais: AuroraLayer = {
  id: 'ais',
  title: 'AIS targets',
  category: 'traffic',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'AIS',
  // Target age drives the fade, and age advances without a new WS frame.
  recomputeOnTick: true,

  createLayer: () => build(useAisStore.getState()),

  update: (layer, state) => {
    const store = state as AisStore;
    const features = aisFeatures(store);
    if (!features) return null;

    if (!layer || !isAisLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncAisSource(source, features);
    else layer.setSource(createAisSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isAisLayer(layer)) layer.setStyle(getAisStyle(palette));
  },

  subscribe: (onChange) => useAisStore.subscribe((state) => onChange(state)),
};
