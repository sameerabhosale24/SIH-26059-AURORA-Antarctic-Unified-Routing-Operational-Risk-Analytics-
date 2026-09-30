/**
 * Non-blocking notifications.
 *
 * Toasts announce *changes* — a republished forecast, a route awaiting review.
 * They never carry information the operator cannot recover elsewhere: every
 * message names something also visible in a panel, so dismissing one loses
 * nothing. Nothing here ever reloads the page or clears view state.
 */
import { create } from 'zustand';

export type ToastTone = 'info' | 'success' | 'warn' | 'error';

export interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
  /** Optional second line — the affected product or route label. */
  detail?: string;
  createdAt: number;
}

export type NewToast = Omit<Toast, 'id' | 'createdAt'>;

export interface ToastStore {
  toasts: Toast[];
  push(toast: NewToast): void;
  dismiss(id: number): void;
  clear(): void;
}

/** Past this age a toast is considered spent and stops demanding attention. */
export const TOAST_TTL_MS = 8_000;

let nextId = 1;

export const useToastStore = create<ToastStore>()((set) => ({
  toasts: [],

  push: (toast) =>
    set((state) => {
      const entry: Toast = { ...toast, id: nextId++, createdAt: Date.now() };

      // Cap the stack: a backend that starts republishing every few seconds
      // must not bury the map under notifications.
      const toasts = [...state.toasts, entry].slice(-4);
      return { toasts };
    }),

  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  clear: () => set({ toasts: [] }),
}));

/** Convenience for call sites that only have a message. */
export function notify(message: string, tone: ToastTone = 'info', detail?: string): void {
  useToastStore.getState().push({ message, tone, ...(detail !== undefined ? { detail } : {}) });
}
