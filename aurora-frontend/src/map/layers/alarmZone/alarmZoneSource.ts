/**
 * Alarm geometry.
 *
 * Two kinds of feature share this layer, distinguished by `ALARM_PROPS.KIND`:
 *
 *  - **markers** for every alarm that carries a position, so an event can be
 *    located even when it is no longer on screen in the alarm list;
 *  - **zones** for alarms whose backend payload includes an area, read from
 *    `payload.zone` or `payload.geometry` as a GeoJSON polygon.
 *
 * The zone is optional and read defensively: an alarm that describes a
 * condition over an area the backend did not send simply draws its marker. No
 * area is ever inferred from the alarm's point.
 *
 * Alarms are event-driven rather than polled, so this layer has no staleness
 * key — an alarm does not "go stale", it is acknowledged or superseded.
 */
import Feature from 'ol/Feature';
import Polygon from 'ol/geom/Polygon';
import type { Polygon as GeoJsonPolygon } from 'geojson';

import type { Alarm } from '@/types/alarm';
import { useAlarmStore, type AlarmStore } from '@/stores/alarmStore';
import {
  createGeoSource,
  pointFeature,
  replaceFeatures,
  type GeoFeature,
  type GeoVectorSource,
} from '../shared';

/** Feature property keys, read by `alarmZoneStyle`. */
export const ALARM_PROPS = {
  KIND: 'kind',
  SEVERITY: 'severity',
  TYPE: 'type',
  MESSAGE: 'message',
} as const;

export type AlarmFeatureKind = 'marker' | 'zone';

function isGeoJsonPolygon(value: unknown): value is GeoJsonPolygon {
  if (value === null || typeof value !== 'object') return false;
  const candidate = value as { type?: unknown; coordinates?: unknown };
  return candidate.type === 'Polygon' && Array.isArray(candidate.coordinates);
}

/** The alarm's area, when the backend described one. */
function zoneGeometry(alarm: Alarm): Polygon | null {
  const payload = alarm.payload;
  const candidate =
    payload && typeof payload === 'object' ? (payload.zone ?? payload.geometry) : undefined;

  if (!isGeoJsonPolygon(candidate)) return null;
  if (candidate.coordinates.length === 0) return null;

  return new Polygon(candidate.coordinates);
}

function markerFeature(alarm: Alarm): GeoFeature | null {
  if (alarm.lat === null || alarm.lon === null) return null;
  if (!Number.isFinite(alarm.lat) || !Number.isFinite(alarm.lon)) return null;

  const feature = pointFeature(alarm.lon, alarm.lat, {
    [ALARM_PROPS.KIND]: 'marker' satisfies AlarmFeatureKind,
    [ALARM_PROPS.SEVERITY]: alarm.severity,
    [ALARM_PROPS.TYPE]: alarm.type,
    [ALARM_PROPS.MESSAGE]: alarm.message,
  });
  feature.setId(`alarm:${alarm.id}`);
  return feature;
}

function zoneFeature(alarm: Alarm): GeoFeature | null {
  const geometry = zoneGeometry(alarm);
  if (!geometry) return null;

  const feature = new Feature({ geometry });
  feature.set(ALARM_PROPS.KIND, 'zone' satisfies AlarmFeatureKind);
  feature.set(ALARM_PROPS.SEVERITY, alarm.severity);
  feature.set(ALARM_PROPS.TYPE, alarm.type);
  feature.set(ALARM_PROPS.MESSAGE, alarm.message);
  feature.setId(`alarm:${alarm.id}:zone`);
  return feature;
}

/**
 * Alarm features, or `null` when nothing is positioned.
 *
 * Zones are emitted before markers so that, on a `zIndex` tie, the marker —
 * the thing to click — wins.
 */
export function alarmFeatures(state: AlarmStore): GeoFeature[] | null {
  const alarms = state.data;
  if (!alarms || alarms.length === 0) return null;

  const features: GeoFeature[] = [];
  for (const alarm of alarms) {
    const zone = zoneFeature(alarm);
    if (zone) features.push(zone);

    const marker = markerFeature(alarm);
    if (marker) features.push(marker);
  }

  return features.length > 0 ? features : null;
}

export function createAlarmSource(features: GeoFeature[]): GeoVectorSource {
  const source = createGeoSource();
  replaceFeatures(source, features);
  return source;
}

export function syncAlarmSource(source: GeoVectorSource, features: GeoFeature[]): void {
  replaceFeatures(source, features);
}

export { useAlarmStore };
