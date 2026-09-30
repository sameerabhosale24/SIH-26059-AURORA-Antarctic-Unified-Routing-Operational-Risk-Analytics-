/**
 * Who is signed in.
 *
 * Hydrated *synchronously* from localStorage at module load rather than in an
 * effect, so `RequireAuth` sees the restored session on the very first render.
 * An effect-based restore would bounce a reloading operator to `/login` for
 * one frame and then back, which acceptance step 6 forbids.
 */
import { create } from 'zustand';

import { getMe, login as apiLogin, logout as apiLogout } from '@/services/api';
import {
  clearAuthStorage,
  getStoredUser,
  getToken,
  setStoredUser,
} from '@/services/session';
import type { User } from '@/types/auth';

export type AuthStatus = 'idle' | 'pending' | 'error';

export interface UserStore {
  user: User | null;
  /** Mirrors storage so callers can show "signed in" without a second read. */
  token: string | null;
  status: AuthStatus;
  error: string | null;

  signIn(email: string, password: string): Promise<boolean>;
  signOut(): Promise<void>;
  /** Re-validate the stored token against `/api/auth/me`. */
  refresh(): Promise<void>;
  /**
   * Local-only teardown for a 401: no network call, because the token is
   * already dead.
   */
  clearSession(): void;
}

function currentToken(): string | null {
  return getToken();
}

export const useUserStore = create<UserStore>()((set, get) => ({
  user: getStoredUser(),
  token: currentToken(),
  status: 'idle',
  error: null,

  signIn: async (email, password) => {
    set({ status: 'pending', error: null });

    try {
      const { token, user } = await apiLogin(email, password);
      set({ user, token, status: 'idle', error: null });
      return true;
    } catch (cause) {
      set({
        status: 'error',
        error: signInErrorMessage(cause),
        // A failed sign-in never signs anyone in: leave whatever session
        // existed untouched.
      });
      return false;
    }
  },

  signOut: async () => {
    set({ status: 'pending' });
    await apiLogout();
    set({ user: null, token: null, status: 'idle', error: null });
  },

  refresh: async () => {
    try {
      const user = await getMe();
      if (user === null) {
        get().clearSession();
        return;
      }
      set({ user, token: currentToken(), status: 'idle', error: null });
    } catch {
      // Network or 5xx: keep the local session. Only an actual 401 — already
      // routed through `clearSession` by the API layer — ends it.
      set({ status: 'idle' });
    }
  },

  clearSession: () => {
    clearAuthStorage();
    setStoredUser(null);
    set({ user: null, token: null, status: 'idle', error: null });
  },
}));

/**
 * Operator-facing sign-in failure text.
 *
 * Authentication failures are phrased for a human at 03:00 in a dark
 * wheelhouse; transport failures say what is actually wrong rather than
 * implying the password was bad.
 */
function signInErrorMessage(cause: unknown): string {
  if (cause && typeof cause === 'object' && 'status' in cause) {
    const status = (cause as { status?: unknown }).status;
    if (status === 401 || status === 403) return 'Email or password is not recognised.';
    if (status === 404) return 'Sign-in service is not available on this backend.';
    if (status === 429) return 'Too many attempts. Wait a moment and try again.';
    if (status === 500 || status === 503) return 'Sign-in service is unavailable.';
  }

  if (cause instanceof TypeError) return 'Cannot reach the AURORA backend. Is it running?';
  if (cause instanceof Error) return cause.message;
  return 'Sign-in failed.';
}
