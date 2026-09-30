/**
 * Route portrayal.
 *
 * The recommended route is a solid, wide line in the route colour; its
 * waypoints are marked underneath it so a marker never hides the line it sits
 * on. Waypoint names and ETAs appear only once the view is detailed enough
 * for them to be readable, and a waypoint without a name falls back to its
 * sequence number rather than disappearing.
 */
import CircleStyle from 'ol/style/Circle';
import LineString from 'ol/geom/LineString';
import type { FeatureLike } from 'ol/Feature';
import { Fill, Style, Stroke, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import {
  MARKER_SIZES,
  ROUTE_TRANSITION_MS,
  ROUTE_WIDTH,
  ZOOM_THRESHOLDS,
} from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { ROUTE_PROPS, type RouteFeatureKind } from './routeSource';

/**
 * End of the current reveal animation, as a `performance.now()` deadline.
 *
 * `0` means "no transition running", which is the steady state — the style
 * function only has to do work while this is in the future.
 */
let transitionEnd = 0;

/**
 * Serial number of the running transition.
 *
 * The route layer can be rebuilt while a reveal is still in flight; without a
 * token the old loop's disposer would blank the *new* transition's deadline as
 * it unwound, and the new line would snap to fully drawn.
 */
let transitionToken = 0;

/**
 * Start the 500 ms route reveal and keep `layer` repainting until it finishes.
 *
 * OpenLayers only re-runs style functions when something it tracks changes
 * (pan, zoom, feature edit) — the passage of time is not one of them — so the
 * loop drives `layer.changed()` itself and stops at the deadline. The returned
 * function cancels it, which matters because the route layer can be torn down
 * mid-transition.
 *
 * @returns a disposer that stops the repaint loop.
 */
export function startRouteTransition(layer: { changed(): void }): () => void {
  const token = (transitionToken += 1);
  transitionEnd = performance.now() + ROUTE_TRANSITION_MS;

  let frame = 0;

  const tick = (): void => {
    layer.changed();
    if (performance.now() < transitionEnd) frame = requestAnimationFrame(tick);
  };

  frame = requestAnimationFrame(tick);

  return () => {
    cancelAnimationFrame(frame);
    if (transitionToken === token) transitionEnd = 0;
  };
}

/** Whether a reveal is currently in progress. */
function isTransitioning(): boolean {
  return transitionEnd > performance.now();
}

/**
 * The first `progress` fraction of a line, as a new geometry.
 *
 * Cut at a vertex rather than interpolated along a segment, so during the
 * reveal the line still passes through exactly the waypoints the optimiser
 * produced — an interpolated endpoint would briefly sit off-route.
 */
function partialLine(feature: FeatureLike, progress: number): LineString | null {
  const geometry = feature.getGeometry?.();

  if (!(geometry instanceof LineString)) return null;

  const coords = geometry.getCoordinates();
  if (coords.length < 2) return null;

  const segments: number[] = [];
  let total = 0;

  for (let i = 1; i < coords.length; i += 1) {
    const dx = (coords[i]?.[0] ?? 0) - (coords[i - 1]?.[0] ?? 0);
    const dy = (coords[i]?.[1] ?? 0) - (coords[i - 1]?.[1] ?? 0);
    const length = Math.hypot(dx, dy);
    segments.push(length);
    total += length;
  }

  if (total === 0) return null;

  const target = total * progress;
  const kept: number[][] = [coords[0] as number[]];
  let travelled = 0;

  for (let i = 0; i < segments.length; i += 1) {
    const length = segments[i] ?? 0;
    const next = travelled + length;
    const vertex = coords[i + 1] as number[];

    if (next <= target) {
      kept.push(vertex);
    } else {
      const fraction = length === 0 ? 0 : (target - travelled) / length;
      const from = coords[i];
      const to = coords[i + 1];
      if (!from || !to) break;

      const fromX = from[0] ?? 0;
      const fromY = from[1] ?? 0;
      const toX = to[0] ?? 0;
      const toY = to[1] ?? 0;

      kept.push([fromX + (toX - fromX) * fraction, fromY + (toY - fromY) * fraction]);
      break;
    }

    travelled = next;
    if (travelled >= target) break;
  }

  if (kept.length < 2) return null;
  return new LineString(kept);
}

function readKind(feature: { get(key: string): unknown }): RouteFeatureKind | null {
  const value = feature.get(ROUTE_PROPS.KIND);
  return value === 'line' || value === 'waypoint' ? value : null;
}

/** Waypoint caption: name when present, else `WP <seq>`, plus ETA if known. */
function caption(feature: { get(key: string): unknown }): string | null {
  const name = feature.get(ROUTE_PROPS.LABEL);
  const seq = feature.get('seq');

  let label: string | null = null;
  if (typeof name === 'string' && name.trim() !== '') label = name.trim();
  else if (typeof seq === 'number' && Number.isFinite(seq)) label = `WP ${seq}`;

  if (label === null) return null;

  const eta = feature.get(ROUTE_PROPS.ETA);
  return typeof eta === 'string' && eta !== '' ? `${label}  ${formatEta(eta)}` : label;
}

/** Render an ISO timestamp as `HH:MM` UTC — an ETA is read, not parsed. */
function formatEta(iso: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return iso;

  const date = new Date(ms);
  const hh = String(date.getUTCHours()).padStart(2, '0');
  const mm = String(date.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm}Z`;
}

export function getRouteStyle(palette: Palette): StyleFunction {
  const line = new Style({
    stroke: new Stroke({
      color: palette.route,
      width: ROUTE_WIDTH.primary,
      lineJoin: 'round',
      lineCap: 'round',
    }),
    zIndex: 4,
  });

  const waypoint = new Style({
    image: new CircleStyle({
      radius: MARKER_SIZES.waypoint,
      fill: new Fill({ color: palette.route }),
      stroke: new Stroke({ color: palette.textHalo, width: 2 }),
    }),
    zIndex: 5,
  });

  const label = new Style({
    text: new Text({
      font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
      text: '',
      fill: new Fill({ color: palette.route }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      offsetY: -MARKER_SIZES.waypoint - 5,
      overflow: true,
    }),
    zIndex: 6,
  });

  return (feature, resolution) => {
    const kind = readKind(feature);

    if (kind === 'line') {
      if (!isTransitioning()) return line;

      const elapsed = performance.now() - (transitionEnd - ROUTE_TRANSITION_MS);
      const progress = Math.min(1, Math.max(0, elapsed / ROUTE_TRANSITION_MS));
      const partial = partialLine(feature as FeatureLike, progress);

      // Nothing to reveal yet (or a geometry we cannot cut): draw it whole
      // rather than blanking the route for the length of the animation.
      if (partial === null) return line;

      return new Style({
        stroke: line.getStroke() ?? undefined,
        geometry: partial,
        zIndex: 4,
      });
    }

    if (kind !== 'waypoint') return undefined;

    if (resolution > ZOOM_THRESHOLDS.WAYPOINT_LABEL) return waypoint;

    const text = caption(feature);
    if (text === null) return waypoint;

    const textSymbol = label.getText();
    if (!textSymbol) return waypoint;

    textSymbol.setText(text);
    return [waypoint, label];
  };
}
