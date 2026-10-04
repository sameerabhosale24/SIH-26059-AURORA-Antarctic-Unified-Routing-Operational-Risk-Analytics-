/**
 * Analysis view — Recharts time series over route-run history.
 *
 * The only genuinely time-indexed data the backend publishes per run is the
 * optimiser's own output, so these charts track the recommended route's fuel
 * estimate and risk score across successive runs. That is a real series: each
 * point is one run, stamped with the run's `run_ts`.
 *
 * SIC and under-keel clearance are *not* charted. Neither has a time series
 * anywhere in the API — SIC is a set of discrete horizon frames and UKC is a
 * single latest reading — and plotting them would require inventing samples
 * between publications. The gap is stated on the panel instead.
 */
import { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState } from '@/components/ui/EmptyState';
import { Panel } from '@/components/ui/Panel';
import { VesselGate } from '@/components/VesselGate';
import { useRouteStore } from '@/stores/routeStore';
import type { RouteRun } from '@/types/route';
import { EM_DASH, fmtDate, fmtTime } from '@/utils/formatting';

interface SeriesPoint {
  /** Run stamp, for the axis. */
  ts: string;
  /** Short axis label — day + time so two runs a day apart read apart. */
  label: string;
  fuel: number | null;
  risk: number | null;
  distance: number | null;
}

function recommendedFuel(run: RouteRun): number | null {
  const route = run.routes.find((candidate) => candidate.is_recommended) ?? run.routes[0];
  return route ? route.fuel_estimate_t : null;
}

function recommendedRisk(run: RouteRun): number | null {
  const route = run.routes.find((candidate) => candidate.is_recommended) ?? run.routes[0];
  return route ? route.risk_score * 100 : null;
}

function recommendedDistance(run: RouteRun): number | null {
  const route = run.routes.find((candidate) => candidate.is_recommended) ?? run.routes[0];
  return route ? route.distance_nm : null;
}

/**
 * Build the chart series.
 *
 * Runs arrive newest-first from the API, so they are re-sorted ascending;
 * runs with an unparseable timestamp are dropped rather than plotted at epoch,
 * which would put a bogus point at the far left of the axis.
 */
function buildSeries(history: RouteRun[]): SeriesPoint[] {
  const sorted = [...history].sort((a, b) => Date.parse(a.run_ts) - Date.parse(b.run_ts));

  const points: SeriesPoint[] = [];

  for (const run of sorted) {
    const time = Date.parse(run.run_ts);
    if (Number.isNaN(time)) continue;

    points.push({
      ts: run.run_ts,
      label: `${fmtDate(run.run_ts)} ${fmtTime(run.run_ts).slice(0, 5)}`,
      fuel: recommendedFuel(run),
      risk: recommendedRisk(run),
      distance: recommendedDistance(run),
    });
  }

  return points;
}

const AXIS_TICK = { fontSize: 10, fill: '#8b9bb4' } as const;

const TOOLTIP_CONTENT_STYLE = {
  backgroundColor: '#0b1220',
  border: '1px solid #1e293b',
  borderRadius: 2,
  fontSize: 11,
} as const;

