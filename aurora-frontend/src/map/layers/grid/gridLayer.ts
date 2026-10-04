/**
 * Graticule layer.
 *
 * Static reference geometry: it has no backing store and never goes stale. It
 * is on by default because it is part of the chart — a lat/lon reading aid
 * that has to be switched on before it can be read is not a reading aid.
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
    style: getGridStyle(getPalette()),
    // Top of the stack, deliberately. The graticule is a navigation
    // reference — like a compass rose on a paper chart it must stay visible
    // whatever is painted underneath it, the SIC raster included.
    zIndex: 90,
    declutter: false,
  });
}

export const grid: AuroraLayer = {
  id: 'grid',
  title: 'Graticule',
  category: 'reference',
  defaultVisible: true,
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
