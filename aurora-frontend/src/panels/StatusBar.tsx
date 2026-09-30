/**
 * Status bar — the always-visible strip along the top of the console.
 *
 * Carries, left to right: identity, own-ship position, the UTC clock, and one
 * health dot per data source. Every dot is derived from `useStaleness`, so the
 * strip and the freshness drawer can never disagree about a source.
 *
 * `NO GPS` is shown once the own-ship stream is older than
 * `STALENESS_THRESHOLDS.GPS` — the single most important fact on the bar,
 * because everything else on the display is referenced to that position.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { STALENESS_THRESHOLDS, type StalenessSource } from '@/config/constants';
import { DISPLAY_MODES } from '@/config/palettes';
import { useDataStore, aggregateWsStatus } from '@/stores/dataStore';
import { useShipsStore } from '@/stores/shipsStore';
import { useUiStore } from '@/stores/uiStore';
import { useUserStore } from '@/stores/userStore';
import { useVesselStore } from '@/stores/vesselStore';
import { useStaleness } from '@/hooks/useStaleness';
import { EM_DASH, fmtBearing, fmtPosition } from '@/utils/formatting';
import { Badge } from '@/components/ui/Badge';

/** Sources shown as a dot, in reading order. */
const SOURCES: ReadonlyArray<{ key: StalenessSource; label: string }> = [
  { key: 'GPS', label: 'GPS' },
  { key: 'AIS', label: 'AIS' },
  { key: 'weather', label: 'WX' },
  { key: 'SIC', label: 'SIC' },
  { key: 'icebergs', label: 'ICE' },
  { key: 'route', label: 'ROUTE' },
  { key: 'enc', label: 'ENC' },
];

type DotTone = 'ok' | 'warn' | 'crit';

function dotClass(tone: DotTone): string {
  return tone === 'ok'
    ? 'bg-aurora-ok'
    : tone === 'warn'
      ? 'bg-aurora-warn'
      : 'bg-aurora-crit';
}

function dotTitle(label: string, missing: boolean, stale: boolean, age: number | null): string {
  if (missing) return `${label}: no data received`;
  if (stale) return `${label}: stale`;
  return age === null ? `${label}: live` : `${label}: live, updated recently`;
}

function SourceDot({ label, state }: { label: string; state: StalenessResult }): JSX.Element {
  const tone: DotTone = state.isMissing ? 'crit' : state.isStale ? 'warn' : 'ok';

  return (
    <span
      className={`h-2 w-2 shrink-0 rounded-full ${dotClass(tone)}`}
      title={dotTitle(label, state.isMissing, state.isStale, state.ageSeconds)}
      role="img"
      aria-label={dotTitle(label, state.isMissing, state.isStale, state.ageSeconds)}
    />
  );
}

/** Local alias so the seven hook calls below stay readable. */
type StalenessResult = ReturnType<typeof useStaleness>;

function useUtcClock(): string {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(id);
  }, []);

  return new Date(now).toISOString().slice(11, 19);
}

/**
 * Day / Dusk / Night.
 *
 * In the status bar rather than only in Settings because it is a *viewing*
 * choice — an operator changes it when the bridge lighting changes, which is
 * not a settings visit — and because the effect it has on the chart has to be
 * visible at the same moment as the control.
 */
function DisplayModeSwitch(): JSX.Element {
  const displayMode = useUiStore((state) => state.displayMode);
  const setDisplayMode = useUiStore((state) => state.setDisplayMode);

  return (
    <div className="flex shrink-0 overflow-hidden rounded-sm border border-aurora-border">
      {DISPLAY_MODES.map((mode) => (
        <button
          key={mode}
          type="button"
          aria-pressed={mode === displayMode}
          onClick={() => setDisplayMode(mode)}
          className={`px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] transition-colors ${
            mode === displayMode
              ? 'bg-aurora-accent/15 text-aurora-accent'
              : 'text-aurora-muted hover:text-aurora-text'
          }`}
        >
          {mode}
        </button>
      ))}
    </div>
  );
}

