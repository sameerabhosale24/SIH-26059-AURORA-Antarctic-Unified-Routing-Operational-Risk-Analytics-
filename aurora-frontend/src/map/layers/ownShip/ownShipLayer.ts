/**
 * Own-ship layer.
 *
 * Sits above every other overlay: the vessel is the frame of reference for the
 * whole display and must never be covered by a route or a target.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useVesselStore, type VesselStore } from '@/stores/vesselStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import {
  createOwnShipSource,
  ownShipFeatures,
  syncOwnShipSource,
} from './ownShipSource';
import { getOwnShipStyle } from './ownShipStyle';

type OwnShipLayer = VectorLayer<GeoFeature>;

function isOwnShipLayer(layer: AuroraOlLayer | null): layer is OwnShipLayer {
  return layer instanceof VectorLayer;
}

function build(state: VesselStore): OwnShipLayer | null {
  const features = ownShipFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createOwnShipSource(features),
    style: getOwnShipStyle(getPalette('day')),
    zIndex: 95,
  });
}

export const ownShip: AuroraLayer = {
  id: 'ownShip',
  title: 'Own ship',
  category: 'traffic',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'GPS',

  createLayer: () => build(useVesselStore.getState()),

  update: (layer, state) => {
    const store = state as VesselStore;
    const features = ownShipFeatures(store);
    if (!features) return null;

    if (!layer || !isOwnShipLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncOwnShipSource(source, features);
    else layer.setSource(createOwnShipSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isOwnShipLayer(layer)) layer.setStyle(getOwnShipStyle(palette));
  },

  subscribe: (onChange) => useVesselStore.subscribe((state) => onChange(state)),
};
