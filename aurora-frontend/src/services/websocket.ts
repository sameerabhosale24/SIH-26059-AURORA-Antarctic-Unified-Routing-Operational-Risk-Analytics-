/**
 * Resilient WebSocket manager.
 *
 * Design rules, in priority order:
 *  1. Never crash the app on connection loss — report status and let the
 *     consuming store go stale.
 *  2. Never buffer messages received while disconnected.
 *  3. Never replay missed messages on reconnect — the store resyncs over REST.
 *
 * Instances are NOT connected on import. A store (or `useWebSocket`) calls
 * `connect()` when it is ready to consume the stream.
 */
import { WS_RECONNECT_BASE_MS, WS_RECONNECT_MAX_MS } from '@/config/constants';
import { WS_BASE } from '@/config/env';

/** Connection lifecycle state of a channel. */
export type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

export type WsMessageHandler = (data: unknown) => void;
export type WsStatusHandler = (status: WsStatus) => void;

/** Unsubscribe function returned by every `on*` registration. */
export type Unsubscribe = () => void;

export class AuroraWebSocket {
  /** Path relative to `WS_BASE`, e.g. `/ws/vessel`. */
  readonly path: string;

  /** Channel name derived from the path, e.g. `vessel`. Used as a dataStore key. */
  readonly channel: string;

  /** Absolute endpoint, without a cache-busting query. */
  readonly url: string;

  private socket: WebSocket | null = null;
  private currentStatus: WsStatus = 'closed';
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByCaller = false;

  private readonly messageHandlers = new Set<WsMessageHandler>();
  private readonly statusHandlers = new Set<WsStatusHandler>();

  constructor(path: string) {
    if (!path.startsWith('/')) {
      throw new Error(`WebSocket path must start with "/", received "${path}"`);
    }

    this.path = path;
    this.channel = path.replace(/^\/ws\/?/, '') || 'default';
    this.url = `${WS_BASE}${path}`;
  }

  /** Current lifecycle state. */
  get status(): WsStatus {
    return this.currentStatus;
  }

  /**
   * Open the socket, or do nothing if it is already open or connecting.
   * Safe to call repeatedly.
   */
  connect(): void {
    this.closedByCaller = false;
    this.clearReconnectTimer();

    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.open();
  }

  /**
   * Close the socket and stop reconnecting. The instance can be re-opened with
   * `connect()` later.
   */
  close(): void {
    this.closedByCaller = true;
    this.clearReconnectTimer();

    if (this.socket) {
      const socket = this.socket;
      this.socket = null;
      // Detach handlers first so `close()` cannot trigger a reconnect.
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;

      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1000, 'client shutdown');
      }
    }

    this.setStatus('closed');
  }

  /** Subscribe to parsed JSON messages. Returns an unsubscribe function. */
  onMessage(handler: WsMessageHandler): Unsubscribe {
    this.messageHandlers.add(handler);
    return () => {
      this.messageHandlers.delete(handler);
    };
  }

  /** Subscribe to connection status changes. Returns an unsubscribe function. */
  onStatus(handler: WsStatusHandler): Unsubscribe {
    this.statusHandlers.add(handler);
    return () => {
      this.statusHandlers.delete(handler);
    };
  }

  private open(): void {
    this.setStatus('connecting');

    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch (cause) {
      console.error(`[aurora] ${this.channel}: could not open ${this.url}`, cause);
      this.setStatus('error');
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;

    socket.onopen = () => {
      // A successful handshake resets backoff so the next outage starts at 1s.
      this.attempt = 0;
      this.setStatus('open');
    };

    socket.onmessage = (event: MessageEvent<unknown>) => {
      this.dispatch(event.data);
    };

    socket.onerror = () => {
      // The browser deliberately hides the reason; `onclose` does the recovery.
      this.setStatus('error');
    };

    socket.onclose = () => {
      this.socket = null;
      this.setStatus('closed');
      if (!this.closedByCaller) this.scheduleReconnect();
    };
  }

  /** Decode one frame and fan it out. Malformed frames are logged and dropped. */
  private dispatch(raw: unknown): void {
    let payload: unknown;

    if (typeof raw === 'string') {
      try {
        payload = JSON.parse(raw);
      } catch {
        console.warn(`[aurora] ${this.channel}: dropping non-JSON message`);
        return;
      }
    } else if (raw instanceof Blob || raw instanceof ArrayBuffer) {
      console.warn(`[aurora] ${this.channel}: dropping binary message`);
      return;
    } else {
      payload = raw;
    }

    for (const handler of this.messageHandlers) {
      try {
        handler(payload);
      } catch (cause) {
        // One bad subscriber must not tear down the channel.
        console.error(`[aurora] ${this.channel}: message handler threw`, cause);
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.closedByCaller || this.reconnectTimer !== null) return;

    const delay = Math.min(WS_RECONNECT_BASE_MS * 2 ** this.attempt, WS_RECONNECT_MAX_MS);
    this.attempt += 1;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setStatus(status: WsStatus): void {
    if (this.currentStatus === status) return;
    this.currentStatus = status;

    for (const handler of this.statusHandlers) {
      try {
        handler(status);
      } catch (cause) {
        console.error(`[aurora] ${this.channel}: status handler threw`, cause);
      }
    }
  }
}

/* ------------------------------------------------------------------ *
 * Channel singletons — created eagerly, never connected on import.
 * ------------------------------------------------------------------ */

export const vesselWs = new AuroraWebSocket('/ws/vessel');
export const aisWs = new AuroraWebSocket('/ws/ais');
export const alarmsWs = new AuroraWebSocket('/ws/alarms');
export const weatherWs = new AuroraWebSocket('/ws/weather');
export const routeWs = new AuroraWebSocket('/ws/route');

/** All channel singletons, keyed by channel name. */
export const WEBSOCKET_CHANNELS = {
  vessel: vesselWs,
  ais: aisWs,
  alarms: alarmsWs,
  weather: weatherWs,
  route: routeWs,
} as const satisfies Record<string, AuroraWebSocket>;

export type WsChannel = keyof typeof WEBSOCKET_CHANNELS;
