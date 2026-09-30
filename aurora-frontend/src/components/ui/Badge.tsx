/**
 * Status badge.
 *
 * Colours map onto the bridge convention already used by the map: green
 * nominal, amber degraded or stale, red failed. The text stays visible in
 * every tone — a badge an operator has to hover to read is not a badge.
 */
import type { ReactNode } from 'react';

export type BadgeTone = 'ok' | 'warn' | 'crit' | 'muted' | 'accent';

const TONE_CLASS: Record<BadgeTone, string> = {
  ok: 'border-aurora-ok/40 bg-aurora-ok/10 text-aurora-ok',
  warn: 'border-aurora-warn/40 bg-aurora-warn/10 text-aurora-warn',
  crit: 'border-aurora-crit/50 bg-aurora-crit/15 text-aurora-crit',
  muted: 'border-aurora-border bg-aurora-bg/60 text-aurora-muted',
  accent: 'border-aurora-accent/40 bg-aurora-accent/10 text-aurora-accent',
};

export interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
}

export function Badge({ tone = 'muted', children }: BadgeProps): JSX.Element {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-[10px] font-medium uppercase tracking-[0.12em] ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}
