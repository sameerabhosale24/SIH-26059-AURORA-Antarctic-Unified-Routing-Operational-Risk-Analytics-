/**
 * OpenLayers map construction and lifetime.
 *
 * The view uses the AURORA Lambert Conformal Conic projection (`EPSG:9802`) —
 * never Web Mercator. `createMap` builds a bare shell: a view, the standard
 * controls, and one empty `aurora-layers` group that Part 2 fills. There is no
 * base layer, no tile source and no data here; nothing is invented.
 *
 * ## Coordinates
 *
 * Because WGS84 is the user projection, **every public `ol/View` method takes
 * and returns lon/lat**: `setCenter`, `animate`, `fit` and `calculateExtent`
 * all run their argument through `fromUserCoordinate`/`fromUserExtent`
 * (`ol/View.js`). Passing LCC metres to any of them would be transformed a
 * second time. Only the resolution stays in view-projection units, because a
 * scale is not a coordinate.
 *
 * The `*Internal` variants are the view-projection ones; nothing here uses
 * them, so the convention holds across the whole app: *hand OpenLayers
 * lon/lat*.
 */
import 'ol/ol.css';

import Map from 'ol/Map';
import View from 'ol/View';
import LayerGroup from 'ol/layer/Group';
import { Attribution, MousePosition, ScaleLine, Zoom } from 'ol/control';
import { createStringXY } from 'ol/coordinate';

import { FOLLOW_SHIP } from '@/config/constants';
import { getPalette } from '@/config/palettes';
import {
  LCC_CODE,
  POLAR_CODE,
  lccProjection,
  polarProjection,
  registerLccProjection,
  WGS84_CODE,
} from '@/config/projection';
import type { Roi } from '@/types/common';
import type { UiProjection } from '@/stores/uiStore';

/** Property key marking the managed layer group. */
export const LAYER_GROUP_KEY = 'aurora-layers';

/**
 * The Cape Town → Antarctic coast corridor, `[lon_min, lat_min, lon_max, lat_max]`.
 *
 * This — not the SIC ROI — is what the map opens framed on: an operator has to
 * see the whole voyage, port of departure included, before anything else on the
 * chart means anything. The SIC ROI stays an internal detail of the map (it
 * frames the raster and the coverage rectangle) and never drives the view.
 */
export const CORRIDOR_BOUNDS: [number, number, number, number] = [10, -78, 85, -30];

/** Centre the corridor view is declared at, before `fit` resolves the scale. */
export const CORRIDOR_CENTER: [number, number] = [40, -54];

/** Padding, in px, applied when fitting an extent into the viewport. */
const FIT_PADDING: [number, number, number, number] = [24, 24, 24, 24];

/** Fallback viewport size used if the container has not been laid out yet. */
const FALLBACK_SIZE: [number, number] = [1024, 768];

/** Metres in a nautical mile. */
const METRES_PER_NM = 1852;

const layerGroups = new WeakMap<Map, LayerGroup>();
const rois = new WeakMap<Map, Roi>();
let singleton: Map | null = null;
let lastFollowAt = 0;

function viewportSize(map: Map): [number, number] {
  const size = map.getSize() ?? FALLBACK_SIZE;
  return [Math.max(size[0] || FALLBACK_SIZE[0], 1), Math.max(size[1] || FALLBACK_SIZE[1], 1)];
}

/** The WGS84 bounding box of a ROI — what `View.fit` expects. */
function roiBox(roi: Roi): [number, number, number, number] {
  return [roi.lon_min, roi.lat_min, roi.lon_max, roi.lat_max];
}

/**
 * Build the AURORA map shell into `target`, framed on the Cape Town corridor.
 *
 * The projection is registered as a side effect, so callers do not need to
 * remember to do it. The supplied ROI is kept with the map (it is what the SIC
 * raster and its coverage rectangle are framed on) but does not set the view.
 */
export function createMap(target: HTMLElement, roi: Roi): Map {
  registerLccProjection();

  const map = new Map({
    target,
    layers: [],
    controls: [
      new Zoom(),
      new ScaleLine({ units: 'metric' }),
      // With a user projection declared, the control renders the user
      // projection's coordinates and ignores the `projection` option — the
      // option is kept so the readout still means lon/lat if the user
      // projection is ever removed.
      new MousePosition({
        projection: WGS84_CODE,
        coordinateFormat: createStringXY(6),
      }),
      new Attribution({ collapsible: true, collapsed: true }),
    ],
    // `center` is lon/lat: the constructor converts it via `fromUserCoordinate`.
    view: new View({
      projection: lccProjection(),
      center: CORRIDOR_CENTER,
      resolution: 100_000,
      constrainResolution: false,
      showFullExtent: true,
    }),
  });

  // Frame the corridor — Cape Town at the top, the Antarctic coast at the
  // bottom. OpenLayers 9 does the fit arithmetic inside `View.fit`
  // (`ol/extent.fit` was removed from the public API) and it needs a real
  // pixel size, which only exists once the container is laid out.
  try {
    map.getView().fit(CORRIDOR_BOUNDS, { size: viewportSize(map), padding: FIT_PADDING });
  } catch (cause) {
    console.warn('[aurora] could not fit the corridor to the viewport; using declared centre/resolution', cause);
  }

  const layers = new LayerGroup({ layers: [] });
  layers.set(LAYER_GROUP_KEY, true);
  map.addLayer(layers);
  layerGroups.set(map, layers);

  // The chart background is not a layer — it is the colour of empty canvas,
  // so it has to be set on the viewport or an un-layered map shows the
  // container's colour instead of the palette's.
  setMapBackground(map, getPalette().background);
  rois.set(map, roi);

  singleton = map;

  return map;
}

