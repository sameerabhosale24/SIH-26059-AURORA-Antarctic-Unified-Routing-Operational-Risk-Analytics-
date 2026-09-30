/**
 * Conning panel — own-ship instruments and the metocean immediately around it.
 *
 * Two sources are read side by side on purpose: the vessel stream carries the
 * ship's own sensors, the weather stream carries the environment at the ship.
 * They have different cadences (1 Hz vs 5 min) and different staleness
 * thresholds, so each value is qualified by its own source's badge rather than
 * one blanket "live" flag.
 *
 * Every null renders as `—`. A zero is a real measurement: a boat stopped in
 * ice reads `0.0` knots and must not be mistaken for "no data".
 */
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel } from '@/components/ui/Panel';
import { Stat, StatGroup } from '@/components/ui/Stat';
import { useStaleness } from '@/hooks/useStaleness';
import { useVesselStore } from '@/stores/vesselStore';
import { useWeatherStore } from '@/stores/weatherStore';
import { EM_DASH, fmtBearing, fmtNum, fmtSigned } from '@/utils/formatting';
import type { StatTone } from '@/components/ui/Stat';

/** Below this under-keel clearance the reading is flagged, not hidden. */
const UKC_WARN_METRES = 2;

function ukcTone(ukc: number | null): StatTone {
  if (ukc === null) return 'default';
  if (ukc < UKC_WARN_METRES) return 'crit';
  if (ukc < UKC_WARN_METRES * 1.5) return 'warn';
  return 'ok';
}

function SourceFlag({ source }: { source: 'GPS' | 'weather' }): JSX.Element {
  const state = useStaleness(source);

  if (state.isMissing) return <Badge tone="crit">No data</Badge>;
  if (state.isStale) return <Badge tone="warn">Stale</Badge>;
  return <Badge tone="ok">Live</Badge>;
}

export function ConningPanel({ className = '' }: { className?: string }): JSX.Element {
  const vessel = useVesselStore((state) => state.data);
  const weather = useWeatherStore((state) => state.data);

  return (
    <Panel className={className}
      title="Own ship"
      action={
        <div className="flex items-center gap-1.5">
          <SourceFlag source="GPS" />
          <SourceFlag source="weather" />
        </div>
      }
    >
      {vessel === null ? (
        <EmptyState
          message="No own-ship data"
          hint="Awaiting the vessel stream on WS /ws/vessel"
        />
      ) : (
        <>
          <StatGroup>
            <Stat label="SOG" value={fmtNum(vessel.sog, 1)} unit="kn" />
            <Stat label="COG" value={fmtBearing(vessel.cog)} />
            <Stat label="HDG" value={fmtBearing(vessel.heading)} />
            <Stat label="ROT" value={fmtSigned(vessel.rot, 1)} unit="°/min" />
            <Stat label="Draught" value={fmtNum(vessel.draft, 1)} unit="m" />
            <Stat label="UKC" value={fmtNum(vessel.ukc, 1)} unit="m" tone={ukcTone(vessel.ukc)} />
            <Stat label="Fuel" value={fmtNum(vessel.fuel_remaining, 0)} unit="t" />
            <Stat label="Engine" value={fmtNum(vessel.engine_load, 0)} unit="%" />
            <Stat label="Ship wind" value={fmtNum(vessel.wind_speed, 1)} unit="m/s" />
            <Stat label="Ship wind dir" value={fmtBearing(vessel.wind_dir)} />
          </StatGroup>

          <div className="mt-3 border-t border-aurora-border/60 pt-2">
            <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-aurora-muted">
              Metocean
            </p>

            {weather === null ? (
              <EmptyState
                message="No metocean data"
                hint="Awaiting the weather stream on WS /ws/weather"
              />
            ) : (
              <StatGroup>
                <Stat label="Wind" value={fmtNum(weather.wind_speed, 1)} unit="m/s" />
                <Stat label="Wind dir" value={fmtBearing(weather.wind_dir)} />
                <Stat label="Wave Hs" value={fmtNum(weather.wave_height, 1)} unit="m" />
                <Stat label="Wave dir" value={fmtBearing(weather.wave_dir)} />
                <Stat label="Current" value={fmtNum(weather.current_speed, 2)} />
                <Stat label="Current dir" value={fmtBearing(weather.current_dir)} />
                <Stat label="Air temp" value={fmtNum(weather.air_temp, 1)} unit="°C" />
                <Stat label="Source" value={weather.source || EM_DASH} tone="muted" />
              </StatGroup>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
