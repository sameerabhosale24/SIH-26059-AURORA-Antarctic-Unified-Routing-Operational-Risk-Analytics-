/**
 * Connection health badge.
 *
 * The one piece of always-visible chrome in Part 1. It reads straight from
 * `dataStore`, so it reflects real transport state — it never guesses.
 *
 * At startup, before the backend has answered anything, `apiStatus` is `down`
 * and no WebSocket has connected, so this reads `API: down / WS: closed`.
 */
import { aggregateWsStatus, useDataStore } from '@/stores/dataStore';

const API_TONE: Record<string, string> = {
  ok: 'text-aurora-ok',
  degraded: 'text-aurora-warn',
  down: 'text-aurora-crit',
};

const WS_TONE: Record<string, string> = {
  open: 'text-aurora-ok',
  connecting: 'text-aurora-warn',
  closed: 'text-aurora-muted',
  error: 'text-aurora-crit',
};

export function ConnectionStatusOverlay(): JSX.Element {
  const apiStatus = useDataStore((s) => s.apiStatus);
  const wsStatus = useDataStore((s) => s.wsStatus);

  const ws = aggregateWsStatus(wsStatus);

  return (
    <div
      className="pointer-events-none fixed bottom-3 left-3 z-50 select-none rounded border border-aurora-border bg-aurora-panel/90 px-2 py-1 font-mono text-[11px] leading-tight"
      role="status"
      aria-live="polite"
    >
      <span className={API_TONE[apiStatus] ?? 'text-aurora-muted'}>API: {apiStatus}</span>
      <span className="px-2 text-aurora-border">|</span>
      <span className={WS_TONE[ws] ?? 'text-aurora-muted'}>WS: {ws}</span>
    </div>
  );
}
