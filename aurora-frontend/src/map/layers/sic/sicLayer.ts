/**
 * SIC layer — the selected forecast raster.
 *
 * The layer object survives a horizon change; only its source is swapped, so
 * OpenLayers tears down one image source and installs another without
 * rebuilding the layer's position in the stack.
 */
import ImageLayer from 'ol/layer/Image';
import type ImageStatic from 'ol/source/ImageStatic';

import { useSicStore, type SicStore } from '@/stores/sicStore';
import type { SicFrameMeta } from '@/types/sic';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import {
  SIC_FRAME_PROP,
  SIC_PROJ_PROP,
  createSicSource,
  selectedFrame,
  viewProjectionCode,
} from './sicSource';
import { SIC_FILTER_PROP, attachImageFilter, sicFilterFor } from './sicStyle';

type SicLayer = ImageLayer<ImageStatic>;

function isSicLayer(layer: AuroraOlLayer | null): layer is SicLayer {
  return layer instanceof ImageLayer;
}

function build(state: SicStore): SicLayer | null {
  const frame = selectedFrame(state);
  if (!frame) return null;

  const projectionCode = viewProjectionCode();
  const layer = new ImageLayer<ImageStatic>({
    source: createSicSource(frame, projectionCode),
  });

  layer.set(SIC_FRAME_PROP, frame);
  layer.set(SIC_PROJ_PROP, projectionCode);
  layer.set(SIC_FILTER_PROP, sicFilterFor());
  attachImageFilter(layer);

  // Above the ENC and the coastline, below every hazard overlay: sea ice is
  // the chart's dominant hazard, but a target must never be hidden beneath
  // it. The graticule sits higher still — a reading aid has to be readable
  // over whatever it is measuring.
  layer.setZIndex(30);

  return layer;
}

export const sic: AuroraLayer = {
  id: 'sic',
  title: 'Sea ice forecast',
  category: 'ice',
  defaultVisible: true,
  defaultOpacity: 1,
  stalenessKey: 'SIC',

  createLayer: () => build(useSicStore.getState()),

  update: (layer, state) => {
    const store = state as SicStore;
    const frame = selectedFrame(store);
    if (!frame) return null;

    if (!layer || !isSicLayer(layer)) return build(store);

    const projectionCode = viewProjectionCode();
    const currentFrame = layer.get(SIC_FRAME_PROP) as SicFrameMeta | null;

    const sameFrame =
      currentFrame !== null &&
      currentFrame.frame_url === frame.frame_url &&
      currentFrame.frame_extent[0] === frame.frame_extent[0] &&
      currentFrame.frame_extent[1] === frame.frame_extent[1] &&
      currentFrame.frame_extent[2] === frame.frame_extent[2] &&
      currentFrame.frame_extent[3] === frame.frame_extent[3];

    if (!sameFrame || layer.get(SIC_PROJ_PROP) !== projectionCode) {
      layer.setSource(createSicSource(frame, projectionCode));
      layer.set(SIC_FRAME_PROP, frame);
      layer.set(SIC_PROJ_PROP, projectionCode);
    }

    return layer;
  },

  restyle: (layer) => {
    if (isSicLayer(layer)) layer.set(SIC_FILTER_PROP, sicFilterFor());
  },

  subscribe: (onChange) => useSicStore.subscribe((state) => onChange(state)),
};
