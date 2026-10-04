/**
 * Alarm layer — positioned alarms and their area, when the backend sent one.
 */
import VectorLayer from 'ol/layer/Vector';

import { getPalette } from '@/config/palettes';
import { useAlarmStore, type AlarmStore } from '@/stores/alarmStore';
import type { GeoFeature } from '../shared';
import type { AuroraLayer, AuroraOlLayer } from '../types';
import { alarmFeatures, createAlarmSource, syncAlarmSource } from './alarmZoneSource';
import { getAlarmZoneStyle } from './alarmZoneStyle';

type AlarmLayer = VectorLayer<GeoFeature>;

function isAlarmLayer(layer: AuroraOlLayer | null): layer is AlarmLayer {
  return layer instanceof VectorLayer;
}

function build(state: AlarmStore): AlarmLayer | null {
  const features = alarmFeatures(state);
  if (!features) return null;

  return new VectorLayer<GeoFeature>({
    source: createAlarmSource(features),
    style: getAlarmZoneStyle(getPalette()),
    zIndex: 75,
  });
}

export const alarmZone: AuroraLayer = {
  id: 'alarmZone',
  title: 'Alarms',
  category: 'route',
  defaultVisible: true,
  defaultOpacity: 1,
  // Alarms are pushed, not polled: there is no "quiet channel" to go stale
  // on, and STALENESS_THRESHOLDS has no entry for one.
  stalenessKey: null,

  createLayer: () => build(useAlarmStore.getState()),

  update: (layer, state) => {
    const store = state as AlarmStore;
    const features = alarmFeatures(store);
    if (!features) return null;

    if (!layer || !isAlarmLayer(layer)) return build(store);

    const source = layer.getSource();
    if (source) syncAlarmSource(source, features);
    else layer.setSource(createAlarmSource(features));

    return layer;
  },

  restyle: (layer, palette) => {
    if (isAlarmLayer(layer)) layer.setStyle(getAlarmZoneStyle(palette));
  },

  subscribe: (onChange) => useAlarmStore.subscribe((state) => onChange(state)),
};
