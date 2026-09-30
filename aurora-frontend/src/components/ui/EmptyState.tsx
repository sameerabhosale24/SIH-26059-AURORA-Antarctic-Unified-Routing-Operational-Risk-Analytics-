/**
 * Empty state.
 *
 * Rendered whenever a store holds `null` — never a zero, never a spinner that
 * outlives its request. The wording names *what* is missing so an operator can
 * tell "backend has no data" from "nobody has computed a route yet".
 */
export interface EmptyStateProps {
  /** What is absent, e.g. `No route has been computed`. */
  message: string;
  /** Optional second line explaining what would fill it. */
  hint?: string;
}

export function EmptyState({ message, hint }: EmptyStateProps): JSX.Element {
  return (
    <div className="flex h-full min-h-[3rem] flex-col items-center justify-center gap-1 px-2 py-4 text-center">
      <p className="text-xs tracking-wide text-aurora-muted">{message}</p>
      {hint ? <p className="text-[11px] leading-relaxed text-aurora-muted/70">{hint}</p> : null}
    </div>
  );
}
