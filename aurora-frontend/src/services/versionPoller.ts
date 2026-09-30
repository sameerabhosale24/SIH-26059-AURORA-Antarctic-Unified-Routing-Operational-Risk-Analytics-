/**
 * Polls `GET /api/version` and reports which data products have been
 * republished.
 *
 * This module deliberately does NOT touch any store. Refetch orchestration
 * lives in the app shell (Part 2 wires `onVersionChange` → store refetches);
 * keeping the poller side-effect free makes it testable and prevents
 * accidental refresh storms.
 */
import { VERSION_POLL_INTERVAL_MS } from '@/config/constants';
import { getVersion } from './api';
import { diffVersions, type DataVersion, type DataVersionKey } from '@/types/version';

export type VersionChangeHandler = (version: DataVersion, changed: DataVersionKey[]) => void;

const handlers = new Set<VersionChangeHandler>();

let lastVersion: DataVersion | null = null;
let timer: ReturnType<typeof setInterval> | null = null;
let pollInFlight = false;

/** Bumped by `stopPolling` so a late in-flight reply is discarded. */
let generation = 0;

/**
 * Subscribe to version changes.
 *
 * The first successful poll after startup reports every key in `changed`
 * (there is no prior snapshot to diff against), which lets the shell treat
 * "first load" and "republished" through one code path.
 */
export function onVersionChange(handler: VersionChangeHandler): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}

/** Most recent version snapshot, or null before the first successful poll. */
export function getCurrentVersion(): DataVersion | null {
  return lastVersion;
}

/** Drop the cached snapshot so the next poll reports a full change set. */
export function resetVersionSnapshot(): void {
  lastVersion = null;
}

/**
 * Start polling. Polls once immediately, then every `intervalMs`.
 * Calling this while already running is a no-op and returns the existing stop
 * function's behaviour is unchanged.
 *
 * @returns a stop function; safe to call more than once.
 */
export function startVersionPoller(intervalMs: number = VERSION_POLL_INTERVAL_MS): () => void {
  if (timer !== null) return stopPolling;

  void pollOnce();

  timer = setInterval(() => {
    void pollOnce();
  }, intervalMs);

  return stopPolling;
}

/** Stop polling and release the interval. Idempotent. */
export function stopPolling(): void {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }

  // Invalidate any in-flight poll so its reply cannot emit after shutdown.
  generation += 1;
  pollInFlight = false;
}

/**
 * One poll cycle. Errors are logged and swallowed: a backend outage must not
 * surface as an unhandled rejection, and the next tick simply tries again.
 */
async function pollOnce(): Promise<void> {
  if (pollInFlight) return;
  pollInFlight = true;

  const cycle = generation;

  try {
    const version = await getVersion();

    if (cycle !== generation) return;

    const changed = diffVersions(lastVersion, version);

    lastVersion = version;

    if (changed.length > 0) {
      emit(version, changed);
    }
  } catch (cause) {
    if (cycle === generation) {
      console.warn('[aurora] version poll failed', cause);
    }
  } finally {
    if (cycle === generation) {
      pollInFlight = false;
    }
  }
}

function emit(version: DataVersion, changed: DataVersionKey[]): void {
  for (const handler of handlers) {
    try {
      handler(version, changed);
    } catch (cause) {
      console.error('[aurora] version-change handler threw', cause);
    }
  }
}
