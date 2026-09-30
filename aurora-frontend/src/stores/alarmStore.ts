import { create } from 'zustand';

import { alarmsWs } from '@/services/websocket';
import type { Alarm } from '@/types/alarm';
import { createDataSlice, type DataStore } from './createDataStore';
import { bindStatus, pickList, rejectFrame } from './wsBinding';

/**
 * Severity ordering, most urgent first. Used to sort the alarm list so a new
 * low-priority alarm can never push a critical one down the panel.
 */
const SEVERITY_RANK: Record<Alarm['severity'], number> = {
  critical: 0,
  warning: 1,
  caution: 2,
};

export interface AlarmStore extends DataStore<Alarm[]> {
  /**
   * Insert or update a single alarm, newest first.
   *
   * Called per message from `WS /ws/alarms`, which pushes individual alarm
   * state changes rather than the full list. An alarm already present is
   * replaced in place (keeping its position) so an ack does not reorder the
   * panel. Sets `newestId` so the panel can pulse the affected row.
   */
  add(alarm: Alarm): void;

  /** Id of the most recently added alarm, or null. Drives the row pulse. */
  newestId: number | null;

  /**
   * Optimistically mark an alarm as acknowledged so the row reacts instantly.
   * The authoritative record arrives from `POST /api/alarms/{id}/ack` or the
   * next `WS /ws/alarms` frame.
   */
  ackLocal(id: number): void;

  init(): () => void;
}

const CHANNEL = 'alarms';

export const useAlarmStore = create<AlarmStore>()((set, get, api) => ({
  ...createDataSlice<Alarm[], AlarmStore>()(set, get, api),

  newestId: null,

  add: (alarm) =>
    set((state) => {
      const existing = state.data ?? [];
      const index = existing.findIndex((candidate) => candidate.id === alarm.id);

      const next =
        index >= 0
          ? existing.map((candidate, i) => (i === index ? alarm : candidate))
          : [...existing, alarm];

      next.sort((a, b) => {
        const bySeverity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
        if (bySeverity !== 0) return bySeverity;
        return Date.parse(b.ts) - Date.parse(a.ts);
      });

      return { data: next, lastUpdated: Date.now(), error: null, newestId: alarm.id };
    }),

  ackLocal: (id) =>
    set((state) => {
      const alarms = state.data;
      if (!alarms) return state;

      return {
        data: alarms.map((alarm) =>
          alarm.id === id && alarm.acked_at === null
            ? { ...alarm, acked_at: new Date().toISOString() }
            : alarm,
        ),
      };
    }),

  init: () => {
    const offMessage = alarmsWs.onMessage((payload) => {
      // The channel pushes either one alarm or a batch of state changes; both
      // are applied through `add`, which is the only path that maintains the
      // ordering and the newest-id pulse.
      const alarms = pickList<Alarm>(payload, ['alarms', 'items']);

      if (alarms) {
        for (const alarm of alarms) get().add(alarm);
        return;
      }

      const single = payload as Alarm | null;
      if (single && typeof single.id === 'number' && typeof single.severity === 'string') {
        get().add(single);
        return;
      }

      rejectFrame(CHANNEL, payload);
    });

    const offStatus = bindStatus(CHANNEL, (handler) => alarmsWs.onStatus(handler));
    alarmsWs.connect();

    return () => {
      offMessage();
      offStatus();
      alarmsWs.close();
    };
  },
}));
