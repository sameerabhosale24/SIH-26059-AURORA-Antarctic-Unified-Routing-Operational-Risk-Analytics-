/**
 * Who is signed in.
 *
 * Hydrated *synchronously* from localStorage at module load rather than in an
 * effect, so `RequireAuth` sees the restored session on the very first render.
 * An effect-based restore would bounce a reloading operator to `/login` for
 * one frame and then back, which acceptance step 6 forbids.
 */
import { create } from 'zustand';

import { ApiError, getMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '@/services/api';
import {
  clearAuthStorage,
  getStoredUser,
  getToken,
  setStoredUser,
  setToken,
} from '@/services/session';
import type { LoginResponse, User } from '@/types/auth';

export type AuthStatus = 'idle' | 'pending' | 'error';

export interface UserStore {
  user: User | null;
  /** Mirrors storage so callers can show "signed in" without a second read. */
  token: string | null;
  status: AuthStatus;
  error: string | null;

  signIn(email: string, password: string): Promise<boolean>;
  /**
   * Create an account and sign straight in. Resolves `false` (with `error`
   * set) rather than throwing, so a duplicate address can be shown inline.
   */
  register(email: string, password: string): Promise<boolean>;
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
      const { token, user } = await authenticate(email, password);
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

  register: async (email, password) => {
    set({ status: 'pending', error: null });

    try {
      const { token, user } = await createAccount(email, password);
      set({ user, token, status: 'idle', error: null });
      return true;
    } catch (cause) {
      set({ status: 'error', error: registerErrorMessage(cause) });
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

/**
 * Sign-in, routed to the dev shim when `VITE_AUTH_DEV=true`.
 *
 * The shim persists through the same session helpers as the real client, so a
 * reload restores a dev session exactly as it would a real one.
 */
async function authenticate(email: string, password: string): Promise<LoginResponse> {
  if (import.meta.env.VITE_AUTH_DEV !== 'true') return apiLogin(email, password);

  const { devLogin } = await import('@/services/authDev');
  const credentials = await devLogin(email, password);
  setToken(credentials.token);
  setStoredUser(credentials.user);
  return credentials;
}

/** Registration, with the same dev-mode routing as {@link authenticate}. */
async function createAccount(email: string, password: string): Promise<LoginResponse> {
  if (import.meta.env.VITE_AUTH_DEV !== 'true') return apiRegister(email, password);

  const { devRegister } = await import('@/services/authDev');
  const credentials = await devRegister(email, password);
  setToken(credentials.token);
  setStoredUser(credentials.user);
  return credentials;
}

/** `detail` out of a FastAPI error body, when the backend sent one. */
function backendDetail(cause: ApiError): string | null {
  try {
    const parsed = JSON.parse(cause.body) as { detail?: unknown };
    if (typeof parsed.detail === 'string' && parsed.detail.trim() !== '') return parsed.detail;
  } catch {
    /* body was not JSON — fall through to the generic text */
  }
  return null;
}

/** Registration failure text. A duplicate address gets its own wording. */
function registerErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 409) return 'An account with this email already exists';

    const detail = backendDetail(cause);
    if (detail) return detail;

    if (cause.status === 404) return 'Registration is not available on this backend.';
    if (cause.status === 500 || cause.status === 503) return 'Registration service is unavailable.';
  }

  if (cause instanceof TypeError) return 'Cannot reach the AURORA backend. Is it running?';
  if (cause instanceof Error) return cause.message;
  return 'Registration failed.';
}