/**
 * Signed-in operator and the way out.
 *
 * Sign-out is deliberate and local: the fleet cache is dropped in the same
 * action so the next person to use this console starts from their own ships
 * rather than glancing at ours.
 */
function SessionControl(): JSX.Element | null {
  const navigate = useNavigate();

  const user = useUserStore((state) => state.user);
  const signOut = useUserStore((state) => state.signOut);

  if (user === null) return null;

  async function handleSignOut(): Promise<void> {
    await signOut();
    useShipsStore.getState().reset();
    useVesselStore.getState().clearVessel();
    navigate('/login', { replace: true });
  }

  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="hidden max-w-[12rem] truncate text-[11px] text-aurora-muted lg:inline">
        {user.email}
      </span>

      <button
        type="button"
        title="End this session on this browser"
        onClick={() => {
          void handleSignOut();
        }}
        className="rounded-sm border border-aurora-border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-aurora-muted transition-colors hover:border-aurora-crit/50 hover:text-aurora-crit"
      >
        Sign out
      </button>
    </div>
  );
}

export function StatusBar(): JSX.Element {
  const clock = useUtcClock();

  const vessel = useVesselStore((state) => state.data);
  const vesselUpdated = useVesselStore((state) => state.lastUpdated);
  const blueprint = useVesselStore((state) => state.blueprint);

  const apiStatus = useDataStore((state) => state.apiStatus);
  const wsStatus = useDataStore((state) => aggregateWsStatus(state.wsStatus));

  const gps = useStaleness('GPS');
  const ais = useStaleness('AIS');
  const weather = useStaleness('weather');
  const sic = useStaleness('SIC');
  const icebergs = useStaleness('icebergs');
  const route = useStaleness('route');
  const enc = useStaleness('enc');

  const states: Record<StalenessSource, StalenessResult> = {
    GPS: gps,
    AIS: ais,
    weather,
    SIC: sic,
    icebergs,
    route,
    enc,
  };

  // The position is only trustworthy while it is moving through the pipeline.
  const noGps =
    vessel === null ||
    vesselUpdated === null ||
    Date.now() - vesselUpdated > STALENESS_THRESHOLDS.GPS * 1000;

  const position = vessel ? fmtPosition(vessel.lat, vessel.lon) : EM_DASH;
  const heading = vessel ? fmtBearing(vessel.heading) : EM_DASH;

  return (
    <header className="h-10 shrink-0 border-b border-aurora-border bg-aurora-panel">
      <div className="flex h-full items-center gap-3 overflow-x-auto px-3">
        <span className="shrink-0 text-sm font-semibold tracking-[0.3em] text-aurora-accent">
          AURORA
        </span>

        <span
          className="hidden shrink-0 text-xs text-aurora-text sm:inline"
          title={blueprint ? `IMO ${blueprint.imo}` : undefined}
        >
          {blueprint ? blueprint.name : null}
          {blueprint && vessel ? <span className="text-aurora-muted"> · {vessel.vessel_id}</span> : null}
        </span>

        <span className="shrink-0 font-mono text-xs text-aurora-text">{position}</span>

        <span className="hidden shrink-0 font-mono text-xs text-aurora-muted md:inline">
          HDG {heading}
        </span>

        {noGps ? <Badge tone="crit">No GPS</Badge> : null}

        <div className="ml-auto flex shrink-0 items-center gap-3">
          <DisplayModeSwitch />

          <div className="flex items-center gap-2" title="Data source health">
            {SOURCES.map((source) => (
              <SourceDot key={source.key} label={source.label} state={states[source.key]} />
            ))}
          </div>

          <Badge tone={apiStatus === 'ok' ? 'ok' : apiStatus === 'degraded' ? 'warn' : 'crit'}>
            API {apiStatus}
          </Badge>

          <Badge tone={wsStatus === 'open' ? 'ok' : wsStatus === 'error' ? 'crit' : 'muted'}>
            WS {wsStatus}
          </Badge>

          <span className="font-mono text-xs text-aurora-text">{clock}Z</span>

          <SessionControl />
        </div>
      </div>
    </header>
  );
}
