/**
 * React binding for an {@link AuroraWebSocket} channel.
 *
 * On mount: subscribes to messages and status, publishes status into
 * `dataStore`, and connects. On unmount: unsubscribes.
 *
 * The socket is intentionally NOT closed on unmount. Channel instances are
 * singletons shared by several components; tearing one down when a panel
 * remounts would drop a stream that others still need. Lifecycle is owned by
 * the store's own init function.
 */
import { useEffect, useRef, useState } from 'react';
import type { AuroraWebSocket, WsStatus } from '@/services/websocket';
import { useDataStore } from '@/stores/dataStore';

export interface UseWebSocketResult {
  status: WsStatus;
}

export function useWebSocket<T>(
  ws: AuroraWebSocket,
  storeSetter: (data: T) => void,
): UseWebSocketResult {
  const [status, setStatus] = useState<WsStatus>(ws.status);

  // Held in a ref so an inline arrow function in the caller does not tear down
  // and rebuild the subscription on every render.
  const setterRef = useRef(storeSetter);

  useEffect(() => {
    setterRef.current = storeSetter;
  }, [storeSetter]);

  useEffect(() => {
    const offMessage = ws.onMessage((data) => setterRef.current(data as T));

    const offStatus = ws.onStatus((next) => {
      setStatus(next);
      useDataStore.getState().setWsStatus(ws.channel, next);
    });

    // Adopt the state we may have missed between render and effect.
    useDataStore.getState().setWsStatus(ws.channel, ws.status);
    setStatus(ws.status);

    ws.connect();

    return () => {
      offMessage();
      offStatus();
    };
  }, [ws]);

  return { status };
}
