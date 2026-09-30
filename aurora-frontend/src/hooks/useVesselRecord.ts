/**
 * Load one vessel blueprint by id.
 *
 * Used by the fleet pages and by the map views, which all need the same
 * three answers — loading, missing, failed — and must not tell those apart by
 * inspecting a string. The hook never touches `vesselStore`; selecting a
 * vessel for the map is a separate decision made by the view.
 */
import { useEffect, useState } from 'react';

import { getVessel } from '@/services/api';
import type { Vessel } from '@/types/ship';

export interface VesselRecordState {
  vessel: Vessel | null;
  loading: boolean;
  /** Non-null when the request failed for a reason other than 404. */
  error: string | null;
  /** The id is valid but no such vessel exists. */
  notFound: boolean;
}

export function useVesselRecord(id: number | undefined): VesselRecordState & { reload(): void } {
  const [state, setState] = useState<VesselRecordState>({
    vessel: null,
    loading: id !== undefined,
    error: null,
    notFound: false,
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (id === undefined || Number.isNaN(id)) {
      setState({ vessel: null, loading: false, error: null, notFound: true });
      return;
    }

    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null, notFound: false }));

    getVessel(id)
      .then((vessel) => {
        if (!cancelled) setState({ vessel, loading: false, error: null, notFound: false });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;

        const status =
          cause && typeof cause === 'object' && 'status' in cause
            ? (cause as { status?: number }).status
            : undefined;

        if (status === 404) {
          setState({ vessel: null, loading: false, error: null, notFound: true });
          return;
        }

        setState({
          vessel: null,
          loading: false,
          error: cause instanceof Error ? cause.message : 'Could not load that vessel.',
          notFound: false,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  return { ...state, reload: () => setAttempt((value) => value + 1) };
}
