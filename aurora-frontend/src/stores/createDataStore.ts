/**
 * Shared shape for every AURORA data store.
 *
 * All stores follow the same contract so that UI code (and `useStaleness`) can
 * treat them uniformly:
 *
 *  - `data` starts as `null`. It is never a zero-filled object, never an empty
 *    placeholder, and never fabricated. `null` means "no data yet" and drives
 *    the empty state.
 *  - `lastUpdated` is the client-side wall-clock time the payload arrived
 *    (ms since epoch), not the producer's `ts` field. Staleness is about how
 *    long *we* have been blind, so arrival time is the correct reference.
 *  - `error` holds the last transport/decoding failure for display only; it
 *    never replaces `data`, so a transient blip does not blank the screen.
 */
import type { StateCreator } from 'zustand';

/** Read-only slice present on every data store. */
export interface DataState<T> {
  data: T | null;
  lastUpdated: number | null;
  error: string | null;
}

/** Actions present on every data store. */
export interface DataActions<T> {
  /** Replace the payload and stamp `lastUpdated`. `null` clears the timestamp. */
  set(data: T | null): void;
  /** Record (or clear) a transport error without touching `data`. */
  setError(msg: string | null): void;
  /** Full reset — used on sign-out or vessel change. */
  clear(): void;
}

export type DataStore<T> = DataState<T> & DataActions<T>;

/**
 * Build the shared slice for a store.
 *
 * `S` is the store's *final* shape, so the returned `set` also accepts the
 * store's own extra fields while the slice stays fully typed.
 *
 * ```ts
 * export const useFooStore = create<FooStore>()((set, get, api) => ({
 *   ...createDataSlice<FooPayload, FooStore>()(set, get, api),
 *   selected: 1,
 * }));
 * ```
 */
export function createDataSlice<T, S extends DataStore<T>>(): StateCreator<S, [], [], DataStore<T>> {
  return (set) => {
    // `S` is opaque to this factory, so each patch is cast to `Partial<S>`.
    // The cast is safe because every key written here is part of DataStore<T>,
    // which `S` is constrained to extend.
    const patch = (update: Partial<DataStore<T>>): void => {
      set(update as Partial<S>);
    };

    return {
      data: null,
      lastUpdated: null,
      error: null,

      set: (data) =>
        patch({
          data,
          lastUpdated: data === null ? null : Date.now(),
          error: null,
        }),

      setError: (error) => patch({ error }),

      clear: () => patch({ data: null, lastUpdated: null, error: null }),
    };
  };
}

/** Best-effort human-readable message from an unknown thrown value. */
export function toErrorMessage(cause: unknown): string {
  if (cause instanceof Error) return cause.message;
  if (typeof cause === 'string') return cause;
  return String(cause);
}
