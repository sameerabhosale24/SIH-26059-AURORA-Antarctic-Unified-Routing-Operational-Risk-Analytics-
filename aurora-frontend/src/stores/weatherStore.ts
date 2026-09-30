import { create } from 'zustand';

import { weatherWs } from '@/services/websocket';
import type { WeatherPoint } from '@/types/weather';
import { createDataSlice, type DataStore } from './createDataStore';
import { bindStatus, pickRecord, rejectFrame } from './wsBinding';

/**
 * Weather, wave and current at the vessel, fed by `WS /ws/weather`.
 *
 * One measurement point, not a grid: this is the value the forecast table and
 * the conning panel read, so a frame replaces it wholesale.
 */
export interface WeatherStore extends DataStore<WeatherPoint> {
  init(): () => void;
}

const CHANNEL = 'weather';

export const useWeatherStore = create<WeatherStore>()((set, get, api) => ({
  ...createDataSlice<WeatherPoint, WeatherStore>()(set, get, api),

  init: () => {
    const offMessage = weatherWs.onMessage((payload) => {
      const point = pickRecord<WeatherPoint>(payload, ['weather', 'point', 'latest']);

      if (!point) {
        rejectFrame(CHANNEL, payload);
        return;
      }

      get().set(point);
    });

    const offStatus = bindStatus(CHANNEL, (handler) => weatherWs.onStatus(handler));
    weatherWs.connect();

    return () => {
      offMessage();
      offStatus();
      weatherWs.close();
    };
  },
}));
