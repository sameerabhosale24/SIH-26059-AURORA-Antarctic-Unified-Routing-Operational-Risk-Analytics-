/**
 * Primary navigation.
 *
 * The four views are routes, but they are also *modes* — the operator thinks
 * "I am in planning now", not "I am on /planning/17". The two are kept in
 * sync here so `uiStore.mode` stays a trustworthy input for anything that
 * behaves differently per mode, and so a deep link still lands with the right
 * mode set.
 *
 * Every view link is scoped to the selected vessel. With no vessel selected
 * (the fleet pages) the links are disabled rather than pointing somewhere
 * that would only bounce back: a view with no ship is not a destination.
 */
import { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import type { UiMode } from '@/stores/uiStore';
import { useUiStore } from '@/stores/uiStore';
import { useVesselStore } from '@/stores/vesselStore';

const ITEMS: ReadonlyArray<{ mode: UiMode; base: string; label: string }> = [
  { mode: 'operational', base: '/map', label: 'Operational' },
  { mode: 'planning', base: '/planning', label: 'Planning' },
  { mode: 'analysis', base: '/analysis', label: 'Analysis' },
  { mode: 'settings', base: '/settings', label: 'Settings' },
];

const MODE_FOR_BASE: Record<string, UiMode> = {
  '/map': 'operational',
  '/planning': 'planning',
  '/analysis': 'analysis',
  '/settings': 'settings',
};

function modeForPath(pathname: string): UiMode {
  const [, base] = pathname.split('/');
  return (base ? MODE_FOR_BASE[`/${base}`] : undefined) ?? 'operational';
}

export function ViewNav(): JSX.Element {
  const location = useLocation();
  const setMode = useUiStore((state) => state.setMode);

  const mode = modeForPath(location.pathname);
  const vesselId = useVesselStore((state) => state.vesselId);

  useEffect(() => {
    setMode(mode);
  }, [mode, setMode]);

  const onFleet = location.pathname.startsWith('/ships') || location.pathname === '/login';

  return (
    <nav className="flex shrink-0 items-center gap-1 border-b border-aurora-border bg-aurora-bg px-2">
      <NavLink
        to="/ships"
        className={`border-b-2 px-2.5 py-1.5 text-[11px] uppercase tracking-[0.14em] transition-colors ${
          onFleet
            ? 'border-aurora-accent text-aurora-accent'
            : 'border-transparent text-aurora-muted hover:text-aurora-text'
        }`}
      >
        Fleet
      </NavLink>

      <span className="mx-1 h-4 w-px bg-aurora-border" />

      {ITEMS.map((item) => {
        const active = !onFleet && item.mode === mode;
        const disabled = vesselId === null;

        if (disabled) {
          return (
            <span
              key={item.mode}
              title="Open a vessel from the fleet first"
              className="cursor-not-allowed border-b-2 border-transparent px-2.5 py-1.5 text-[11px] uppercase tracking-[0.14em] text-aurora-muted/40"
            >
              {item.label}
            </span>
          );
        }

        return (
          <NavLink
            key={item.mode}
            to={`${item.base}/${vesselId}`}
            className={`border-b-2 px-2.5 py-1.5 text-[11px] uppercase tracking-[0.14em] transition-colors ${
              active
                ? 'border-aurora-accent text-aurora-accent'
                : 'border-transparent text-aurora-muted hover:text-aurora-text'
            }`}
          >
            {item.label}
          </NavLink>
        );
      })}

      <span className="ml-auto pr-1 text-[10px] text-aurora-muted/70">
        {vesselId === null ? 'No vessel selected' : `Vessel #${vesselId}`}
      </span>
    </nav>
  );
}
