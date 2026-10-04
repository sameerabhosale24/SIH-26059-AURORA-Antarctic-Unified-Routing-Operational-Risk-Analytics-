/**
 * Reference-corridor layer.
 *
 * Static geometry: two great-circle tracks from Cape Town, the SIC coverage
 * rectangle and its caption. It is rebuilt only when the station list lands,
 * because that is the one input that can change the endpoints.
 *
 * The layer sits above the rasters and the routes so the corridor stays
 * readable over the SIC field and the A* result alike — it is chart
 * reference geometry, not an operational overlay — and below the graticule.
 */
import VectorLayer from 'ol/layer/Vector';
import type Map from 'ol/Map';

import { getPalette } from '@/config/palettes';
import { CORRIDOR_BOUNDS, getMapRoi } from '@/map/mapSetup';
import { useStationsStore, type StationsStore } from '@/stores/stationsStore';
import type { Roi } from '@/types/common';
import type { GeoFeature, GeoVectorSource } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import {
  corridorFeatures,
  createCorridorSource,
  resolveEndpoints,
  syncCorridorSource,
} from './corridorSource';
import { getCorridorStyle } from './corridorStyle';

type CorridorLayer = VectorLayer<GeoFeature>;

/** Viewport size used when the map has not been laid out yet. */
const FALLBACK_SIZE: [number, number] = [1024, 768];

/** Layer property holding the ROI the rectangle was drawn from. */
const ROI_PROP = 'aurora-corridor-roi';

/** Layer property holding the resolution the coverage rectangle opens at. */
const ROI_VISIBLE_FROM = 'aurora-corridor-roi-visible-from';

function isCorridorLayer(layer: AuroraOlLayer | null): layer is CorridorLayer {
  return layer instanceof VectorLayer;
}

/**
 * Resolution at which the corridor bounds exactly fill the viewport.
 *
 * Computed with the view's own arithmetic (the same call `View#fit` makes, minus
 * the fit padding), so "zoomed out past the corridor bounds" is decided by the
 * map rather than by a magic number. Viewport size is sampled at build time;
 * the number only shifts if the window is resized.
 */
function roiVisibleFrom(map: Map): number {
  const size = map.getSize() ?? FALLBACK_SIZE;
  const resolution = map.getView().getResolutionForExtent(CORRIDOR_BOUNDS, size);

  // Never fall back to "always visible": if the view cannot answer, the
  // rectangle stays hidden rather than cluttering a detailed chart.
  return Number.isFinite(resolution) && resolution > 0 ? resolution : Number.POSITIVE_INFINITY;
}

function build(map: Map, state: StationsStore): CorridorLayer | null {
  const roi = getMapRoi(map);
  if (!roi) return null;

  const visibleFrom = roiVisibleFrom(map);
  const layer = new VectorLayer<GeoFeature>({
    source: createCorridorSource(corridorFeatures(roi, resolveEndpoints(state))),
    style: getCorridorStyle(getPalette(), visibleFrom),
    zIndex: 85,
  });

  layer.set(ROI_PROP, roi);
  layer.set(ROI_VISIBLE_FROM, visibleFrom);

  return layer;
}

export const corridor: AuroraLayer = {
  id: 'corridor',
  title: 'Reference corridor',
  category: 'reference',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: null,

  createLayer: (map) => build(map, useStationsStore.getState()),

  update: (layer, state) => {
    // A rebuild needs the ROI, which only `createLayer` has — and it always
    // finds one, because the map is not built without a ROI.
    if (!layer || !isCorridorLayer(layer)) return null;

    const roi = layer.get(ROI_PROP) as Roi | null;
    if (!roi) return layer;

    const source = layer.getSource();
    if (source) {
      syncCorridorSource(source as GeoVectorSource, corridorFeatures(roi, resolveEndpoints(state as StationsStore)));
    } else {
      layer.setSource(
        createCorridorSource(corridorFeatures(roi, resolveEndpoints(state as StationsStore))),
      );
    }

    return layer;
  },

  restyle: (layer, palette) => {
    if (!isCorridorLayer(layer)) return;

    const visibleFrom = layer.get(ROI_VISIBLE_FROM);
    layer.setStyle(
      getCorridorStyle(palette, typeof visibleFrom === 'number' ? visibleFrom : Number.POSITIVE_INFINITY),
    );
  },

  subscribe: (onChange) => useStationsStore.subscribe((state) => onChange(state)),
};
