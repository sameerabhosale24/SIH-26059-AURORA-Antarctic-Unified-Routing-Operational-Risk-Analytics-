/**
 * Environment contract.
 *
 * Both variables are required. This module throws on import (i.e. at startup)
 * if either is missing or malformed, so that a misconfigured deployment fails
 * loudly instead of silently pointing at the wrong backend.
 *
 * Nothing else in the app may read `import.meta.env` directly — always go
 * through `API_BASE` / `WS_BASE` so URLs stay in one place.
 */

const MISSING_CONFIG_HINT = [
  'AURORA frontend is not configured.',
  '',
  'Create a `.env` file in the project root (see `.env.example`):',
  '',
  '  VITE_API_BASE=http://localhost:8000',
  '  VITE_WS_BASE=ws://localhost:8000',
  '',
  'Vite only exposes variables prefixed with VITE_ and requires a dev-server',
  'restart (or rebuild) after changing them.',
].join('\n');

function requireEnv(name: 'VITE_API_BASE' | 'VITE_WS_BASE'): string {
  const raw = import.meta.env[name];

  if (typeof raw !== 'string' || raw.trim() === '') {
    throw new Error(`${MISSING_CONFIG_HINT}\n\nMissing environment variable: ${name}`);
  }

  const value = raw.trim().replace(/\/+$/, '');

  try {
    new URL(value);
  } catch {
    throw new Error(
      `${MISSING_CONFIG_HINT}\n\nMalformed environment variable ${name}="${value}" (expected an absolute URL such as http://localhost:8000)`,
    );
  }

  return value;
}

function assertProtocol(name: 'VITE_API_BASE' | 'VITE_WS_BASE', value: string, allowed: string[]): void {
  const protocol = new URL(value).protocol;
  if (!allowed.includes(protocol)) {
    throw new Error(
      `${MISSING_CONFIG_HINT}\n\nEnvironment variable ${name}="${value}" uses protocol "${protocol}", expected one of: ${allowed.join(', ')}`,
    );
  }
}

/** Base URL for REST calls. Never has a trailing slash. */
export const API_BASE: string = requireEnv('VITE_API_BASE');

/** Base URL for WebSocket connections. Never has a trailing slash. */
export const WS_BASE: string = requireEnv('VITE_WS_BASE');

assertProtocol('VITE_API_BASE', API_BASE, ['http:', 'https:']);
assertProtocol('VITE_WS_BASE', WS_BASE, ['ws:', 'wss:']);
