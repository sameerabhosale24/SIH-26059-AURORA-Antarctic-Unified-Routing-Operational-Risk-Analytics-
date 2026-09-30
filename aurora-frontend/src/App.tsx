/**
 * Application shell.
 *
 * Responsibilities:
 *  - register the projection once, before the map or any view can use it,
 *  - start the version poller and the data-sync path (initial REST load,
 *    WebSocket store subscriptions, version → refetch → toast),
 *  - lay out the status bar, the routed view, the toast stack and the
 *    connection overlay.
 *
 * Nothing here refreshes the page or discards view state when data changes —
 * a republished forecast updates a panel, it does not move the operator's
 * viewport.
 */
import { useEffect } from 'react';

import { ConnectionStatusOverlay } from '@/components/ConnectionStatusOverlay';
import { ToastHost } from '@/components/ToastHost';
import { ViewNav } from '@/components/ViewNav';
import { StatusBar } from '@/panels/StatusBar';
import { VERSION_POLL_INTERVAL_MS } from '@/config/constants';
import { registerLccProjection } from '@/config/projection';
import { CHROME_CLASS } from '@/map/layers/types';
import { AppRoutes } from '@/router';
import { initDataSync } from '@/services/dataSync';
import { startVersionPoller } from '@/services/versionPoller';
import { useUiStore } from '@/stores/uiStore';
import { useUserStore } from '@/stores/userStore';

export function App(): JSX.Element {
  const displayMode = useUiStore((state) => state.displayMode);
  const signedIn = useUserStore((state) => state.user !== null);

  useEffect(() => {
    // Register the projection eagerly so a console check works before the map
    // mounts, and so any failure surfaces here rather than mid-render.
    registerLccProjection();
  }, []);

  useEffect(() => {
    // Everything below talks to the backend and therefore carries the bearer
    // token. Starting it before sign-in would fire an unauthenticated wave
    // that a real backend answers with 401 — and a 401 while the operator is
    // still typing their password is not a helpful first impression.
    if (!signedIn) return undefined;

    const stopPoller = startVersionPoller(VERSION_POLL_INTERVAL_MS);
    const stopSync = initDataSync();

    return () => {
      stopSync();
      stopPoller();
    };
  }, [signedIn]);

  return (
    <div className={`flex h-full min-h-0 flex-col ${CHROME_CLASS[displayMode]}`}>
      {/* The console chrome belongs to an operator who is signed in. On
          `/login` it would advertise controls that cannot be used and a vessel
          that has not been chosen. */}
      {signedIn ? <StatusBar /> : null}
      {signedIn ? <ViewNav /> : null}

      <main className="min-h-0 flex-1">
        <AppRoutes />
      </main>

      <ToastHost />
      <ConnectionStatusOverlay />
    </div>
  );
}
