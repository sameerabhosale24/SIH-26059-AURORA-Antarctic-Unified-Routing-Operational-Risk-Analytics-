/**
 * Alarm portrayal.
 *
 * Severity drives colour (`critical | warning | caution`) and the zone's fill
 * opacity is fixed by `ALARM_ZONE_OPACITY` so a wide area never masks the
 * chart beneath it. The zone outline stays fully opaque: the boundary is the
 * part that matters operationally.
 *
 * The label shows the alarm type rather than its message. Messages are full
 * sentences sized for the alarm panel; on the map they would collide with the
 * symbology they are describing.
 */
import CircleStyle from 'ol/style/Circle';
import { Fill, Style, Stroke, Text } from 'ol/style';
import type { FeatureLike } from 'ol/Feature';
import type { StyleFunction } from 'ol/style/Style';

import { ALARM_ZONE_OPACITY, MARKER_SIZES, ZOOM_THRESHOLDS } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { withAlpha } from '../shared';
import { ALARM_PROPS, type AlarmFeatureKind } from './alarmZoneSource';

type Severity = 'critical' | 'warning' | 'caution';

const SEVERITIES: readonly Severity[] = ['critical', 'warning', 'caution'];

function severityOf(feature: FeatureLike): Severity {
  const value = feature.get(ALARM_PROPS.SEVERITY);
  return typeof value === 'string' && (SEVERITIES as readonly string[]).includes(value)
    ? (value as Severity)
    : 'caution';
}

function kindOf(feature: FeatureLike): AlarmFeatureKind | null {
  const value = feature.get(ALARM_PROPS.KIND);
  return value === 'marker' || value === 'zone' ? value : null;
}

export function getAlarmZoneStyle(palette: Palette): StyleFunction {
  const zones = new Map<Severity, Style>();
  const markers = new Map<Severity, Style>();

  for (const severity of SEVERITIES) {
    const color = palette.alarm[severity];

    zones.set(
      severity,
      new Style({
        fill: new Fill({ color: withAlpha(color, ALARM_ZONE_OPACITY) }),
        stroke: new Stroke({ color, width: 2 }),
        zIndex: 1,
      }),
    );

    markers.set(
      severity,
      new Style({
        image: new CircleStyle({
          radius: MARKER_SIZES.alarmZone,
          fill: new Fill({ color }),
          stroke: new Stroke({ color: palette.textHalo, width: 2 }),
        }),
        zIndex: 2,
      }),
    );
  }

  const label = new Style({
    text: new Text({
      font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
      text: '',
      fill: new Fill({ color: palette.text }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      offsetY: -MARKER_SIZES.alarmZone - 6,
      overflow: true,
    }),
    zIndex: 3,
  });

  return (feature, resolution) => {
    const severity = severityOf(feature);
    const kind = kindOf(feature);

    if (kind === 'zone') return zones.get(severity);
    if (kind !== 'marker') return undefined;

    const marker = markers.get(severity);
    if (!marker) return undefined;
    if (resolution > ZOOM_THRESHOLDS.AIS_LABEL) return marker;

    const type = feature.get(ALARM_PROPS.TYPE);
    if (typeof type !== 'string' || type === '') return marker;

    const text = label.getText();
    if (!text) return marker;

    text.setText(`${severity.toUpperCase()} · ${type.toUpperCase()}`);
    return [marker, label];
  };
}
