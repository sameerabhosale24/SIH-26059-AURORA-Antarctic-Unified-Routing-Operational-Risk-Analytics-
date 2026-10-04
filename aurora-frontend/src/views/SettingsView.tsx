/**
 * Settings view — the read-only facts about how this console is wired, plus
 * the two preferences that belong to the operator rather than to a route.
 *
 * Everything here is a *readout*, not an editor: endpoints come from the build
 * environment and thresholds come from `config/constants.ts`. Surfacing them
 * lets someone diagnosing a blank map confirm in one glance that the console
 * is pointed at the backend they think it is, without a source-code search.
 */
import { Badge } from '@/components/ui/Badge';
import { Panel } from '@/components/ui/Panel';
import { Stat, StatGroup } from '@/components/ui/Stat';
import { VesselGate } from '@/components/VesselGate';
import {
  STALENESS_THRESHOLDS,
  UPDATE_CADENCE,
  VERSION_POLL_INTERVAL_MS,
  type StalenessSource,
} from '@/config/constants';
import { API_BASE, WS_BASE } from '@/config/env';
import { LAYERS } from '@/map/layers';
import { EM_DASH, fmtDuration } from '@/utils/formatting';

const SOURCES: readonly StalenessSource[] = [
  'GPS',
  'AIS',
  'weather',
  'SIC',
  'icebergs',
  'route',
  'enc',
];

function EndpointsPanel(): JSX.Element {
  return (
    <Panel title="Endpoints">
      <StatGroup>
        <Stat label="API" value={API_BASE} tone="muted" />
        <Stat label="WebSocket" value={WS_BASE} tone="muted" />
        <Stat label="Version poll" value={fmtDuration(VERSION_POLL_INTERVAL_MS / 1000)} />
      </StatGroup>

      <p className="mt-2 text-[10px] leading-snug text-ocean-300">
        Set at build time from <code className="text-ocean-100">.env</code>; changing
        them requires a rebuild.
      </p>
    </Panel>
  );
}

function ThresholdsPanel(): JSX.Element {
  return (
    <Panel title="Staleness thresholds" bodyClassName="p-0">
      <table className="w-full border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-ocean-800 text-[10px] uppercase tracking-wide text-ocean-300">
            <th className="px-3 py-1.5 font-medium">Source</th>
            <th className="px-3 py-1.5 text-right font-medium">Stale after</th>
          </tr>
        </thead>

        <tbody>
          {SOURCES.map((source) => (
            <tr key={source} className="border-b border-ocean-800/40 last:border-b-0">
              <td className="px-3 py-1.5 text-ocean-100">{source}</td>
              <td className="px-3 py-1.5 text-right font-mono text-ocean-300">
                {fmtDuration(STALENESS_THRESHOLDS[source])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function CadencePanel(): JSX.Element {
  return (
    <Panel title="Producer cadence">
      <StatGroup>
        {Object.entries(UPDATE_CADENCE).map(([key, value]) => (
          <Stat key={key} label={key} value={String(value)} tone="muted" />
        ))}
      </StatGroup>

      <p className="mt-2 text-[10px] leading-snug text-ocean-300">
        Expected intervals as documented by the backend. Actual arrival is
        measured separately and shown in Data freshness.
      </p>
    </Panel>
  );
}

function LayerDefaultsPanel({ className = '' }: { className?: string }): JSX.Element {
  return (
    <Panel className={className} title="Layer defaults" bodyClassName="p-0">
      <table className="w-full border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-ocean-800 text-[10px] uppercase tracking-wide text-ocean-300">
            <th className="px-3 py-1.5 font-medium">Layer</th>
            <th className="px-3 py-1.5 text-right font-medium">Visible</th>
            <th className="px-3 py-1.5 text-right font-medium">Opacity</th>
            <th className="px-3 py-1.5 text-right font-medium">Stale by</th>
          </tr>
        </thead>

        <tbody>
          {LAYERS.map((layer) => (
            <tr key={layer.id} className="border-b border-ocean-800/40 last:border-b-0">
              <td className="px-3 py-1.5 text-ocean-100">{layer.title}</td>

              <td className="px-3 py-1.5 text-right">
                {layer.defaultVisible ? (
                  <Badge tone="ok">On</Badge>
                ) : (
                  <Badge tone="muted">Off</Badge>
                )}
              </td>

              <td className="px-3 py-1.5 text-right font-mono text-ocean-300">
                {Math.round(layer.defaultOpacity * 100)}%
              </td>

              <td className="px-3 py-1.5 text-right font-mono text-ocean-300">
                {layer.stalenessKey ?? EM_DASH}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

export function SettingsView(): JSX.Element {
  return (
    <VesselGate>
      <div className="grid h-full min-h-0 gap-2 overflow-auto p-2 lg:grid-cols-2">
        <EndpointsPanel />
        <ThresholdsPanel />
        <CadencePanel />
        <LayerDefaultsPanel className="lg:col-span-2" />
      </div>
    </VesselGate>
  );
}
