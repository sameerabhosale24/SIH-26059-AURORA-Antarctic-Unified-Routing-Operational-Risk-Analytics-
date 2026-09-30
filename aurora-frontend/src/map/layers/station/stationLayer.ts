/**
 * Station layer.
 *
 * Updated in place on every store notification: the marker set is small and
 * stable, so rebuilding the source would buy nothing and would drop the
 * renderer's feature cache for no reason.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useStationsStore, type StationsStore } from '@/stores/stationsStore';
import type { GeoFeature, GeoVectorSource } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import {
  createStationSource,
  stationFeatures,
  syncStationSource,
} from './stationSource';
import { getStationStyle } from './stationStyle';

type StationLayer = VectorLayer<GeoFeature>;

function isStationLayer(layer: AuroraOlLayer | null): layer is StationLayer {
  return layer instanceof VectorLayer;
}

function build(state: StationsStore): StationLayer | null {
  const features = stationFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createStationSource(features),
    style: getStationStyle(getPalette('day')),
    zIndex: 70,
  });
}

export const station: AuroraLayer = {
  id: 'station',
  title: 'Stations',
  category: 'reference',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: null,

  createLayer: () => build(useStationsStore.getState()),

  update: (layer, state) => {
    const store = state as StationsStore;
    const features = stationFeatures(store);
    if (!features) return null;

    if (!layer || !isStationLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncStationSource(source as GeoVectorSource, features);
    else layer.setSource(createStationSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isStationLayer(layer)) layer.setStyle(getStationStyle(palette));
  },

  subscribe: (onChange) => useStationsStore.subscribe((state) => onChange(state)),
};