/**
 * Switch the map between the corridor, local and polar presets.
 *
 * Only the *polar* preset changes the view projection; `corridor` and `local`
 * both render in LCC and differ purely in framing, so neither rebuilds the
 * view unless the projection actually changes. Swapping the projection does
 * require a new `View` — `ol/View` has no `setProjection`.
 *
 * @param vesselPos `[lon, lat]` in WGS84; required to frame `local`.
 */
export function applyProjectionPreset(
  map: Map,
  preset: UiProjection,
  vesselPos: [number, number] | null,
): void {
  registerLccProjection();

  const code = preset === 'polar' ? POLAR_CODE : LCC_CODE;
  const roi = rois.get(map);

  let view = map.getView();

  if (view.getProjection().getCode() !== code) {
    // The previous view's centre is returned in lon/lat, and the new View
    // accepts lon/lat, so the hand-over needs no transform of our own.
    const previousCentre = view.getCenter();

    view = new View({
      projection: code === POLAR_CODE ? polarProjection() : lccProjection(),
      center: previousCentre ?? [0, 0],
      resolution: view.getResolution() ?? 100_000,
      constrainResolution: false,
      showFullExtent: true,
    });

    map.setView(view);
  }

  const size = viewportSize(map);

  if (preset === 'local' && vesselPos) {
    // Framing a fixed radius around the ship. Resolution *is* in view-projection
    // units, so the radius is converted to metres here rather than passed
    // through the user projection.
    const radiusMetres = FOLLOW_SHIP.LOCAL_RADIUS_NM * METRES_PER_NM;
    const halfShortSide = Math.min(size[0], size[1]) / 2;

    view.setCenter(vesselPos);
    if (halfShortSide > 0) view.setResolution(radiusMetres / halfShortSide);
    return;
  }

  // `corridor` frames the whole Cape Town → station corridor, the view the
  // console opens on. `polar` frames the SIC region instead, which is what the
  // polar view exists to inspect.
  const box = preset === 'corridor' || !roi ? CORRIDOR_BOUNDS : roiBox(roi);

  try {
    view.fit(box, { size, padding: FIT_PADDING });
  } catch (cause) {
    console.warn('[aurora] could not frame preset', preset, cause);
  }
}

/**
 * Paint the map's empty canvas with a palette colour.
 *
 * OpenLayers has no "background" option on `Map` — an area with no layer
 * beneath it is simply transparent — so the colour lives on the viewport
 * element. Called once at construction, which is what gives a chart with no
 * ENC loaded yet the ocean colour rather than the container's.
 */
export function setMapBackground(map: Map, color: string): void {
  map.getViewport().style.backgroundColor = color;
}

/**
 * The managed layer group for a map.
 * @throws if the map was not built by {@link createMap}.
 */
export function getLayerGroup(map: Map): LayerGroup {
  const group = layerGroups.get(map);

  if (!group) {
    throw new Error('Map was not created by createMap(); no aurora-layers group is attached.');
  }

  return group;
}

/** The most recently created map, or null before the map has mounted. */
export function getMap(): Map | null {
  return singleton;
}

/**
 * The ROI this map was built with — the SIC region, in WGS84 degrees.
 *
 * Kept as an internal detail of the map rather than a view input: the SIC
 * raster, its coverage rectangle and the `polar` preset all frame on it, and
 * nothing else does.
 *
 * @returns null when the map was not built by {@link createMap}.
 */
export function getMapRoi(map: Map): Roi | null {
  return rois.get(map) ?? null;
}

/** Forget the singleton. Call after disposing the map. */
export function clearMap(): void {
  singleton = null;
}

/**
 * Re-centre on the own ship while follow-mode is enabled.
 *
 * `vesselPos` is `[lon, lat]` in WGS84. Calls arriving inside
 * `FOLLOW_SHIP.MIN_INTERVAL_MS` of the previous one are ignored so a 1 Hz GPS
 * stream cannot queue animations faster than they can be drawn.
 */
export function setFollowShip(
  map: Map,
  vesselPos: [number, number] | null,
  enabled: boolean,
): void {
  if (!enabled || vesselPos === null) return;

  const now = Date.now();
  if (now - lastFollowAt < FOLLOW_SHIP.MIN_INTERVAL_MS) return;
  lastFollowAt = now;

  // `animate` converts its centre from the user projection, so this is lon/lat.
  map.getView().animate({
    center: vesselPos,
    duration: FOLLOW_SHIP.ANIMATION_MS,
  });
}
