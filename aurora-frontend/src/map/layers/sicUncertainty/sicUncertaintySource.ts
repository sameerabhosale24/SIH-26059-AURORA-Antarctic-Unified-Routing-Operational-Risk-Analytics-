/**
 * SIC uncertainty source.
 *
 * Shares the frame selection with the primary SIC layer so the two rasters
 * can never drift onto different issues: the interval product is defined as
 * being *of the same run* as the concentration product.
 *
 * The source is `null` when the manifest carries no `interval_url` for the
 * selected frame — a run without an uncertainty product leaves this layer
 * absent, which the layer manager surfaces as "no data", never as a blank
 * rectangle over the chart.
 */
import type ImageStatic from 'ol/source/ImageStatic';

import type { SicFrameMeta } from '@/types/sic';
import { SIC_FRAME_PROP, SIC_PROJ_PROP, createUncertaintySource, selectedFrame } from '../sic/sicSource';

export { selectedFrame };

/** The uncertainty raster for a frame and projection, or `null`. */
export function uncertaintySource(
  frame: SicFrameMeta | null,
  projectionCode: string,
): ImageStatic | null {
  if (!frame) return null;
  return createUncertaintySource(frame, projectionCode);
}

/**
 * Whether an existing layer already shows this frame in this projection.
 *
 * Deliberately reuses the SIC layer's property keys: both rasters describe one
 * frame, so recognising the same frame under the same keys is the point.
 */
export function isCurrent(
  layer: { get(key: string): unknown },
  frame: SicFrameMeta | null,
  projectionCode: string,
): boolean {
  if (!frame) return false;
  if (layer.get(SIC_PROJ_PROP) !== projectionCode) return false;

  const current = layer.get(SIC_FRAME_PROP) as SicFrameMeta | null;
  if (!current) return false;

  return (
    current.frame_url === frame.frame_url &&
    current.frame_extent[0] === frame.frame_extent[0] &&
    current.frame_extent[1] === frame.frame_extent[1] &&
    current.frame_extent[2] === frame.frame_extent[2] &&
    current.frame_extent[3] === frame.frame_extent[3]
  );
}
