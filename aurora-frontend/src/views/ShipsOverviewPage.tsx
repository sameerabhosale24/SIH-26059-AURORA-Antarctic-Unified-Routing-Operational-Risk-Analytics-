/**
 * Fleet overview — every vessel the operator can plan with.
 *
 * Three states are first-class and mutually exclusive: loading, failed, empty.
 * "No vessels" and "the backend is unreachable" must never look alike, so the
 * empty state carries an action and the error state carries a retry.
 *
 * Deletion is the one destructive action in the fleet, so it always passes
 * through a confirmation that names the vessel being removed.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { useShipsStore } from '@/stores/shipsStore';
import { notify } from '@/stores/toastStore';
import type { Vessel } from '@/types/ship';
import { EM_DASH, fmtDateTime } from '@/utils/formatting';

function lastUsed(vessel: Vessel): string {
  const stamp = vessel.updated_at ?? vessel.created_at;
  return stamp ? fmtDateTime(stamp) : 'Never';
}

function stat(label: string, value: string | null | undefined): JSX.Element {
  return (
    <div className="min-w-0">
      <dt className="text-[9px] uppercase tracking-[0.14em] text-aurora-muted">{label}</dt>
      <dd className="truncate font-mono text-[11px] text-aurora-text">{value || EM_DASH}</dd>
    </div>
  );
}

function ShipCard({
  vessel,
  onEdit,
  onDelete,
}: {
  vessel: Vessel;
  onEdit: (vessel: Vessel) => void;
  onDelete: (vessel: Vessel) => void;
}): JSX.Element {
  return (
    <article className="flex flex-col rounded border border-aurora-border bg-aurora-panel">
      <header className="flex items-start justify-between gap-2 border-b border-aurora-border px-3 py-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-aurora-text" title={vessel.name}>
            {vessel.name}
          </h3>
          <p className="truncate text-[10px] uppercase tracking-[0.14em] text-aurora-muted">
            {vessel.vessel_type} · {vessel.imo}
          </p>
        </div>

        <Badge tone="accent">{vessel.iacs_polar_class}</Badge>
      </header>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 px-3 py-2.5 sm:grid-cols-3">
        {stat('MMSI', vessel.mmsi)}
        {stat('Flag', vessel.flag)}
        {stat('Call sign', vessel.call_sign)}
        {stat('Economical', `${vessel.economical_speed_kt} kt`)}
        {stat('In ice', `${vessel.speed_in_ice_kt} kt`)}
        {stat('Ice / SIC', `${vessel.max_ice_thickness_m} m · ${Math.round(vessel.max_sic * 100)}%`)}
        {stat('Fuel', `${vessel.fuel_capacity_t} t`)}
        {stat('Endurance', vessel.endurance_days ? `${vessel.endurance_days} d` : null)}
        {stat('Last used', lastUsed(vessel))}
      </dl>

      <footer className="mt-auto flex items-center gap-2 border-t border-aurora-border px-3 py-2">
        <Link
          to={`/map/${vessel.id}`}
          className="rounded-sm bg-aurora-accent/15 px-2 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-aurora-accent transition-colors hover:bg-aurora-accent/25"
        >
          Open
        </Link>

        <Link
          to={`/ships/${vessel.id}`}
          className="rounded-sm border border-aurora-border px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-muted transition-colors hover:text-aurora-text"
        >
          Details
        </Link>

        <button
          type="button"
          onClick={() => onEdit(vessel)}
          className="rounded-sm border border-aurora-border px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-muted transition-colors hover:text-aurora-text"
        >
          Edit
        </button>

        <button
          type="button"
          onClick={() => onDelete(vessel)}
          className="ml-auto rounded-sm border border-aurora-crit/40 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-crit transition-colors hover:bg-aurora-crit/10"
        >
          Delete
        </button>
      </footer>
    </article>
  );
}

function ConfirmDelete({
  vessel,
  onConfirm,
  onCancel,
  busy,
}: {
  vessel: Vessel;
  onConfirm: () => void;
  onCancel: () => void;
  busy: boolean;
}): JSX.Element {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-delete-title"
    >
      <div className="w-full max-w-sm rounded border border-aurora-border bg-aurora-panel p-4">
        <h2 id="confirm-delete-title" className="text-sm font-semibold text-aurora-text">
          Delete {vessel.name}?
        </h2>

        <p className="mt-2 text-[11px] leading-relaxed text-aurora-muted">
          This removes the vessel and all of its stored limits from the fleet. Routes already
          computed for it are kept as history. This cannot be undone.
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-sm border border-aurora-border px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-aurora-muted transition-colors hover:text-aurora-text disabled:opacity-50"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-sm bg-aurora-crit px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? 'Deleting…' : 'Delete vessel'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ShipsOverviewPage(): JSX.Element {
  const navigate = useNavigate();

  const list = useShipsStore((state) => state.list);
  const loading = useShipsStore((state) => state.loading);
  const error = useShipsStore((state) => state.error);
  const loadedAt = useShipsStore((state) => state.loadedAt);
  const fetchShips = useShipsStore((state) => state.fetchShips);
  const removeShip = useShipsStore((state) => state.removeShip);
  const reset = useShipsStore((state) => state.reset);

  const [query, setQuery] = useState('');
  const [pendingDelete, setPendingDelete] = useState<Vessel | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Load once per signed-in visit; `loadedAt` makes this idempotent across
  // remounts (navigating away and back must not re-hit the backend).
  useEffect(() => {
    void fetchShips();
  }, [fetchShips, loadedAt]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return list;

    return list.filter((vessel) =>
      [vessel.name, vessel.imo, vessel.mmsi ?? '', vessel.call_sign ?? '', vessel.flag]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    );
  }, [list, query]);

  const hasQuery = query.trim().length > 0;
  const showSkeleton = loading && list.length === 0 && !hasQuery;

  // With an error and nothing loaded, the banner above is the whole story —
  // falling through to an empty state would offer to "add your first vessel"
  // while the reason none are listed is that the backend never answered.
  const showLoadFailed = error !== null && list.length === 0;
  const showEmpty = !showSkeleton && !showLoadFailed && list.length === 0 && !hasQuery;
  const showNoMatch = !showSkeleton && !showLoadFailed && !showEmpty && filtered.length === 0;

  async function confirmDelete(): Promise<void> {
    if (!pendingDelete) return;

    setDeleting(true);
    const ok = await removeShip(pendingDelete.id);
    setDeleting(false);
    setPendingDelete(null);

    if (ok) notify(`${pendingDelete.name} deleted`, 'success');
  }

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-3 p-3">
      <header className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-base font-semibold tracking-[0.14em] text-aurora-text">Vessels</h1>
          <p className="text-[11px] text-aurora-muted">
            {list.length === 1 ? '1 vessel' : `${list.length} vessels`}
            {loadedAt ? ` · refreshed ${fmtDateTime(new Date(loadedAt).toISOString())}` : ''}
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, IMO, MMSI…"
            aria-label="Search vessels"
            title="Filter the fleet by name, IMO number, MMSI, call sign or flag"
            className="w-44 rounded-sm border border-aurora-border bg-aurora-panel px-2.5 py-1.5 text-xs text-aurora-text outline-none transition-colors focus:border-aurora-accent sm:w-64"
          />

          <button
            type="button"
            onClick={() => navigate('/ships/new')}
            className="rounded-sm bg-aurora-accent px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-aurora-bg transition-opacity hover:opacity-90"
          >
            Add vessel
          </button>
        </div>
      </header>

      {error ? (
        <div className="flex items-center gap-3 rounded border border-aurora-crit/40 bg-aurora-crit/10 px-3 py-2">
          <p className="text-xs text-aurora-crit">{error}</p>

          <button
            type="button"
            onClick={() => {
              reset();
              void fetchShips(true);
            }}
            disabled={loading}
            className="ml-auto rounded-sm border border-aurora-crit/50 px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-crit transition-colors hover:bg-aurora-crit/15 disabled:opacity-50"
          >
            {loading ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {showSkeleton ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                className="h-40 animate-pulse rounded border border-aurora-border bg-aurora-panel/60"
              />
            ))}
          </div>
        ) : showLoadFailed ? null : showEmpty ? (
          <EmptyState
            message="No vessels yet"
            hint="Add your first vessel to give routing something to constrain against."
          />
        ) : showNoMatch ? (
          <EmptyState message="No vessels match that search" hint="Clear the filter to see the fleet." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((vessel) => (
              <ShipCard
                key={vessel.id}
                vessel={vessel}
                onEdit={(target) => navigate(`/ships/${target.id}/edit`)}
                onDelete={setPendingDelete}
              />
            ))}
          </div>
        )}
      </div>

      {pendingDelete ? (
        <ConfirmDelete
          vessel={pendingDelete}
          busy={deleting}
          onConfirm={() => {
            void confirmDelete();
          }}
          onCancel={() => setPendingDelete(null)}
        />
      ) : null}
    </div>
  );
}
