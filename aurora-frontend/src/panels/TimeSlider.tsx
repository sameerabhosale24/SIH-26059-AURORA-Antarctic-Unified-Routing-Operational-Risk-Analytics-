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

export function TimeSlider({ className = '' }: { className?: string }): JSX.Element {
  const horizon = useSicStore((state) => state.selectedHorizon);
  const setHorizon = useSicStore((state) => state.setHorizon);
  const manifest = useSicStore((state) => state.data);
  const error = useSicStore((state) => state.error);

  // `selectedFrame` reads the horizon and the manifest together, so it takes
  // the whole store slice rather than two independently-subscribed values.
  const frame = selectedFrame({ data: manifest, selectedHorizon: horizon });

  return (
    <Panel className={className} title="Forecast horizon">
      <input
        type="range"
        min={MIN}
        max={MAX}
        step={1}
        value={horizon}
        onChange={(event) => setHorizon(toHorizon(Number(event.target.value)))}
        className="h-1 w-full cursor-pointer accent-aurora-accent"
        aria-label="Forecast horizon in days"
        aria-valuetext={`Day plus ${horizon}`}
      />

      <div className="mt-1 flex justify-between text-[10px] text-aurora-muted">
        {STEP_LABELS.map((step) => (
          <button
            key={step.horizon}
            type="button"
            onClick={() => setHorizon(step.horizon)}
            className={
              step.horizon === horizon
                ? 'font-semibold text-aurora-accent'
                : 'transition-colors hover:text-aurora-text'
            }
          >
            {step.label}
          </button>
        ))}
      </div>

      <p className="mt-2 font-mono text-[11px] text-aurora-text">
        {frame ? `Frame ${fmtDate(frame.date)} · D+${frame.horizon}` : 'No frame published'}
      </p>

      {error ? <p className="mt-1 text-[10px] text-aurora-warn">{error}</p> : null}
    </Panel>
  );
}
