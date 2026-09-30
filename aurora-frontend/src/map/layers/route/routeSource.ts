/**
 * Route geometry.
 *
 * The primary layer draws the AI-recommended route; the alternative layer
 * draws everything else. Both read the same `routeStore` snapshot so the two
 * can never disagree about which run they are showing.
 *
 * `is_recommended` is the backend's own flag and is never re-derived from
 * `risk_score` or `fuel_estimate_t`. The single documented exception: when the
 * run contains exactly one route the flag cannot be used to distinguish
 * anything, so that route is treated as the recommendation rather than
 * leaving the primary layer blank.
 */
import Feature from 'ol/Feature';
import LineString from 'ol/geom/LineString';

import { useRouteStore, type RouteStore } from '@/stores/routeStore';
import type { Route } from '@/types/route';
import {
  createGeoSource,
  pointFeature,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';

/** Feature property keys, read by `routeStyle`. */
export const ROUTE_PROPS = {
  KIND: 'kind',
  LABEL: 'label',
  ETA: 'eta',
  RECOMMENDED: 'recommended',
} as const;

export type RouteFeatureKind = 'line' | 'waypoint';

/** The route this run puts forward, or `null` when it put forward none. */
export function recommendedRoute(state: RouteStore): Route | null {
  const run = state.data;
  if (!run || run.routes.length === 0) return null;

  const flagged = run.routes.find((route) => route.is_recommended);
  if (flagged) return flagged;

  const only = run.routes[0];
  return run.routes.length === 1 && only ? only : null;
}

/** Routes this run does *not* put forward. */
export function alternativeRoutes(state: RouteStore): Route[] {
  const run = state.data;
  if (!run) return [];

  const recommended = recommendedRoute(state);
  return run.routes.filter((route) => route !== recommended);
}

function lineFeature(route: Route): GeoFeature {
  const feature = new Feature({ geometry: new LineString(route.geometry.coordinates) });
  feature.set(ROUTE_PROPS.KIND, 'line' satisfies RouteFeatureKind);
  feature.set(ROUTE_PROPS.RECOMMENDED, route.is_recommended);
  feature.set(ROUTE_PROPS.ETA, route.eta);
  feature.setId(`route:${route.id}:line`);
  return feature;
}

function waypointFeatures(route: Route): GeoFeature[] {
  return route.waypoints.map((waypoint) => {
    const feature = pointFeature(
      waypoint.lon,
      waypoint.lat,
      {
        [ROUTE_PROPS.KIND]: 'waypoint' satisfies RouteFeatureKind,
        [ROUTE_PROPS.LABEL]: waypoint.name,
        [ROUTE_PROPS.ETA]: waypoint.eta,
        seq: waypoint.seq,
      },
      `route:${route.id}:wp:${waypoint.id}`,
    );
    return feature;
  });
}

/** Primary route line plus its waypoint markers, or `null` when absent. */
export function primaryRouteFeatures(state: RouteStore): GeoFeature[] | null {
  const route = recommendedRoute(state);
  if (!route) return null;

  const features: GeoFeature[] = [lineFeature(route), ...waypointFeatures(route)];
  return features.length > 0 ? features : null;
}

/** One line feature per alternative route, or `null` when there are none. */
export function alternativeRouteFeatures(state: RouteStore): GeoFeature[] | null {
  const routes = alternativeRoutes(state);
  if (routes.length === 0) return null;

  const features = routes.map(lineFeature);
  return features.length > 0 ? features : null;
}

export function createRouteSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncRouteSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useRouteStore };
