/**
 * Projection switcher — corridor, local, polar.
 *
 * Each preset is a different question about the same coastline:
 *
 *  - **corridor** — the mission ROI in LCC, the default planning view,
 *  - **local**    — a close-up radius around the vessel, for conning,
 *  - **polar**    — EPSG:3031, for judging distance across the continent.
 *
 * Switching re-frames the view; it never refetches or re-styles anything, and
 * it never moves the vessel's own data — only the projection it is drawn in.
 */
import type { UiProjection } from '@/stores/uiStore';
import { useUiStore } from '@/stores/uiStore';

const PRESETS: ReadonlyArray<{ id: UiProjection; label: string; hint: string }> = [
  { id: 'corridor', label: 'Corridor', hint: 'Mission region in LCC' },
  { id: 'local', label: 'Local', hint: 'Radius around own ship' },
  { id: 'polar', label: 'Polar', hint: 'Antarctic polar stereographic' },
];

export function ProjectionSwitcher(): JSX.Element {
  const projection = useUiStore((state) => state.projection);
  const setProjection = useUiStore((state) => state.setProjection);

  return (
    <div className="flex overflow-hidden rounded-sm border border-aurora-border">
      {PRESETS.map((preset) => {
        const active = preset.id === projection;

        return (
          <button
            key={preset.id}
            type="button"
            title={preset.hint}
            aria-pressed={active}
            onClick={() => setProjection(preset.id)}
            className={`px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors ${
              active
                ? 'bg-aurora-accent/15 text-aurora-accent'
                : 'text-aurora-muted hover:text-aurora-text'
            }`}
          >
            {preset.label}
          </button>
        );
      })}
    </div>
  );
}
