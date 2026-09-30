/**
 * Forecast table — per-waypoint conditions along the recommended route.
 *
 * Rows are built from the backend's own waypoints, and the ice column is
 * derived from real iceberg positions by great-circle proximity. SIC, wind and
 * wave columns are rendered as `—` because no endpoint returns a per-waypoint
 * forecast for them: the two grid products are raster frames keyed by horizon
 * and metocean is a single point at the vessel. Fabricating an interpolation
 * would put a number on the chart that no model produced, so the gap is shown
 * as a gap and called out in the footnote.
 */
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel } from '@/components/ui/Panel';
import { useIcebergStore } from '@/stores/icebergStore';
import { useRouteStore } from '@/stores/routeStore';
import type { Route, Waypoint } from '@/types/route';
import { EM_DASH, fmtTime } from '@/utils/formatting';
import { haversineNm } from '@/utils/geo';

/** Closest iceberg inside this radius is reported for the waypoint. */
const ICE_PROXIMITY_NM = 100;

interface Row {
  waypoint: Waypoint;
  icebergId: string | null;
  icebergNm: number | null;
}

function nearestIceberg(
  lat: number,
  lon: number,
  icebergs: ReadonlyArray<{ id: string; lat: number; lon: number }> | null,
): { id: string; nm: number } | null {
  if (!icebergs || icebergs.length === 0) return null;

  let best: { id: string; nm: number } | null = null;

  for (const iceberg of icebergs) {
    const nm = haversineNm(lat, lon, iceberg.lat, iceberg.lon);
    if (best === null || nm < best.nm) best = { id: iceberg.id, nm };
  }

  return best && best.nm <= ICE_PROXIMITY_NM ? best : null;
}

function buildRows(route: Route, icebergs: IcebergLike[] | null): Row[] {
  return route.waypoints.map((waypoint) => {
    const nearest = nearestIceberg(waypoint.lat, waypoint.lon, icebergs);
    return {
      waypoint,
      icebergId: nearest ? nearest.id : null,
      icebergNm: nearest ? nearest.nm : null,
    };
  });
}

/** Minimal view of the iceberg store's payload, so this panel owns no imports. */
interface IcebergLike {
  id: string;
  lat: number;
  lon: number;
}

function IceCell({ row }: { row: Row }): JSX.Element {
  if (row.icebergNm === null || row.icebergId === null) {
    return <span className="font-mono text-aurora-muted">{EM_DASH}</span>;
  }

  return (
    <span className="font-mono text-aurora-warn" title={`Iceberg ${row.icebergId}`}>
      {row.icebergNm.toFixed(1)} nm
    </span>
  );
}

export function ForecastTable({ className = '' }: { className?: string }): JSX.Element {
  const run = useRouteStore((state) => state.data);
  const icebergs = useIcebergStore((state) => state.data);

  const route = run?.routes.find((candidate) => candidate.is_recommended) ?? null;

  if (!route) {
    return (
      <Panel className={className} title="Forecast">
        <EmptyState
          message="No recommended route"
          hint="The forecast table is keyed to the recommended route's waypoints"
        />
      </Panel>
    );
  }

  const rows = buildRows(route, icebergs);

  if (rows.length === 0) {
    return (
      <Panel className={className} title="Forecast">
        <EmptyState message="Recommended route has no waypoints" />
      </Panel>
    );
  }

  return (
    <Panel className={className}
      title="Forecast"
      action={<span className="text-[10px] text-aurora-muted">{rows.length} waypoints</span>}
      bodyClassName="p-0"
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-[11px]">
          <thead className="sticky top-0 bg-aurora-panel">
            <tr className="border-b border-aurora-border text-[10px] uppercase tracking-wide text-aurora-muted">
              <th className="px-3 py-1.5 font-medium">WPT</th>
              <th className="px-3 py-1.5 font-medium">ETA</th>
              <th className="px-3 py-1.5 text-right font-medium">SIC</th>
              <th className="px-3 py-1.5 text-right font-medium">Wind</th>
              <th className="px-3 py-1.5 text-right font-medium">Wave</th>
              <th className="px-3 py-1.5 text-right font-medium">Ice</th>
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => (
              <tr key={row.waypoint.id} className="border-b border-aurora-border/40">
                <td className="px-3 py-1.5">
                  <span className="block truncate text-aurora-text">
                    {row.waypoint.name ?? `WP${row.waypoint.seq}`}
                  </span>
                </td>

                <td className="px-3 py-1.5 font-mono text-aurora-text">
                  {fmtTime(row.waypoint.eta)}
                </td>

                <td className="px-3 py-1.5 text-right font-mono text-aurora-muted">{EM_DASH}</td>
                <td className="px-3 py-1.5 text-right font-mono text-aurora-muted">{EM_DASH}</td>
                <td className="px-3 py-1.5 text-right font-mono text-aurora-muted">{EM_DASH}</td>

                <td className="px-3 py-1.5 text-right">
                  <IceCell row={row} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="border-t border-aurora-border px-3 py-1.5 text-[10px] leading-snug text-aurora-muted">
        SIC, wind and wave have no per-waypoint endpoint — shown as
        {' —'} rather than interpolated. Ice is nearest reported iceberg within
        100 nm, computed from live positions.
      </p>
    </Panel>
  );
}
