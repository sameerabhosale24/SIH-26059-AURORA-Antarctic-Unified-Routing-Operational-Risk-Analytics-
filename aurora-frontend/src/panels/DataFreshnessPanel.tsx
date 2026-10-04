/**
 * Data-freshness drawer — the truth about every stream, in one place.
 *
 * This is the panel an operator opens when the map looks wrong: it answers
 * "how old is this?" for each source using the same `useStaleness` calculation
 * the status-bar dots use, so the dot and the drawer can never disagree.
 *
 * `isMissing` and `isStale` are distinct states because they need different
 * actions: a missing source is a connectivity problem, a stale source is a
 * producer problem.
 */
import { Badge } from '@/components/ui/Badge';
import { Panel } from '@/components/ui/Panel';
import { STALENESS_THRESHOLDS, type StalenessSource } from '@/config/constants';
import { useStaleness } from '@/hooks/useStaleness';
import { useDataStore } from '@/stores/dataStore';
import { useEncStore } from '@/stores/encStore';
import { useIcebergStore } from '@/stores/icebergStore';
import { useRouteStore } from '@/stores/routeStore';
import { useSicStore } from '@/stores/sicStore';
import { useVesselStore } from '@/stores/vesselStore';
import { useWeatherStore } from '@/stores/weatherStore';
import { EM_DASH, fmtDateTime, fmtDuration } from '@/utils/formatting';

interface SourceRow {
  key: StalenessSource;
  label: string;
  /** Transport error recorded by the owning store, if any. */
  error: string | null;
}

function Row({ row }: { row: SourceRow }): JSX.Element {
  const state = useStaleness(row.key);

  return (
    <div className="border-b border-ocean-800/40 py-2 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-ocean-100">{row.label}</span>

        {state.isMissing ? (
          <Badge tone="crit">No data</Badge>
        ) : state.isStale ? (
          <Badge tone="warn">Stale</Badge>
        ) : (
          <Badge tone="ok">Live</Badge>
        )}
      </div>

      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px]">
        <dt className="text-ocean-300">Age</dt>
        <dd className="text-right font-mono text-ocean-100">
          {state.ageSeconds === null ? EM_DASH : fmtDuration(state.ageSeconds)}
        </dd>

        <dt className="text-ocean-300">Threshold</dt>
        <dd className="text-right font-mono text-ocean-300">
          {fmtDuration(STALENESS_THRESHOLDS[row.key])}
        </dd>

        <dt className="text-ocean-300">Last payload</dt>
        <dd className="text-right font-mono text-ocean-300">
          {state.lastUpdated === null
            ? EM_DASH
            : fmtDateTime(new Date(state.lastUpdated).toISOString())}
        </dd>
      </dl>

      {row.error ? (
        <p className="mt-1 break-words text-[10px] leading-snug text-aurora-warn">{row.error}</p>
      ) : null}
    </div>
  );
}

export function DataFreshnessPanel({ onClose }: { onClose?: () => void }): JSX.Element {
  const apiStatus = useDataStore((state) => state.apiStatus);
  const wsStatus = useDataStore((state) => state.wsStatus);

  const vesselError = useVesselStore((state) => state.error);
  const weatherError = useWeatherStore((state) => state.error);
  const sicError = useSicStore((state) => state.error);
  const icebergError = useIcebergStore((state) => state.error);
  const routeError = useRouteStore((state) => state.error);
  const encError = useEncStore((state) => state.error);

  const rows: SourceRow[] = [
    { key: 'GPS', label: 'Own ship (GPS)', error: vesselError },
    // AIS has no REST call — the stream is the only path, so there is no
    // separate transport error to report beyond the channel badge above.
    { key: 'AIS', label: 'AIS targets', error: null },
    { key: 'weather', label: 'Metocean', error: weatherError },
    { key: 'SIC', label: 'Sea-ice forecast', error: sicError },
    { key: 'icebergs', label: 'Icebergs', error: icebergError },
    { key: 'route', label: 'Route', error: routeError },
    { key: 'enc', label: 'ENC chart', error: encError },
  ];

  return (
    <Panel
      title="Data freshness"
      action={
        onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-ocean-300 transition-colors hover:text-ocean-100"
            aria-label="Close data freshness panel"
          >
            ×
          </button>
        ) : null
      }
      className="shadow-lg shadow-black/40"
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5 border-b border-ocean-800 pb-2">
        <Badge tone={apiStatus === 'ok' ? 'ok' : apiStatus === 'degraded' ? 'warn' : 'crit'}>
          API {apiStatus}
        </Badge>

        {Object.entries(wsStatus).map(([channel, status]) => (
          <Badge
            key={channel}
            tone={status === 'open' ? 'ok' : status === 'error' ? 'crit' : 'muted'}
          >
            {channel} {status}
          </Badge>
        ))}
      </div>

      <div>
        {rows.map((row) => (
          <Row key={row.key} row={row} />
        ))}
      </div>

      <p className="mt-2 text-[10px] leading-snug text-ocean-300">
        Age is measured from when this client last received the payload, not from
        the producer's own timestamp.
      </p>
    </Panel>
  );
}
