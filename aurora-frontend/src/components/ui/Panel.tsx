/**
 * Panel shell used by every side panel.
 *
 * One shape for the whole console so an operator learns the affordance once:
 * a caption row with an optional trailing control, then a scrollable body.
 * Panels are sized by their container, never by their content, so a long
 * alarm list scrolls inside its frame instead of pushing the map around.
 */
import type { ReactNode } from 'react';

export interface PanelProps {
  title: string;
  /** Rendered at the trailing edge of the caption row — a control or a count. */
  action?: ReactNode;
  children: ReactNode;
  /** Extra classes for the outer frame (grid placement, height). */
  className?: string;
  /** Extra classes for the body, when the content needs to opt out of scroll. */
  bodyClassName?: string;
}

export function Panel({ title, action, children, className = '', bodyClassName = '' }: PanelProps): JSX.Element {
  return (
    <section
      className={`flex min-h-0 flex-col rounded border border-aurora-border bg-aurora-panel/95 ${className}`}
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-aurora-border px-3 py-1.5">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-aurora-muted">
          {title}
        </h2>
        {action}
      </header>

      <div className={`min-h-0 flex-1 overflow-auto p-3 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
