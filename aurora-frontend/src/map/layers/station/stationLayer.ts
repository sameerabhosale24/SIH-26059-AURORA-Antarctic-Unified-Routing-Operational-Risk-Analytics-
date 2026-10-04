/**
 * Station layer.
 *
 * Updated in place on every store notification: the marker set is small and
 * stable, so rebuilding the source would buy nothing and would drop the
 * renderer's feature cache for no reason.
 */
import type Map from 'ol/Map';
import VectorLayer from 'ol/layer/Vector';

import { ZOOM_THRESHOLDS } from '@/config/constants';
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

/** Layer property holding the resolution the label gate opens at. */
const LABEL_RESOLUTION = 'aurora-station-label-resolution';

function isStationLayer(layer: AuroraOlLayer | null): layer is StationLayer {
  return layer instanceof VectorLayer;
}

/**
 * Resolution at which `ZOOM_THRESHOLDS.STATION_LABEL` sits on this view.
 *
 * `getResolutionForZoom` is OpenLayers' own conversion, so the gate reads the
 * same zoom numbers the controls and the docs use whatever projection is live.
 */
function labelResolution(map: Map): number {
  const resolution = map.getView().getResolutionForZoom(ZOOM_THRESHOLDS.STATION_LABEL);
  return Number.isFinite(resolution) && resolution > 0 ? resolution : Number.POSITIVE_INFINITY;
}

function build(map: Map, state: StationsStore): StationLayer | null {
  const features = stationFeatures(state);
  if (!features) return null;

  const resolution = labelResolution(map);
  const layer = new VectorLayer<GeoFeature>({
    source: createStationSource(features),
    style: getStationStyle(getPalette(), resolution),
    zIndex: 80,
  });

  layer.set(LABEL_RESOLUTION, resolution);

  return layer;
}

export const station: AuroraLayer = {
  id: 'station',
  title: 'Stations',
  category: 'reference',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: null,

  createLayer: (map) => build(map, useStationsStore.getState()),

  update: (layer, state) => {
    const store = state as StationsStore;
    const features = stationFeatures(store);
    if (!features) return null;

    // Rebuilding needs the map, which only `createLayer` has — and it always
    // has features, because the client-side stations are always present.
    if (!layer || !isStationLayer(layer)) return null;

    const source = layer.getSource();
    if (source) syncStationSource(source as GeoVectorSource, features);
    else layer.setSource(createStationSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (!isStationLayer(layer)) return;

    const stored = layer.get(LABEL_RESOLUTION);
    layer.setStyle(
      getStationStyle(palette, typeof stored === 'number' ? stored : Number.POSITIVE_INFINITY),
    );
  },

  subscribe: (onChange) => useStationsStore.subscribe((state) => onChange(state)),
};
