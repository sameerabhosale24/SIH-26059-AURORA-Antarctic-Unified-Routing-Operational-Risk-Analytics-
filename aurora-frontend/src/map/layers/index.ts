/**
 * Layer registry.
 *
 * The single ordered list every consumer reads: `MapView` (creation and
 * subscription order), the `LayerManager` (display order), and anything that
 * needs to resolve a layer by id.
 *
 * ## Order and z-index
 *
 * Both are specified deliberately and must agree.
 *
 * - **Array order** is bottom-to-top display order in the layer manager, and
 *   is grouped by {@link CATEGORY_ORDER}.
 * - **`zIndex`** is what OpenLayers actually paints by, set on each layer
 *   individually so a layer's stacking survives the manager being collapsed,
 *   filtered, or reordered in the UI.
 *
 * The invariant to preserve when adding a layer: its `zIndex` must place it
 * where its position in this array says it is.
 *
 * ## Stacking rationale
 *
 * | band       | zIndex | contents |
 * |------------|--------|----------|
 * | chart      | 10–20  | ENC, then the coastline outline |
 * | reference  | 30     | graticule |
 * | rasters    | 40–41  | SIC, then its uncertainty band |
 * | routes     | 55–60  | alternatives, then the recommended route |
 * | positions  | 70–85  | stations, drift cones, icebergs, AIS |
 * | alarms     | 90     | alarm markers and zones |
 * | own ship   | 95     | the vessel — never covered |
 */
import type { UiStoreState } from '@/stores/uiStore';

import type { AuroraLayer, LayerCategory } from './types';
import { CATEGORY_ORDER } from './types';

import { encLayer } from './enc/encLayer';
import { coastline } from './coastline/coastlineLayer';
import { grid } from './grid/gridLayer';
import { station } from './station/stationLayer';
import { sic } from './sic/sicLayer';
import { sicUncertainty } from './sicUncertainty/sicUncertaintyLayer';
import { icebergDrift } from './icebergDrift/icebergDriftLayer';
import { iceberg } from './iceberg/icebergLayer';
import { routeAlt } from './routeAlt/routeAltLayer';
import { route } from './route/routeLayer';
import { alarmZone } from './alarmZone/alarmZoneLayer';
import { ais } from './ais/aisLayer';
import { ownShip } from './ownShip/ownShipLayer';

/**
 * All AURORA layers, bottom of the stack first.
 *
 * Every entry is created eagerly and subscribes lazily: a layer that has no
 * data simply contributes nothing until its store fills, so the map is fully
 * populated from the first render without any coordination in `MapView`.
 */
export const LAYERS: readonly AuroraLayer[] = [
  // base — the chart itself
  encLayer,
  coastline,

  // reference
  grid,
  station,

  // ice
  sic,
  sicUncertainty,
  icebergDrift,
  iceberg,

  // route
  routeAlt,
  route,
  alarmZone,

  // traffic
  ais,
  ownShip,
];

const BY_ID = new Map<string, AuroraLayer>(LAYERS.map((layer) => [layer.id, layer]));

export function layerById(id: string): AuroraLayer | undefined {
  return BY_ID.get(id);
}

/**
 * Layers grouped by category, in `CATEGORY_ORDER`, preserving array order
 * inside each group. Categories with no layers are omitted rather than shown
 * empty — the `weather` category is defined by the contract but currently has
 * no raster behind it.
 */
export function layersByCategory(): Array<{ category: LayerCategory; layers: AuroraLayer[] }> {
  return CATEGORY_ORDER.map((category) => ({
    category,
    layers: LAYERS.filter((layer) => layer.category === category),
  })).filter((group) => group.layers.length > 0);
}

/**
 * Visibility of a layer, resolving "never touched" to the layer's own default.
 *
 * `uiStore.layerVisibility` starts as an empty record on purpose, so that a
 * layer added later starts at its documented default instead of at `false`.
 */
export function isLayerVisible(id: string, ui: UiStoreState): boolean {
  const stored = ui.layerVisibility[id];
  if (stored !== undefined) return stored;
  return layerById(id)?.defaultVisible ?? false;
}

/** Effective opacity of a layer, resolving "never touched" to its default. */
export function layerOpacity(id: string, ui: UiStoreState): number {
  const stored = ui.layerOpacity[id];
  if (stored !== undefined) return stored;
  return layerById(id)?.defaultOpacity ?? 1;
}
