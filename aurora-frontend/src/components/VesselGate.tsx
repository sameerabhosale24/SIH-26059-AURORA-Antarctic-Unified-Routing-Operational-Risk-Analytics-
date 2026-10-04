/**
 * Blocking wrapper for the vessel-scoped views.
 *
 * A map with no blueprint behind it would still draw — and then quietly
 * assume limits nobody entered. So the gate holds the view back until the
 * vessel named in the URL is loaded into `vesselStore`, and shows a full
 * panel (not a toast, not a spinner in a corner) whenever it cannot.
 *
 * Everything it blocks on is a fetch the view would otherwise have to
 * duplicate four times; the map, the panels and the status bar all continue
 * to read their own stores as before.
 */
import { useEffect, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useVesselRecord } from '@/hooks/useVesselRecord';
import { useVesselStore } from '@/stores/vesselStore';

function Blocked({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
}): JSX.Element {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm font-semibold tracking-[0.1em] text-ocean-100">{title}</p>
      <p className="max-w-md text-[11px] leading-relaxed text-ocean-300">{message}</p>

      <div className="flex items-center gap-2">
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-sm border border-ocean-600 px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-ocean-300 transition-colors hover:bg-ocean-800 hover:text-ocean-100"
          >
            Retry
          </button>
        ) : null}

        <Link
          to="/ships"
          className="rounded-sm bg-ocean-600 hover:bg-ocean-500 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-white "
        >
          Back to fleet
        </Link>
      </div>
    </div>
  );
}

export function VesselGate({ children }: { children: ReactNode }): JSX.Element {
  const params = useParams();
  const raw = params.vesselId;
  const id = raw !== undefined && /^\d+$/.test(raw) ? Number(raw) : undefined;

  const { vessel, loading, error, notFound, reload } = useVesselRecord(id);
  const setVessel = useVesselStore((state) => state.setVessel);

  useEffect(() => {
    if (vessel !== null && vessel.id === id) setVessel(vessel.id, vessel);
  }, [vessel, id, setVessel]);

  // Readiness is judged from the fetch, not from the store: the store is
  // updated one effect later, and waiting on it would flash the error panel
  // for a frame on every successful load.
  const ready = vessel !== null && id !== undefined && vessel.id === id;

  if (loading && !ready) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-ocean-300">
        Loading vessel…
      </div>
    );
  }

  if (notFound) {
    return (
      <Blocked
        title="Vessel not found"
        message="No vessel with that id exists on this fleet. It may have been deleted, or the link is out of date."
      />
    );
  }

  if (!ready) {
    return (
      <Blocked
        title="Vessel not loaded"
        message={error ?? 'The blueprint for this vessel could not be retrieved from the backend.'}
        onRetry={reload}
      />
    );
  }

  return <>{children}</>;
}
