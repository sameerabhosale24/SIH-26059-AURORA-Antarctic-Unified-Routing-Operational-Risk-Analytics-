/**
 * Route panel — candidate comparison and the AI recommendation.
 *
 * Everything shown here comes from the backend's `RouteRun`: the frontend does
 * not rank, filter or re-score routes. `is_recommended` is the only claim of
 * optimality on the display, and the table shows the inputs behind it so an
 * operator can disagree with the machine on evidence rather than on trust.
 *
 * When no run exists the panel says so — there is no "best guess" route to
 * fall back on, because a fabricated optimum is worse than an empty panel.
 */
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel } from '@/components/ui/Panel';
import { useRouteStore } from '@/stores/routeStore';
import type { Route, RouteRun } from '@/types/route';
import { EM_DASH, fmtDateTime, fmtNum, fmtTime } from '@/utils/formatting';

const STATUS_TONE: Record<RouteRun['status'], 'ok' | 'warn' | 'crit'> = {
  optimal: 'ok',
  degraded: 'warn',
  infeasible: 'crit',
};

const STATUS_LABEL: Record<RouteRun['status'], string> = {
  optimal: 'Optimal',
  degraded: 'Degraded',
  infeasible: 'Infeasible',
};

/** Risk is normalised 0..1; higher is worse. */
function riskTone(risk: number): 'ok' | 'warn' | 'crit' {
  if (risk >= 0.66) return 'crit';
  if (risk >= 0.33) return 'warn';
  return 'ok';
}

function Recommendation({ routes }: { routes: Route[] }): JSX.Element | null {
  const recommended = routes.find((route) => route.is_recommended) ?? null;

  if (!recommended) {
    return (
      <div className="mb-2 rounded-sm border border-aurora-warn/40 bg-aurora-warn/10 px-2 py-1.5 text-[11px] leading-snug text-aurora-warn">
        No route is marked recommended — compare the candidates below before
        committing.
      </div>
    );
  }

  const alternatives = routes.filter((route) => route.id !== recommended.id);
  const closest = alternatives.length
    ? Math.min(...alternatives.map((route) => route.risk_score))
    : null;

  return (
    <div className="mb-2 rounded-sm border border-ocean-400/40 bg-ocean-400/10 px-2 py-1.5">
      <div className="flex items-center gap-2">
        <Badge tone="accent">AI recommended</Badge>
        <span className="truncate text-xs text-ocean-100">{recommended.label}</span>
      </div>

      <p className="mt-1 text-[11px] leading-snug text-ocean-300">
        {fmtNum(recommended.distance_nm, 1)} nm · {fmtNum(recommended.fuel_estimate_t, 1)} t ·
        risk {fmtNum(recommended.risk_score * 100, 0)}
        {closest === null ? '' : ` (best alternative ${fmtNum(closest * 100, 0)})`}
      </p>
    </div>
  );
}

function RouteTable({ routes }: { routes: Route[] }): JSX.Element {
  if (routes.length === 0) {
    return <EmptyState message="No candidate routes in this run" />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-ocean-800 text-[10px] uppercase tracking-wide text-ocean-300">
            <th className="py-1 pr-2 font-medium">Route</th>
            <th className="py-1 pr-2 text-right font-medium">Dist</th>
            <th className="py-1 pr-2 text-right font-medium">ETA</th>
            <th className="py-1 pr-2 text-right font-medium">Fuel</th>
            <th className="py-1 text-right font-medium">Risk</th>
          </tr>
        </thead>

        <tbody>
          {routes.map((route) => (
            <tr
              key={route.id}
              className={`border-b border-ocean-800/40 ${
                route.is_recommended ? 'bg-ocean-400/5' : ''
              }`}
            >
              <td className="max-w-[9rem] py-1 pr-2">
                <span className="block truncate text-ocean-100">{route.label}</span>
                {route.is_recommended ? (
                  <span className="text-[10px] uppercase tracking-wide text-ocean-400">
                    recommended
                  </span>
                ) : null}
              </td>

              <td className="py-1 pr-2 text-right font-mono text-ocean-100">
                {fmtNum(route.distance_nm, 1)}
              </td>

              <td className="py-1 pr-2 text-right font-mono text-ocean-100">
                {fmtTime(route.eta)}
              </td>

              <td className="py-1 pr-2 text-right font-mono text-ocean-100">
                {fmtNum(route.fuel_estimate_t, 1)}
              </td>

              <td
                className={`py-1 text-right font-mono ${
                  riskTone(route.risk_score) === 'crit'
                    ? 'text-aurora-crit'
                    : riskTone(route.risk_score) === 'warn'
                      ? 'text-aurora-warn'
                      : 'text-aurora-ok'
                }`}
              >
                {fmtNum(route.risk_score * 100, 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RoutePanel({ className = '' }: { className?: string }): JSX.Element {
  const run = useRouteStore((state) => state.data);
  const error = useRouteStore((state) => state.error);

  if (run === null) {
    return (
      <Panel className={className} title="Route">
        <EmptyState
          message="No route has been computed"
          hint={error ? `Last attempt failed: ${error}` : 'Awaiting WS /ws/route or GET /api/route/current'}
        />
      </Panel>
    );
  }

  const worst = run.routes.length
    ? Math.max(...run.routes.map((route) => route.risk_score))
    : null;

  return (
    <Panel className={className}
      title="Route"
      action={<Badge tone={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</Badge>}
    >
      <div className="mb-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
        <span className="text-ocean-300">Run</span>
        <span className="text-right font-mono text-ocean-100">{fmtDateTime(run.run_ts)}</span>

        <span className="text-ocean-300">Vessel</span>
        <span className="truncate text-right text-ocean-100">{run.vessel_id}</span>

        <span className="text-ocean-300">Candidates</span>
        <span className="text-right font-mono text-ocean-100">{run.routes.length}</span>

        <span className="text-ocean-300">Peak risk</span>
        <span className="text-right font-mono text-ocean-100">
          {worst === null ? EM_DASH : fmtNum(worst * 100, 0)}
        </span>
      </div>

      <Recommendation routes={run.routes} />
      <RouteTable routes={run.routes} />

      <p className="mt-2 text-[10px] leading-snug text-ocean-300">
        Distance nm · fuel t · risk % (0 best, 100 worst). Ranking is the
        backend's; the console displays it without modification.
      </p>
    </Panel>
  );
}
