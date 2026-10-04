/**
 * Time slider — selects which sea-ice forecast horizon is on the map.
 *
 * The backend publishes frames at D+1, D+2 and D+3; the slider steps between
 * those three and the SIC layer resolves the newest frame at that horizon. It
 * is deliberately not a continuous scrubber: there is no data between the
 * published horizons, and a control that can land between frames invites the
 * operator to read a position off a frame that does not exist.
 */
import { Panel } from '@/components/ui/Panel';
import { useSicStore, type SicHorizon } from '@/stores/sicStore';
import { selectedFrame } from '@/map/layers/sic/sicSource';
import type { SicFrameMeta } from '@/types/sic';
import { fmtDate } from '@/utils/formatting';

const MIN: SicHorizon = 1;
const MAX: SicHorizon = 3;

function toHorizon(value: number): SicHorizon {
  if (value <= 1) return 1;
  if (value >= 3) return 3;
  return Math.round(value) as SicHorizon;
}

const STEP_LABELS: ReadonlyArray<{ horizon: SicHorizon; label: string }> = [
  { horizon: 1, label: 'D+1' },
  { horizon: 2, label: 'D+2' },
  { horizon: 3, label: 'D+3' },
];

/**
 * The frame's day in plain words: `Today` for an issue dated today (UTC), so
 * an operator reads the date and its meaning in one glance.
 */
function dayLabel(isoDate: string): string {
  const today = new Date().toISOString().slice(0, 10);
  if (isoDate === today) return 'Today';
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
  if (isoDate === tomorrow) return 'Tomorrow';
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString('en-GB', {
    weekday: 'short',
    timeZone: 'UTC',
  });
}

export function TimeSlider({ className = '' }: { className?: string }): JSX.Element {
  const horizon = useSicStore((state) => state.selectedHorizon);
  const setHorizon = useSicStore((state) => state.setHorizon);
  const manifest = useSicStore((state) => state.data);
  const error = useSicStore((state) => state.error);

  // `selectedFrame` reads the horizon and the manifest together, so it takes
  // the whole store slice rather than two independently-subscribed values.
  const frame = selectedFrame({ data: manifest, selectedHorizon: horizon });

  // The empty-manifest case is the only one that says "no frame published":
  // as long as the backend published *something*, the panel names the day the
  // map is drawing rather than claiming there is nothing to show.
  const shown =
    frame ??
    (manifest?.frames.reduce<SicFrameMeta | null>(
      (newest, candidate) => (newest === null || candidate.date > newest.date ? candidate : newest),
      null,
    ) ??
      null);

  return (
    <Panel className={className} title="Forecast horizon">
      <input
        type="range"
        min={MIN}
        max={MAX}
        step={1}
        value={horizon}
        onChange={(event) => setHorizon(toHorizon(Number(event.target.value)))}
        className="h-1 w-full cursor-pointer accent-ocean-400"
        aria-label="Forecast horizon in days"
        aria-valuetext={`Day plus ${horizon}`}
      />

      <div className="mt-1 flex justify-between text-[10px] text-ocean-300">
        {STEP_LABELS.map((step) => (
          <button
            key={step.horizon}
            type="button"
            onClick={() => setHorizon(step.horizon)}
            className={
              step.horizon === horizon
                ? 'font-semibold text-ocean-400'
                : 'transition-colors hover:text-ocean-100'
            }
          >
            {step.label}
          </button>
        ))}
      </div>

      <p className="mt-2 font-mono text-[11px] text-ocean-100">
        {shown
          ? `Valid for: ${fmtDate(shown.date)} (${dayLabel(shown.date)}) · D+${shown.horizon}`
          : 'No frame published'}
      </p>

      {error ? <p className="mt-1 text-[10px] text-aurora-warn">{error}</p> : null}
    </Panel>
  );
}
