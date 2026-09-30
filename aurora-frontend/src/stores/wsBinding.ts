/**
 * Helpers for binding a WebSocket channel to a store.
 *
 * The backend's push frames are not contract-tested on the client, so every
 * binding accepts the shapes a reasonable producer might send — a bare value,
 * a bare array, or a single-key envelope — and refuses anything else rather
 * than writing garbage into a store. A refused frame is logged once per
 * channel and the store keeps its previous (possibly stale) data, which the
 * UI already knows how to show.
 */
import { useDataStore } from '@/stores/dataStore';
import type { Unsubscribe, WsStatus } from '@/services/websocket';

/** Record-shaped guard: non-null object, not an array. */
export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Locate a single record inside a frame.
 *
 * @param keys envelope keys to try, in order, before treating the frame
 *             itself as the record.
 */
export function pickRecord<T>(payload: unknown, keys: readonly string[]): T | null {
  if (isPlainObject(payload)) {
    for (const key of keys) {
      const inner = payload[key];
      if (isPlainObject(inner)) return inner as T;
    }
    return payload as T;
  }
  return null;
}

/**
 * Locate a list inside a frame.
 *
 * @param keys envelope keys to try, in order.
 */
export function pickList<T>(payload: unknown, keys: readonly string[]): T[] | null {
  if (Array.isArray(payload)) return payload as T[];
  if (isPlainObject(payload)) {
    for (const key of keys) {
      const inner = payload[key];
      if (Array.isArray(inner)) return inner as T[];
    }
  }
  return null;
}

/**
 * Mirror a channel's lifecycle into `dataStore.wsStatus`.
 *
 * The status badge is the only place connection health is shown, so every
 * binding routes through here rather than each store inventing its own.
 */
export function bindStatus(channel: string, onStatus: (handler: (status: WsStatus) => void) => Unsubscribe): Unsubscribe {
  return onStatus((status) => useDataStore.getState().setWsStatus(channel, status));
}

/** Log-and-drop helper for frames a channel cannot interpret. */
export function rejectFrame(channel: string, payload: unknown): void {
  console.warn(`[aurora] ${channel}: ignoring unrecognised frame`, payload);
}
