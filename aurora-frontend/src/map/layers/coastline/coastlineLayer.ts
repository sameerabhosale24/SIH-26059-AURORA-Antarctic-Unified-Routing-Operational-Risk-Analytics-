/**
 * Coastline layer.
 *
 * Absent until `GET /api/coastline` has answered with geometry. The layer
 * object, when it exists, never changes: the source is built once and reused
 * for the life of the map.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { coastlineSource, subscribeCoastline } from './coastlineSource';
import { getCoastlineStyle } from './coastlineStyle';

type CoastlineLayer = VectorLayer<GeoFeature>;

function isCoastlineLayer(layer: AuroraOlLayer | null): layer is CoastlineLayer {
  return layer instanceof VectorLayer;
}

function build(): CoastlineLayer | null {
  const source = coastlineSource();
  if (!source) return null;

  return new VectorLayer<GeoFeature>({
    source,
    style: getCoastlineStyle(getPalette('day')),
    zIndex: 20,
  });
}

export const coastline: AuroraLayer = {
  id: 'coastline',
  title: 'Coastline',
  category: 'base',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: null,

  createLayer: () => build(),

  update: (layer) => {
    const source = coastlineSource();

    if (!source) return null;
    if (!layer) return build();

    if (isCoastlineLayer(layer) && layer.getSource() !== source) {
      layer.setSource(source);
    }
    return layer;
  },

  restyle: (layer, palette) => {
    if (isCoastlineLayer(layer)) layer.setStyle(getCoastlineStyle(palette));
  },

  subscribe: (onChange) => subscribeCoastline(() => onChange(undefined)),
};
