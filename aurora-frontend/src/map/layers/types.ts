/**
 * The AuroraLayer contract.
 *
 * Every map layer is split into three files, mirroring an ECDIS separation of
 * concerns:
 *
 *   `<name>Source.ts` — data acquisition and store subscription. Returns `null`
 *                       when the store holds no data, so an empty layer is never
 *                       fabricated.
 *   `<name>Style.ts`  — portrayal. Takes a {@link Palette}; never hardcodes a
 *                       colour.
 *   `<name>Layer.ts`  — the assembled {@link AuroraLayer}.
 *
 * `restyle()` exists so switching display mode (Day/Dusk/Night) re-portrays the
 * layers **without refetching anything**. That separation is deliberate: a
 * palette change must not cause a network request.
 */
import type BaseLayer from 'ol/layer/Base';
import type Map from 'ol/Map';

import type { DisplayMode, Palette } from '@/config/palettes';
import type { StalenessSource } from '@/config/constants';

export type LayerCategory = 'base' | 'ice' | 'traffic' | 'route' | 'weather' | 'reference';

/**
 * Note on types: the brief writes `ol.layer.Layer`, but OpenLayers has no such
 * export. The base class every concrete layer extends is `ol/layer/Base`'s
 * default export, which is what `Map.addLayer` accepts.
 */
export type AuroraOlLayer = BaseLayer;

export interface AuroraLayer {
  /** Stable key used in `uiStore.layerVisibility` / `layerOpacity`. */
  id: string;
  title: string;
  category: LayerCategory;
  defaultVisible: boolean;
  defaultOpacity: number;

  /**
   * Staleness source driving the fade-to-50 % rule and the StatusBar health
   * dot. `null` for layers whose data is immutable reference material (the
   * graticule), which therefore never go stale.
   */
  stalenessKey: StalenessSource | null;

  /**
   * Build the layer from current store contents.
   * @returns `null` when there is no data to draw.
   */
  createLayer(map: Map): AuroraOlLayer | null;

  /**
   * Apply new store state to an existing layer.
   *
   * Must update features in place where possible — recreating the source on
   * every 1 Hz GPS tick or every AIS frame would thrash the renderer.
   *
   * @returns the layer to use from now on, or `null` if there is no data.
   */
  update(layer: AuroraOlLayer | null, state: unknown): AuroraOlLayer | null;

  /** Re-apply portrayal for a new display mode. Must not fetch anything. */
  restyle(layer: AuroraOlLayer, palette: Palette): void;

  /**
   * Opt in to a periodic rebuild while the view is otherwise idle.
   *
   * Set only by layers whose feature properties encode an *age* (AIS targets
   * fading after `AIS_LIFETIME.FADE_AFTER_SECONDS`). OpenLayers re-runs style
   * functions on pan and zoom but not on the passage of time, so without this
   * a target that stops being reported would never dim.
   *
   * Left off for layers whose contents are a pure function of the store —
   * rebuilding those every second would churn the renderer for no change.
   */
  recomputeOnTick?: boolean;

  /**
   * Subscribe to the layer's backing store.
   *
   * Keeping this on the layer means MapView never needs to know which store a
   * given layer reads. The callback fires immediately with current state so a
   * layer that had no data at mount picks it up.
   */
  subscribe(onChange: (state: unknown) => void): () => void;
}

/** Ordering of categories in the LayerManager, bottom of the stack first. */
export const CATEGORY_ORDER: readonly LayerCategory[] = [
  'base',
  'reference',
  'ice',
  'route',
  'traffic',
  'weather',
];

export const CATEGORY_LABELS: Record<LayerCategory, string> = {
  base: 'Base chart',
  reference: 'Reference',
  ice: 'Ice',
  route: 'Route',
  traffic: 'Traffic',
  weather: 'Weather',
};

/**
 * Chrome variants per display mode, applied as a class on the app root.
 *
 * These are whole-console themes, not tokens: they set the root background and
 * foreground together so the chrome outside the panels visibly follows the
 * bridge-lighting setting. Panels keep their own aurora tokens, so only the
 * shell colour changes with them.
 */
export const CHROME_CLASS: Record<DisplayMode, string> = {
  day: 'bg-slate-100 text-slate-900',
  dusk: 'bg-slate-800 text-slate-100',
  night: 'bg-black text-red-100',
};