function FuelChart({ points }: { points: SeriesPoint[] }): JSX.Element {
  return (
    <div className="h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="2 3" />
          <XAxis dataKey="label" tick={AXIS_TICK} minTickGap={24} stroke="#334155" />
          <YAxis tick={AXIS_TICK} stroke="#334155" width={44} />
          <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={{ color: '#8b9bb4' }} />

          <Line
            type="monotone"
            dataKey="fuel"
            name="Fuel (t)"
            stroke="#38bdf8"
            strokeWidth={1.5}
            dot={{ r: 2 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function RiskChart({ points }: { points: SeriesPoint[] }): JSX.Element {
  return (
    <div className="h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="2 3" />
          <XAxis dataKey="label" tick={AXIS_TICK} minTickGap={24} stroke="#334155" />
          <YAxis tick={AXIS_TICK} stroke="#334155" width={44} domain={[0, 100]} />
          <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={{ color: '#8b9bb4' }} />

          <Line
            type="monotone"
            dataKey="risk"
            name="Risk (0–100)"
            stroke="#f97316"
            strokeWidth={1.5}
            dot={{ r: 2 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AnalysisView(): JSX.Element {
  return (
    <VesselGate>
      <AnalysisContent />
    </VesselGate>
  );
}

function AnalysisContent(): JSX.Element {
  const history = useRouteStore((state) => state.history);
  const current = useRouteStore((state) => state.data);

  const points = useMemo(
    () => buildSeries(current ? [current, ...history] : history),
    [history, current],
  );

  if (points.length === 0) {
    return (
      <div className="p-2">
        <Panel title="Analysis">
          <EmptyState
            message="No route-run history yet"
            hint="Series are drawn from GET /api/route/history plus the active run"
          />
        </Panel>
      </div>
    );
  }

  const latest = points[points.length - 1];
  const previous = points.length > 1 ? points[points.length - 2] : null;

  // Deltas are only meaningful when both runs actually reported a value —
  // a null on either side means "unknown", and subtracting it would print a
  // number the optimiser never produced.
  const deltaFuel =
    latest && previous && latest.fuel !== null && previous.fuel !== null
      ? latest.fuel - previous.fuel
      : null;
  const deltaRisk =
    latest && previous && latest.risk !== null && previous.risk !== null
      ? latest.risk - previous.risk
      : null;

  return (
    <div className="grid h-full min-h-0 gap-2 overflow-auto p-2 lg:grid-cols-2">
      <Panel title="Fuel estimate, recommended route" className="lg:col-span-1">
        <FuelChart points={points} />

        <div className="mt-2 flex items-baseline justify-between text-[11px]">
          <span className="text-ocean-300">Latest</span>
          <span className="font-mono text-ocean-100">
            {latest?.fuel === null || latest?.fuel === undefined
              ? EM_DASH
              : `${latest.fuel.toFixed(1)} t`}
          </span>

          <span className="text-ocean-300">Δ previous run</span>
          <span
            className={`font-mono ${
              deltaFuel === null ? 'text-ocean-300' : deltaFuel > 0 ? 'text-aurora-warn' : 'text-aurora-ok'
            }`}
          >
            {deltaFuel === null
              ? EM_DASH
              : `${deltaFuel >= 0 ? '+' : ''}${deltaFuel.toFixed(1)} t`}
          </span>
        </div>
      </Panel>

      <Panel title="Risk score, recommended route" className="lg:col-span-1">
        <RiskChart points={points} />

        <div className="mt-2 flex items-baseline justify-between text-[11px]">
          <span className="text-ocean-300">Latest</span>
          <span className="font-mono text-ocean-100">
            {latest?.risk === null || latest?.risk === undefined
              ? EM_DASH
              : latest.risk.toFixed(0)}
          </span>

          <span className="text-ocean-300">Δ previous run</span>
          <span
            className={`font-mono ${
              deltaRisk === null ? 'text-ocean-300' : deltaRisk > 0 ? 'text-aurora-warn' : 'text-aurora-ok'
            }`}
          >
            {deltaRisk === null
              ? EM_DASH
              : `${deltaRisk >= 0 ? '+' : ''}${deltaRisk.toFixed(0)}`}
          </span>
        </div>
      </Panel>

      <Panel title="Not charted" className="lg:col-span-2">
        <p className="text-[11px] leading-relaxed text-ocean-300">
          Sea-ice concentration and under-keel clearance have no time series in
          the API — SIC is published as discrete D+1/D+2/D+3 frames and UKC as a
          single latest reading. Charting either would mean interpolating samples
          the models never produced, so both are left out rather than drawn as
          something they are not.
        </p>
      </Panel>
    </div>
  );
}
