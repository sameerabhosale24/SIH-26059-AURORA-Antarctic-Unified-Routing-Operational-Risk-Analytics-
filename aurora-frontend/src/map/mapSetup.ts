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
 * Build the AURORA map shell into `target`, framed on the supplied ROI.
 *
 * The projection is registered as a side effect, so callers do not need to
 * remember to do it.
 */
export function createMap(target: HTMLElement, roi: Roi): Map {
  registerLccProjection();

  const centre: [number, number] = [
    (roi.lon_min + roi.lon_max) / 2,
    (roi.lat_min + roi.lat_max) / 2,
  ];

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
      center: centre,
      resolution: 100_000,
      constrainResolution: false,
      showFullExtent: true,
    }),
  });

  // Frame the ROI. OpenLayers 9 does the fit arithmetic inside `View.fit`
  // (`ol/extent.fit` was removed from the public API) and it needs a real
  // pixel size, which only exists once the container is laid out.
  try {
    map.getView().fit(roiBox(roi), { size: viewportSize(map), padding: FIT_PADDING });
  } catch (cause) {
    console.warn('[aurora] could not fit ROI to viewport; using declared centre/resolution', cause);
  }

  const layers = new LayerGroup({ layers: [] });
  layers.set(LAYER_GROUP_KEY, true);
  map.addLayer(layers);
  layerGroups.set(map, layers);

  // The chart background is not a layer — it is the colour of empty canvas,
  // so it has to be set on the viewport or an un-layered map shows the
  // container's colour instead of the palette's.
  setMapBackground(map, getPalette('day').background);
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

  if (roi) {
    try {
      view.fit(roiBox(roi), { size, padding: FIT_PADDING });
    } catch (cause) {
      console.warn('[aurora] could not frame preset', preset, cause);
    }
  }
}

/**
 * Paint the map's empty canvas with a palette colour.
 *
 * OpenLayers has no "background" option on `Map` — an area with no layer
 * beneath it is simply transparent — so the colour lives on the viewport
 * element. Called once at construction and again whenever the display mode
 * changes, which is what makes Day/Dusk/Night visibly different on a chart
 * that has no ENC loaded yet.
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
