/**
 * Alarm panel — the operator's queue of active alarms.
 *
 * Ordering comes from `alarmStore.add`, which sorts by severity then time, so
 * this component never re-sorts: a list that re-ordered itself while an
 * operator was reading it would be actively dangerous.
 *
 * Acknowledgement is optimistic — the row clears the moment the button is
 * pressed — but the authoritative record comes back from the API, and a failed
 * ack restores the row and raises a toast rather than silently leaving the
 * operator believing they had handled it.
 */
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel } from '@/components/ui/Panel';
import { ackAlarm } from '@/services/api';
import { useAlarmStore } from '@/stores/alarmStore';
import { notify } from '@/stores/toastStore';
import type { Alarm } from '@/types/alarm';
import { EM_DASH, fmtPosition, fmtTime } from '@/utils/formatting';

/** How long a newly arrived alarm keeps its arrival highlight. */
const PULSE_MS = 3_000;

const SEVERITY_TONE: Record<Alarm['severity'], 'crit' | 'warn' | 'accent'> = {
  critical: 'crit',
  warning: 'warn',
  caution: 'accent',
};

const SEVERITY_BAR: Record<Alarm['severity'], string> = {
  critical: 'border-l-aurora-crit',
  warning: 'border-l-aurora-warn',
  caution: 'border-l-aurora-accent',
};

/** Human label for the machine `type` union. */
const TYPE_LABEL: Record<Alarm['type'], string> = {
  ukc: 'Under-keel clearance',
  collision: 'Collision risk',
  ice: 'Ice',
  iceberg: 'Iceberg',
  off_course: 'Off course',
  forecast_stale: 'Forecast stale',
};

function AlarmRow({ alarm, pulsing }: { alarm: Alarm; pulsing: boolean }): JSX.Element {
  const ackLocal = useAlarmStore((state) => state.ackLocal);
  const [pending, setPending] = useState(false);

  const acked = alarm.acked_at !== null;
  const hasPosition = alarm.lat !== null && alarm.lon !== null;

  async function handleAck(): Promise<void> {
    if (acked || pending) return;

    setPending(true);
    ackLocal(alarm.id);

    try {
      const updated = await ackAlarm(alarm.id, 'console');
      useAlarmStore.getState().add(updated);
      notify('Alarm acknowledged', 'success', TYPE_LABEL[alarm.type]);
    } catch (cause) {
      // Restore the un-acked state so the queue is truthful again.
      useAlarmStore.getState().add({ ...alarm, acked_at: null, acked_by: null });
      notify('Ack failed', 'error', cause instanceof Error ? cause.message : String(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <li
      className={`border-l-2 bg-aurora-bg/40 px-2 py-1.5 transition-colors ${SEVERITY_BAR[alarm.severity]} ${
        pulsing ? 'animate-pulse' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={SEVERITY_TONE[alarm.severity]}>{alarm.severity}</Badge>
            <span className="truncate text-[11px] uppercase tracking-wide text-aurora-muted">
              {TYPE_LABEL[alarm.type] ?? alarm.type}
            </span>
            <span className="font-mono text-[10px] text-aurora-muted">{fmtTime(alarm.ts)}</span>
          </div>

          <p className="mt-1 text-xs leading-snug text-aurora-text">{alarm.message}</p>

          <p className="mt-0.5 font-mono text-[10px] text-aurora-muted">
            {hasPosition ? fmtPosition(alarm.lat, alarm.lon) : EM_DASH}
          </p>
        </div>

        <button
          type="button"
          onClick={() => void handleAck()}
          disabled={acked || pending}
          className={`shrink-0 rounded-sm border px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors ${
            acked
              ? 'cursor-default border-aurora-border text-aurora-muted/60'
              : 'border-aurora-border text-aurora-text hover:border-aurora-accent hover:text-aurora-accent'
          }`}
        >
          {acked ? 'Acked' : 'Ack'}
        </button>
      </div>
    </li>
  );
}

export function AlarmPanel({ className = '' }: { className?: string }): JSX.Element {
  const alarms = useAlarmStore((state) => state.data);
  const newestId = useAlarmStore((state) => state.newestId);

  const [pulsingId, setPulsingId] = useState<number | null>(null);

  useEffect(() => {
    if (newestId === null) return;

    setPulsingId(newestId);
    const id = window.setTimeout(() => setPulsingId(null), PULSE_MS);
    return () => window.clearTimeout(id);
  }, [newestId]);

  const list = alarms ?? [];
  const active = list.filter((alarm) => alarm.acked_at === null);

  return (
    <Panel className={className}
      title="Alarms"
      action={
        active.length > 0 ? (
          <Badge tone="crit">{active.length} active</Badge>
        ) : (
          <Badge tone="ok">Clear</Badge>
        )
      }
    >
      {list.length === 0 ? (
        <EmptyState
          message="No active alarms"
          hint="Awaiting the alarm stream on WS /ws/alarms"
        />
      ) : (
        <ul className="flex flex-col gap-1.5">
          {list.map((alarm) => (
            <AlarmRow key={alarm.id} alarm={alarm} pulsing={alarm.id === pulsingId} />
          ))}
        </ul>
      )}
    </Panel>
  );
}
