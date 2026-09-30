/**
 * Graticule layer.
 *
 * Static reference geometry: it has no backing store, never goes stale and is
 * off by default so it cannot be mistaken for charted data.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { gridSource } from './gridSource';
import { getGridStyle } from './gridStyle';

type GridLayer = VectorLayer<GeoFeature>;

function isGridLayer(layer: AuroraOlLayer | null): layer is GridLayer {
  return layer instanceof VectorLayer;
}

function build(): GridLayer | null {
  const source = gridSource();
  if (!source) return null;

  return new VectorLayer<GeoFeature>({
    source,
    style: getGridStyle(getPalette('day')),
    // Above the SIC raster and the ENC, but below every operational overlay —
    // a reading aid must never sit on top of a route or a target.
    zIndex: 30,
    declutter: false,
  });
}

export const grid: AuroraLayer = {
  id: 'grid',
  title: 'Graticule',
  category: 'reference',
  defaultVisible: false,
  defaultOpacity: 1,
  stalenessKey: null,

  createLayer: () => build(),

  update: (layer) => (layer && isGridLayer(layer) ? layer : build()),

  restyle: (layer, palette) => {
    if (isGridLayer(layer)) layer.setStyle(getGridStyle(palette));
  },

  // No store exists for static reference geometry; the callback still fires
  // once so MapView treats this layer uniformly with the rest.
  subscribe: (onChange) => {
    onChange(null);
    return () => undefined;
  },
};
