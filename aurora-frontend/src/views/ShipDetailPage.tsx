/**
 * Vessel detail — the read-only mirror of the add/edit sheet.
 *
 * Same eight sections, same labels, same tooltips, in the same order: an
 * operator can check "is the draft right?" by looking at the same words they
 * typed. Nothing here is editable in place; corrections go through the form,
 * so what is displayed is always exactly what is stored.
 */
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/Badge';
import { useVesselRecord } from '@/hooks/useVesselRecord';
import { useShipsStore } from '@/stores/shipsStore';
import { notify } from '@/stores/toastStore';
import type { Vessel } from '@/types/ship';
import { SHIP_SECTIONS, formatFieldValue } from './shipSections';

function DetailSection({ section, vessel }: { section: (typeof SHIP_SECTIONS)[number]; vessel: Vessel }): JSX.Element {
  return (
    <section className="rounded border border-aurora-border bg-aurora-panel">
      <header className="border-b border-aurora-border px-3 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-aurora-text">
          {section.title}
        </h2>
        <p className="mt-0.5 text-[11px] leading-snug text-aurora-muted">{section.hint}</p>
      </header>

      <dl className="grid gap-x-4 gap-y-2.5 p-3 sm:grid-cols-2">
        {section.fields.map((field) => (
          <div key={field.key} className="min-w-0">
            <dt className="text-[9px] uppercase tracking-[0.14em] text-aurora-muted" title={field.tooltip}>
              {field.label}
            </dt>
            <dd className="truncate text-xs text-aurora-text" title={formatFieldValue(vessel, field)}>
              {formatFieldValue(vessel, field)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function ShipDetailPage(): JSX.Element {
  const params = useParams();
  const navigate = useNavigate();

  const id = params.id ? Number(params.id) : undefined;
  const { vessel, loading, error, notFound, reload } = useVesselRecord(id);

  const removeShip = useShipsStore((state) => state.removeShip);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-aurora-muted">
        Loading vessel…
      </div>
    );
  }

  if (notFound || vessel === null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-sm text-aurora-text">
          {notFound ? 'That vessel does not exist' : 'Could not load that vessel'}
        </p>
        <p className="max-w-md text-[11px] leading-relaxed text-aurora-muted">
          {notFound
            ? 'It may have been deleted from the fleet, or this link is out of date.'
            : (error ?? 'The backend returned no record.')}
        </p>
        <Link
          to="/ships"
          className="rounded-sm bg-aurora-accent px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-aurora-bg"
        >
          Back to fleet
        </Link>
      </div>
    );
  }

  async function confirmDelete(): Promise<void> {
    if (!vessel) return;

    setDeleting(true);
    const ok = await removeShip(vessel.id);
    setDeleting(false);
    setConfirming(false);

    if (ok) {
      notify(`${vessel.name} deleted`, 'success');
      navigate('/ships');
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-aurora-border bg-aurora-panel px-3 py-2">
        <Link
          to="/ships"
          className="rounded-sm border border-aurora-border px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-muted transition-colors hover:text-aurora-text"
        >
          ← Fleet
        </Link>

        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold tracking-[0.12em] text-aurora-text">
            {vessel.name}
          </h1>
          <p className="truncate text-[11px] text-aurora-muted">
            {vessel.vessel_type} · IMO {vessel.imo}
            {vessel.operator ? ` · ${vessel.operator}` : ''}
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Badge tone="accent">{vessel.iacs_polar_class}</Badge>

          <Link
            to={`/map/${vessel.id}`}
            className="rounded-sm bg-aurora-accent px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-aurora-bg transition-opacity hover:opacity-90"
          >
            Open map
          </Link>

          <Link
            to={`/ships/${vessel.id}/edit`}
            className="rounded-sm border border-aurora-border px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-muted transition-colors hover:text-aurora-text"
          >
            Edit
          </Link>

          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded-sm border border-aurora-crit/40 px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-crit transition-colors hover:bg-aurora-crit/10"
          >
            Delete
          </button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-3">
        {error ? (
          <div className="mb-3 flex items-center gap-3 rounded border border-aurora-crit/40 bg-aurora-crit/10 px-3 py-2">
            <p className="text-xs text-aurora-crit">{error}</p>
            <button
              type="button"
              onClick={reload}
              className="ml-auto rounded-sm border border-aurora-crit/50 px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] text-aurora-crit hover:bg-aurora-crit/15"
            >
              Retry
            </button>
          </div>
        ) : null}

        <div className="mx-auto grid max-w-5xl gap-3 lg:grid-cols-2">
          {SHIP_SECTIONS.map((section) => (
            <DetailSection key={section.id} section={section} vessel={vessel} />
          ))}
        </div>
      </div>

      {confirming ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="detail-delete-title"
        >
          <div className="w-full max-w-sm rounded border border-aurora-border bg-aurora-panel p-4">
            <h2 id="detail-delete-title" className="text-sm font-semibold text-aurora-text">
              Delete {vessel.name}?
            </h2>

            <p className="mt-2 text-[11px] leading-relaxed text-aurora-muted">
              This removes the vessel and all of its stored limits from the fleet. Routes already
              computed for it are kept as history. This cannot be undone.
            </p>

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={deleting}
                className="rounded-sm border border-aurora-border px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-aurora-muted hover:text-aurora-text disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() => {
                  void confirmDelete();
                }}
                disabled={deleting}
                className="rounded-sm bg-aurora-crit px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-white hover:opacity-90 disabled:opacity-50"
              >
                {deleting ? 'Deleting…' : 'Delete vessel'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
