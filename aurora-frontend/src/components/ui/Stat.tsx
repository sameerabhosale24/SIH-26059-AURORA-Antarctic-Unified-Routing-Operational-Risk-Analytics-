/**
 * Label/value row.
 *
 * `value` is already formatted — this component never applies a fallback of
 * its own, so the caller stays responsible for turning `null` into `—`. That
 * keeps the "never render 0 for unknown" rule in one place (`formatting.ts`)
 * rather than scattered through presentation code.
 *
 * `tone` exists because a value can be *present and wrong*: a high wind is
 * still data, and it should be readable as a warning without hiding it.
 */
import type { ReactNode } from 'react';

export type StatTone = 'default' | 'ok' | 'warn' | 'crit' | 'muted';

const TONE_CLASS: Record<StatTone, string> = {
  default: 'text-ocean-100',
  ok: 'text-aurora-ok',
  warn: 'text-aurora-warn',
  crit: 'text-aurora-crit',
  muted: 'text-ocean-300',
};

export interface StatProps {
  label: string;
  value: string;
  unit?: string;
  tone?: StatTone;
}

export function Stat({ label, value, unit, tone = 'default' }: StatProps): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="shrink-0 text-[11px] uppercase tracking-wide text-ocean-300">
        {label}
      </span>

      <span className={`min-w-0 truncate text-right text-sm ${TONE_CLASS[tone]}`}>
        {value}
        {unit ? <span className="ml-1 text-[11px] text-ocean-300">{unit}</span> : null}
      </span>
    </div>
  );
}

export interface StatGroupProps {
  children: ReactNode;
}

/** Vertical stack of {@link Stat} rows with a hairline between entries. */
export function StatGroup({ children }: StatGroupProps): JSX.Element {
  return <div className="divide-y divide-ocean-800/60">{children}</div>;
}
