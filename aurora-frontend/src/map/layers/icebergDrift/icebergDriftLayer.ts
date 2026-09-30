/**
 * Iceberg drift-cone layer.
 *
 * Split from `iceberg` so cones can be hidden without losing hazard positions.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useIcebergStore, type IcebergStore } from '@/stores/icebergStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { createDriftSource, icebergDriftFeatures, syncDriftSource } from './icebergDriftSource';
import { getIcebergDriftStyle } from './icebergDriftStyle';

type DriftLayer = VectorLayer<GeoFeature>;

function isDriftLayer(layer: AuroraOlLayer | null): layer is DriftLayer {
  return layer instanceof VectorLayer;
}

function build(state: IcebergStore): DriftLayer | null {
  const features = icebergDriftFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createDriftSource(features),
    style: getIcebergDriftStyle(getPalette('day')),
    // Below the iceberg markers: a cone must not obscure the position it
    // belongs to.
    zIndex: 75,
  });
}

export const icebergDrift: AuroraLayer = {
  id: 'icebergDrift',
  title: 'Drift cones',
  category: 'ice',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'icebergs',

  createLayer: () => build(useIcebergStore.getState()),

  update: (layer, state) => {
    const store = state as IcebergStore;
    const features = icebergDriftFeatures(store);
    if (!features) return null;

    if (!layer || !isDriftLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncDriftSource(source, features);
    else layer.setSource(createDriftSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isDriftLayer(layer)) layer.setStyle(getIcebergDriftStyle(palette));
  },

  subscribe: (onChange) => useIcebergStore.subscribe((state) => onChange(state)),
};
