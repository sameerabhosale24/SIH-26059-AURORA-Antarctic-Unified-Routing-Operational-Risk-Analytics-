/**
 * Alternative-route geometry.
 *
 * Reads the same `routeStore` snapshot as the primary layer, so the two layers
 * always describe one run. Any route the run does not flag as recommended is
 * drawn here, including every route when the run flagged none at all — the
 * operator then sees candidates and an explicit empty primary layer, rather
 * than a blank map.
 *
 * Waypoints are deliberately not drawn for alternatives: a waypoint is a
 * navigation instruction for *one* track, and overlapping three sets of them
 * would make each unreadable.
 */
import Feature from 'ol/Feature';
import LineString from 'ol/geom/LineString';

import { useRouteStore, type RouteStore } from '@/stores/routeStore';
import {
  createGeoSource,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';
import { ROUTE_PROPS, alternativeRoutes } from '../route/routeSource';

/** Alternative-route features, or `null` when the run produced only one. */
export function alternativeRouteFeatures(state: RouteStore): GeoFeature[] | null {
  const routes = alternativeRoutes(state);
  if (routes.length === 0) return null;

  const features: GeoFeature[] = routes.map((route) => {
    const feature = new Feature({ geometry: new LineString(route.geometry.coordinates) });
    feature.set(ROUTE_PROPS.KIND, 'line');
    feature.set(ROUTE_PROPS.RECOMMENDED, route.is_recommended);
    feature.set(ROUTE_PROPS.ETA, route.eta);
    feature.set('label', route.label);
    feature.setId(`route:${route.id}:line`);
    return feature;
  });

  return features;
}

export function createAlternativeSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncAlternativeSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useRouteStore };
