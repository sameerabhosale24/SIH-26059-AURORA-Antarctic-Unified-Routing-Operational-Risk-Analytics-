/**
 * Auth session storage and the unauthorised-redirect channel.
 *
 * Lives apart from both `api.ts` and `userStore.ts` so neither has to import
 * the other: the API layer only needs to *read* the token and *announce* a 401,
 * while the store needs to *write* it. A cycle there would leave the token
 * variable undefined at module-init time.
 *
 * localStorage, not sessionStorage: step 6 of the acceptance list requires the
 * operator to still be signed in after a reload.
 */
import type { User } from '@/types/auth';

const TOKEN_KEY = 'aurora.token';
const USER_KEY = 'aurora.user';

/**
 * Where the operator was heading when a 401 interrupted them.
 *
 * sessionStorage so it survives the redirect to `/login` but not a browser
 * restart — a stale path from last week is worse than the default.
 */
const INTENDED_KEY = 'aurora.intended';

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // Storage can be blocked (private mode, disabled cookies). A token we
    // cannot read is a signed-out user, not a crash.
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* nothing useful to do — the session simply will not persist */
  }
}

export function getToken(): string | null {
  return read(TOKEN_KEY);
}

export function setToken(token: string): void {
  write(TOKEN_KEY, token);
}

export function getStoredUser(): User | null {
  const raw = read(USER_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as User;
    return typeof parsed?.email === 'string' ? parsed : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: User | null): void {
  write(USER_KEY, user === null ? null : JSON.stringify(user));
}

/** Drop the token and the cached user. Does *not* navigate. */
export function clearAuthStorage(): void {
  write(TOKEN_KEY, null);
  write(USER_KEY, null);
}

export function storeIntendedPath(path: string): void {
  write(INTENDED_KEY, path);
}

/** Read-and-clear, so a stale intention cannot fire twice. */
export function takeIntendedPath(fallback = '/ships'): string {
  const raw = read(INTENDED_KEY);
  write(INTENDED_KEY, null);

  // Only same-origin absolute paths — never let a stored value become an
  // open redirect.
  if (raw && raw.startsWith('/') && !raw.startsWith('//')) return raw;
  return fallback;
}

export function peekIntendedPath(): string | null {
  return read(INTENDED_KEY);
}

/**
 * Register what should happen when the API reports 401.
 *
 * Registered once from inside the router (`AuthBridge`), because navigating
 * needs router context that the API layer does not have. Until it is
 * registered, a 401 still clears the credentials — it just cannot redirect.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

/** Called by the API layer. Returns `true` when a handler dealt with it. */
export function notifyUnauthorized(): boolean {
  if (!unauthorizedHandler) return false;
  unauthorizedHandler();
  return true;
}
