/**
 * Toast stack.
 *
 * Toasts are non-blocking and self-dismissing: they announce that something
 * changed, and every message is recoverable from a panel, so an operator can
 * ignore one without losing information. Auto-dismiss is per row and starts on
 * mount, which means a row that React re-orders does not restart its own
 * countdown.
 */
import { useEffect } from 'react';

import { TOAST_TTL_MS, useToastStore, type Toast, type ToastTone } from '@/stores/toastStore';

const TONE_CLASS: Record<ToastTone, string> = {
  info: 'border-aurora-accent/40 text-aurora-accent',
  success: 'border-aurora-ok/40 text-aurora-ok',
  warn: 'border-aurora-warn/50 text-aurora-warn',
  error: 'border-aurora-crit/50 text-aurora-crit',
};

function ToastRow({ toast }: { toast: Toast }): JSX.Element {
  const dismiss = useToastStore((state) => state.dismiss);

  useEffect(() => {
    const id = window.setTimeout(() => dismiss(toast.id), TOAST_TTL_MS);
    return () => window.clearTimeout(id);
  }, [dismiss, toast.id]);

  return (
    <div
      className={`pointer-events-auto min-w-[16rem] max-w-sm rounded border bg-aurora-panel px-3 py-2 shadow-lg shadow-black/40 ${TONE_CLASS[toast.tone]}`}
      role="status"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium tracking-wide text-aurora-text">{toast.message}</p>
          {toast.detail ? (
            <p className="mt-0.5 truncate text-[11px] text-aurora-muted">{toast.detail}</p>
          ) : null}
        </div>

        <button
          type="button"
          onClick={() => dismiss(toast.id)}
          className="shrink-0 text-xs text-aurora-muted transition-colors hover:text-aurora-text"
          aria-label="Dismiss notification"
        >
          ×
        </button>
      </div>
    </div>
  );
}

export function ToastHost(): JSX.Element | null {
  const toasts = useToastStore((state) => state.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-14 z-50 flex flex-col items-end gap-2">
      {toasts.map((toast) => (
        <ToastRow key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
