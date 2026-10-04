/**
 * Iceberg layer — hazard positions.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useIcebergStore, type IcebergStore } from '@/stores/icebergStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { createIcebergSource, icebergFeatures, syncIcebergSource } from './icebergSource';
import { getIcebergStyle } from './icebergStyle';

type IcebergLayer = VectorLayer<GeoFeature>;

function isIcebergLayer(layer: AuroraOlLayer | null): layer is IcebergLayer {
  return layer instanceof VectorLayer;
}

function build(state: IcebergStore): IcebergLayer | null {
  const features = icebergFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createIcebergSource(features),
    style: getIcebergStyle(getPalette()),
    zIndex: 45,
  });
}

export const iceberg: AuroraLayer = {
  id: 'iceberg',
  title: 'Icebergs',
  category: 'ice',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'icebergs',

  createLayer: () => build(useIcebergStore.getState()),

  update: (layer, state) => {
    const store = state as IcebergStore;
    const features = icebergFeatures(store);
    if (!features) return null;

    if (!layer || !isIcebergLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncIcebergSource(source, features);
    else layer.setSource(createIcebergSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isIcebergLayer(layer)) layer.setStyle(getIcebergStyle(palette));
  },

  subscribe: (onChange) => useIcebergStore.subscribe((state) => onChange(state)),
};
