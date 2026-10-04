/**
 * Station hover and selection on the map.
 *
 * Two behaviours, one hit-test:
 *
 *  - **hover** shows a compact overlay 12 px to the right of the marker with
 *    the name, the country and the position to three decimals;
 *  - **click** pins the station into `uiStore.selectedStation`, which is what
 *    `StationInfoPanel` renders. Clicking anywhere else on the map unpins it,
 *    so the panel never outlives the operator's attention.
 *
 * The overlay is an `ol/Overlay` rather than a React portal so it tracks the
 * marker exactly through pans, zooms and projection changes without a re-render.
 */
import type { EventsKey } from 'ol/events';
import { unByKey } from 'ol/Observable';
import type MapBrowserEvent from 'ol/MapBrowserEvent';
import Overlay from 'ol/Overlay';
import type Map from 'ol/Map';
import type { Pixel } from 'ol/pixel';

import { mergeStations } from '@/map/layers/station/stationSource';
import { useStationsStore } from '@/stores/stationsStore';
import { useUiStore } from '@/stores/uiStore';
import type { Station } from '@/types/common';

/** Pixel tolerance around a marker, so a hover does not need pixel accuracy. */
const HIT_TOLERANCE = 6;

/**
 * The station whose marker sits under `pixel`, or null.
 *
 * Deliberately not `map.forEachFeatureAtPixel`: OpenLayers filters hit-test
 * candidates through the same corner-only user extent the renderer culls with
 * (see `UnculledVectorSource` in `layers/shared.ts`), which drops every
 * station south of ~63°S. Screen-space distance uses OL's own transform for
 * the marker pixel, so it stays exact — and available — for all of them.
 */
function stationAt(map: Map, pixel: Pixel): Station | null {
  const [cursorX, cursorY] = pixel;
  if (cursorX === undefined || cursorY === undefined) return null;

  const stations = mergeStations(useStationsStore.getState().data);
  const toleranceSquared = HIT_TOLERANCE * HIT_TOLERANCE;

  let hit: Station | null = null;
  let nearest = Number.POSITIVE_INFINITY;

  for (const station of stations) {
    const [markerX, markerY] = map.getPixelFromCoordinate([station.lon, station.lat]) ?? [];
    if (markerX === undefined || markerY === undefined) continue;

    const dx = markerX - cursorX;
    const dy = markerY - cursorY;
    const distanceSquared = dx * dx + dy * dy;

    if (distanceSquared > toleranceSquared || distanceSquared >= nearest) continue;

    nearest = distanceSquared;
    hit = station;
  }

  return hit;
}

/** Build the overlay's content: name, country, coordinates to 3 decimals. */
function renderTooltip(element: HTMLElement, station: Station): void {
  const name = document.createElement('p');
  name.className = 'font-semibold leading-tight text-ocean-100';
  name.textContent = station.name;

  const country = document.createElement('p');
  country.className = 'text-[11px] leading-tight text-ocean-300';
  country.textContent = station.country;

  const position = document.createElement('p');
  position.className = 'mt-1 font-mono text-[10px] leading-tight text-ocean-200';
  position.textContent = `${station.lat.toFixed(3)}, ${station.lon.toFixed(3)}`;

  element.replaceChildren(name, country, position);
}

/**
 * Wire hover and click for station markers on `map`.
 *
 * @returns the teardown. MapView runs it when the map unmounts.
 */
export function setupStationInteraction(map: Map): () => void {
  const element = document.createElement('div');
  element.className =
    'pointer-events-none rounded border border-ocean-700 bg-ocean-900 p-2 shadow-lg shadow-black/40';

  const overlay = new Overlay({
    element,
    // 12 px to the right of the marker, vertically centred on it.
    offset: [12, 0],
    positioning: 'center-left',
    stopEvent: false,
  });

  map.addOverlay(overlay);

  const setCursor = (cursor: string): void => {
    const target = map.getTargetElement();
    if (target) target.style.cursor = cursor;
  };

  const hideTooltip = (): void => {
    overlay.setPosition(undefined);
    setCursor('');
  };

  const onPointerMove = (event: MapBrowserEvent<UIEvent>): void => {
    // A drag is a pan, not a hover: the marker under the cursor is not what
    // the operator is pointing at.
    if (event.dragging) {
      hideTooltip();
      return;
    }

    const station = stationAt(map, event.pixel);

    if (!station) {
      hideTooltip();
      return;
    }

    renderTooltip(element, station);
    overlay.setPosition([station.lon, station.lat]);
    setCursor('pointer');
  };

  const onClick = (event: MapBrowserEvent<UIEvent>): void => {
    const station = stationAt(map, event.pixel);
    useUiStore.getState().setSelectedStation(station);
  };

  const onPointerLeave = (): void => hideTooltip();

  const moveKey: EventsKey = map.on('pointermove', onPointerMove);
  const clickKey: EventsKey = map.on('singleclick', onClick);
  map.getViewport().addEventListener('pointerleave', onPointerLeave);

  return () => {
    unByKey([moveKey, clickKey]);
    map.getViewport().removeEventListener('pointerleave', onPointerLeave);
    map.removeOverlay(overlay);
    hideTooltip();
    element.remove();
    useUiStore.getState().setSelectedStation(null);
  };
}
