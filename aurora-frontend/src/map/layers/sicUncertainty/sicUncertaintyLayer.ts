/**
 * SIC uncertainty layer — the 90 % interval raster for the selected frame.
 *
 * Sits immediately above the concentration raster it qualifies, and below all
 * vector overlays: the band explains the ice field, it does not replace it.
 */
import ImageLayer from 'ol/layer/Image';
import type ImageStatic from 'ol/source/ImageStatic';

import { useSicStore, type SicStore } from '@/stores/sicStore';
import { useUiStore } from '@/stores/uiStore';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { SIC_FRAME_PROP, SIC_PROJ_PROP, viewProjectionCode } from '../sic/sicSource';
import {
  SIC_FILTER_PROP,
  attachImageFilter,
  uncertaintyFilterFor,
} from './sicUncertaintyStyle';
import { isCurrent, selectedFrame, uncertaintySource } from './sicUncertaintySource';

type UncertaintyLayer = ImageLayer<ImageStatic>;

function isUncertaintyLayer(layer: AuroraOlLayer | null): layer is UncertaintyLayer {
  return layer instanceof ImageLayer;
}

function build(state: SicStore): UncertaintyLayer | null {
  const frame = selectedFrame(state);
  const projectionCode = viewProjectionCode();

  const source = uncertaintySource(frame, projectionCode);
  if (!source) return null;

  const layer = new ImageLayer<ImageStatic>({ source });
  layer.set(SIC_FRAME_PROP, frame);
  layer.set(SIC_PROJ_PROP, projectionCode);
  layer.set(SIC_FILTER_PROP, uncertaintyFilterFor(useUiStore.getState().displayMode));
  attachImageFilter(layer);

  layer.setZIndex(41);

  return layer;
}

export const sicUncertainty: AuroraLayer = {
  id: 'sicUncertainty',
  title: 'Ice forecast uncertainty',
  category: 'ice',
  defaultVisible: false,
  defaultOpacity: 1,
  stalenessKey: 'SIC',

  createLayer: () => build(useSicStore.getState()),

  update: (layer, state) => {
    const store = state as SicStore;
    const frame = selectedFrame(store);
    const projectionCode = viewProjectionCode();

    const source = uncertaintySource(frame, projectionCode);
    if (!source) return null;

    if (!layer || !isUncertaintyLayer(layer)) return build(store);

    if (!isCurrent(layer, frame, projectionCode)) {
      layer.setSource(source);
      layer.set(SIC_FRAME_PROP, frame);
      layer.set(SIC_PROJ_PROP, projectionCode);
    }

    return layer;
  },

  restyle: (layer, palette) => {
    if (isUncertaintyLayer(layer)) {
      layer.set(SIC_FILTER_PROP, uncertaintyFilterFor(palette.mode));
    }
  },

  subscribe: (onChange) => useSicStore.subscribe((state) => onChange(state)),
};
