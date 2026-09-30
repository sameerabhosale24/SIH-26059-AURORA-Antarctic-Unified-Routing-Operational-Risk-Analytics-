/**
 * SIC raster "style".
 *
 * A raster has no OpenLayers style object, so the mode-dependent adjustment
 * lives in a canvas filter applied around the draw. OpenLayers dispatches
 * `prerender` immediately before the layer paints and `postrender`
 * immediately after, and both hand us the same context — so the filter can be
 * installed and removed without leaving a residue on the shared canvas.
 *
 * The filter string comes from `SIC_IMAGE_FILTER`, which is a palette
 * adjustment (brightness/contrast per bridge-lighting mode), not a recolouring
 * of the data: the PNG's class colours are the backend's, unchanged.
 */
import type RenderEvent from 'ol/render/Event';

import { SIC_IMAGE_FILTER, UNCERTAINTY_IMAGE_FILTER } from '@/config/constants';
import type { DisplayMode } from '@/config/palettes';

/** Layer property holding the current filter string. */
export const SIC_FILTER_PROP = 'aurora-filter';

export function sicFilterFor(mode: DisplayMode): string {
  return SIC_IMAGE_FILTER[mode];
}

export function uncertaintyFilterFor(mode: DisplayMode): string {
  return UNCERTAINTY_IMAGE_FILTER[mode];
}

function readContext(event: RenderEvent): CanvasRenderingContext2D | null {
  const context = event.context as CanvasRenderingContext2D | undefined | null;
  if (!context || typeof context.filter !== 'string') return null;
  return context;
}

/**
 * Install the filter hooks on an image layer.
 *
 * Returns the number of listeners removed when the layer is disposed, so the
 * caller can confirm teardown. The filter value itself is read from the layer
 * on every frame, which is what makes `restyle` a property write rather than
 * an unsubscription dance.
 */
export function attachImageFilter(layer: {
  on(type: string, listener: (event: RenderEvent) => void): unknown;
  un(type: string, listener: (event: RenderEvent) => void): unknown;
  get(key: string): unknown;
}): () => void {
  const apply = (event: RenderEvent): void => {
    const context = readContext(event);
    if (!context) return;

    const filter = layer.get(SIC_FILTER_PROP);
    context.filter = typeof filter === 'string' && filter !== '' ? filter : 'none';
  };

  const clear = (event: RenderEvent): void => {
    const context = readContext(event);
    if (context) context.filter = 'none';
  };

  layer.on('prerender', apply);
  layer.on('postrender', clear);

  return () => {
    layer.un('prerender', apply);
    layer.un('postrender', clear);
  };
}
