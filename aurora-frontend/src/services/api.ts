/**
 * Typed REST client for the AURORA backend.
 *
 * Native `fetch` only — no axios. No caching and no retry here: stores own
 * their data lifecycle and the version poller owns refresh timing.
 *
 * `null` is a valid, expected result. It means "the backend has no data yet"
 * and the UI must render an empty state, never a placeholder value.
 */
import { API_BASE } from '@/config/env';
import {
  clearAuthStorage,
  getToken,
  notifyUnauthorized,
  setStoredUser,
  setToken,
  storeIntendedPath,
} from '@/services/session';
import type { Alarm } from '@/types/alarm';
import type { AisTarget } from '@/types/ais';
import type { Iceberg } from '@/types/iceberg';
import type { FeatureCollection } from 'geojson';
import type { Roi, Station } from '@/types/common';
import type { EncManifest } from '@/types/enc';
import type { LoginResponse, User } from '@/types/auth';
import type { RouteRun } from '@/types/route';
import type { SicFramesResponse } from '@/types/sic';
import type { VesselState } from '@/types/vessel';
import type { Vessel, VesselBlueprint, VesselPatch } from '@/types/ship';
import type { DataVersion } from '@/types/version';
import type { WeatherPoint } from '@/types/weather';

/**
 * Endpoint paths, in one place so they can be aligned with the backend
 * without touching call sites.
 */
export const API_PATHS = {
  roi: '/api/roi',
  version: '/api/version',
  vesselLatest: '/api/vessel/latest',
  aisLatest: '/api/ais/latest',
  sicFrames: '/api/sic/frames',
  icebergsCurrent: '/api/icebergs/current',
  routeCurrent: '/api/route/current',
  routeHistory: '/api/route/history',
  routeAccept: '/api/route/accept',
  weatherAtVessel: '/api/weather/vessel',
  alarmsActive: '/api/alarms',
  stations: '/api/stations',
  coastline: '/api/coastline',
  encManifest: '/api/enc/manifest',
  health: '/api/health',

  /* auth + fleet */
  authLogin: '/api/auth/login',
  authMe: '/api/auth/me',
  authLogout: '/api/auth/logout',
  vessels: '/api/vessels',
} as const;

/** Error thrown for any non-2xx response (204 is a success, not an error). */
export class ApiError extends Error {
  readonly status: number;
  readonly body: string;
  readonly url: string;

  constructor(url: string, status: number, body: string) {
    super(`AURORA API ${status} from ${url}${body ? `: ${truncate(body, 300)}` : ''}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.url = url;
  }
}

export type QueryParams = Record<string, string | number>;

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

function buildUrl(path: string, params?: QueryParams): string {
  const url = `${API_BASE}${path}`;
  if (!params) return url;

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    search.append(key, String(value));
  }

  const query = search.toString();
  return query ? `${url}?${query}` : url;
}

async function readBody(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    return '';
  }
}

/** Accept header plus the bearer token, read fresh on every single call. */
function defaultHeaders(): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' };

  // Read per call, never cached: a login in another tab must take effect on
  // the very next request without this module being re-imported.
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  return headers;
}

/**
 * React to a 401: drop the credentials, remember where we were, notify the
 * router.
 *
 * Excluded for the login endpoint — a 401 there *is* the answer to "is this
 * password right", and redirecting from `/login` to `/login` would destroy
 * the inline error the operator needs to see.
 *
 * Network failures never reach this function: `fetch` rejects before a status
 * exists, so an unreachable backend leaves the token alone.
 */
function handleUnauthorized(path: string): void {
  if (path === API_PATHS.authLogin) return;

  // Already on the sign-in page: recording it as "where you were heading"
  // would return the operator to `/login` right after a successful sign-in.
  if (window.location.pathname === '/login') return;

  clearAuthStorage();
  setStoredUser(null);
  storeIntendedPath(`${window.location.pathname}${window.location.search}`);
  notifyUnauthorized();
}

async function decode<T>(url: string, path: string, response: Response): Promise<T | null> {
  if (response.status === 204) return null;

  const raw = await readBody(response);

  if (!response.ok) {
    if (response.status === 401) handleUnauthorized(path);
    throw new ApiError(url, response.status, raw);
  }

  if (raw.trim() === '') return null;

  try {
    return JSON.parse(raw) as T;
  } catch (cause) {
    throw new ApiError(url, response.status, `Malformed JSON: ${String(cause)}`);
  }
}

async function call<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  params?: QueryParams,
): Promise<T | null> {
  const url = buildUrl(path, params);
  const headers = defaultHeaders();

  // `exactOptionalPropertyTypes` rejects an explicit `body: undefined`.
  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  const response = await fetch(url, init);

  return decode<T>(url, path, response);
}

/**
 * Perform a GET and decode the JSON body.
 *
 * Returns `null` for `204 No Content` (and for an empty body), so callers can
 * treat "no data yet" as a first-class state. Throws {@link ApiError} for any
 * other non-2xx status. Throws whatever `fetch` threw on a network error —
 * that is not an auth failure and must not clear the session.
 */
export async function request<T>(path: string, params?: QueryParams): Promise<T | null> {
  return call<T>('GET', path, undefined, params);
}

/** `GET` returning `T | null`. Throws {@link ApiError} on failure. */
export async function get<T>(path: string, params?: QueryParams): Promise<T | null> {
  return call<T>('GET', path, undefined, params);
}

/** `POST` a JSON body, returning `T | null`. Throws {@link ApiError} on failure. */
export async function post<T>(path: string, body?: unknown): Promise<T | null> {
  return call<T>('POST', path, body ?? {});
}

/** `PATCH` a partial JSON body, returning `T | null`. */
export async function patch<T>(path: string, body?: unknown): Promise<T | null> {
  return call<T>('PATCH', path, body ?? {});
}

/** `DELETE`, returning `T | null` (null for the 204 the backend sends). */
export async function del<T>(path: string): Promise<T | null> {
  return call<T>('DELETE', path);
}

/**
 * Required-single-object helper.
 *
 * Used for endpoints whose payload is configuration rather than a measurement
 * (ROI, version). An empty body is a server misconfiguration, so it surfaces as
 * an {@link ApiError} instead of a silent `null` that would leave the map blank.
 */
async function getRequired<T>(path: string, label: string, params?: QueryParams): Promise<T> {
  const result = await request<T>(path, params);
  if (result === null) {
    throw new ApiError(`${API_BASE}${path}`, 204, `Backend returned no ${label}`);
  }
  return result;
}

/** Collection helper: `null` and error-free empty payloads collapse to `[]`. */
async function getList<T>(path: string, params?: QueryParams): Promise<T[]> {
  const result = await request<T[]>(path, params);
  return result ?? [];
}

/* ------------------------------------------------------------------ *
 * Typed endpoint wrappers
 * ------------------------------------------------------------------ */

/** `GET /api/roi` — region of interest. Supplied by the backend, never hardcoded. */
export function getRoi(): Promise<Roi> {
  return getRequired<Roi>(API_PATHS.roi, 'ROI configuration');
}

/** `GET /api/version` — current revision of every data product. */
export function getVersion(): Promise<DataVersion> {
  return getRequired<DataVersion>(API_PATHS.version, 'version payload');
}

/** `GET /api/vessel/latest` — most recent own-ship snapshot, or null. */
export function getVesselLatest(): Promise<VesselState | null> {
  return get<VesselState>(API_PATHS.vesselLatest);
}

/** `GET /api/ais/latest` — snapshot of all tracked targets; `[]` when none. */
export function getAisLatest(): Promise<AisTarget[]> {
  return getList<AisTarget>(API_PATHS.aisLatest);
}

/** `GET /api/sic/frames?v=N` — manifest of available SIC frames. */
export function getSicFrames(): Promise<SicFramesResponse> {
  return getRequired<SicFramesResponse>(API_PATHS.sicFrames, 'SIC frame manifest');
}

/** `GET /api/icebergs/current` — latest iceberg positions; `[]` when none. */
export function getIcebergsCurrent(): Promise<Iceberg[]> {
  return getList<Iceberg>(API_PATHS.icebergsCurrent);
}

/** `GET /api/route/current` — active route run, or null when none computed. */
export function getRouteCurrent(vesselId?: number): Promise<RouteRun | null> {
  return get<RouteRun>(API_PATHS.routeCurrent, vesselId === undefined ? undefined : { vessel_id: vesselId });
}

/** `GET /api/route/history?limit=N` — past route runs, newest first. */
export function getRouteHistory(limit: number): Promise<RouteRun[]> {
  return getList<RouteRun>(API_PATHS.routeHistory, { limit });
}

/** `GET /api/weather/vessel` — weather at the vessel, or null. */
export function getWeatherAtVessel(vesselId?: number): Promise<WeatherPoint | null> {
  return get<WeatherPoint>(
    API_PATHS.weatherAtVessel,
    vesselId === undefined ? undefined : { vessel_id: vesselId },
  );
}

/**
 * `GET /api/alarms?since=T&vessel_id=N` — alarm history.
 *
 * `since` is an ISO timestamp. `vesselId` scopes the list to one ship; left
 * out, the backend returns everything the caller is allowed to see.
 */
export function getAlarmsActive(vesselId?: number, since?: string): Promise<Alarm[]> {
  const params: QueryParams = {};
  if (since) params.since = since;
  if (vesselId !== undefined) params.vessel_id = vesselId;

  return getList<Alarm>(API_PATHS.alarmsActive, Object.keys(params).length ? params : undefined);
}

/** `GET /api/stations` — static station metadata; `[]` when empty. */
export function getStations(): Promise<Station[]> {
  return getList<Station>(API_PATHS.stations);
}

/** `POST /api/alarms/{id}/ack` — acknowledge an alarm, returning the updated alarm. */
export function ackAlarm(id: number, ackedBy: string): Promise<Alarm> {
  return postRequired<Alarm>(`${API_PATHS.alarmsActive}/${id}/ack`, { acked_by: ackedBy });
}

/**
 * `GET /api/coastline` — coastline as GeoJSON.
 *
 * Returns `null` when the backend has not published a coastline. The coastline
 * layer renders nothing in that case; it never substitutes a synthetic outline.
 */
export function getCoastline(): Promise<FeatureCollection | null> {
  return get<FeatureCollection>(API_PATHS.coastline);
}

/**
 * `GET /api/enc/manifest` — available S-57 cells.
 *
 * An ENC-free backend returns `{ cells: [], version: n }`; the ENC layer then
 * renders nothing rather than substituting a placeholder chart.
 */
export function getEncManifest(): Promise<EncManifest> {
  return getRequired<EncManifest>(API_PATHS.encManifest, 'ENC manifest');
}

/** One entry of `GET /api/health`. */
export interface HealthEntry {
  name: string;
  status: 'ok' | 'degraded' | 'down' | 'unknown' | string;
  detail?: string | null;
  last_ok?: string | null;
}

/** Response of `GET /api/health`. */
export interface HealthReport {
  status: 'ok' | 'degraded' | 'down' | string;
  services?: HealthEntry[];
  version?: string | null;
}

/** `GET /api/health` — service status. Null when the backend has no report. */
export function getHealth(): Promise<HealthReport | null> {
  return get<HealthReport>(API_PATHS.health);
}

/**
 * `POST /api/route/accept` — accept a candidate route.
 *
 * The response is intentionally loose: the backend may return the accepted
 * route run, the accepted route, or nothing at all. Only a successful HTTP
 * status is treated as success by the caller.
 */
export function acceptRoute(
  routeId: number,
  routeRunId: number,
  acceptedBy: string,
): Promise<RouteRun | null> {
  return post<RouteRun>(API_PATHS.routeAccept, {
    route_id: routeId,
    route_run_id: routeRunId,
    accepted_by: acceptedBy,
  });
}

/* ------------------------------------------------------------------ *
 * Auth
 * ------------------------------------------------------------------ */

/**
 * `POST /api/auth/login` — exchange credentials for a bearer token.
 *
 * On success the token is persisted here so every subsequent call carries it.
 * A 401 (wrong password) deliberately does *not* trigger the global sign-out
 * path — see {@link handleUnauthorized}.
 */
export async function login(email: string, password: string): Promise<LoginResponse> {
  const body = await postRequired<LoginResponse>(API_PATHS.authLogin, { email, password });

  setToken(body.token);
  setStoredUser(body.user);

  return body;
}

/** `GET /api/auth/me` — re-identify the stored token. Null when rejected. */
export async function getMe(): Promise<User | null> {
  try {
    return await get<User>(API_PATHS.authMe);
  } catch (error) {
    // A 401 here has already cleared storage via the shared handler; anything
    // else (offline, backend restarting) must not sign the operator out.
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/**
 * `POST /api/auth/logout` — advisory server-side invalidation.
 *
 * The credential is dropped locally regardless of the outcome: the operator
 * asked to sign out, and a 500 from a stateless JWT endpoint must not
 * resurrect the session.
 */
export async function logout(): Promise<void> {
  try {
    await post(API_PATHS.authLogout, {});
  } catch {
    /* local sign-out below is the part that matters */
  } finally {
    clearAuthStorage();
    setStoredUser(null);
  }
}

/* ------------------------------------------------------------------ *
 * Fleet
 * ------------------------------------------------------------------ */

/** `GET /api/vessels` — every vessel for the signed-in user. */
export function getVessels(): Promise<Vessel[]> {
  return getList<Vessel>(API_PATHS.vessels);
}

/** `GET /api/vessels/:id` — one blueprint. Throws 404 when absent. */
export function getVessel(id: number): Promise<Vessel> {
  return getRequired<Vessel>(`${API_PATHS.vessels}/${id}`, 'vessel');
}

/** `POST /api/vessels` — create a blueprint, returning the stored record. */
export function createVessel(blueprint: VesselBlueprint): Promise<Vessel> {
  return postRequired<Vessel>(API_PATHS.vessels, blueprint);
}

/** `PATCH /api/vessels/:id` — partial update, returning the stored record. */
export async function updateVessel(id: number, blueprint: VesselPatch): Promise<Vessel> {
  const result = await patch<Vessel>(`${API_PATHS.vessels}/${id}`, blueprint);
  if (result === null) {
    throw new ApiError(`${API_BASE}${API_PATHS.vessels}/${id}`, 204, 'Backend returned no body');
  }
  return result;
}

/** `DELETE /api/vessels/:id` — remove a blueprint (204 on success). */
export function deleteVessel(id: number): Promise<void> {
  return del<null>(`${API_PATHS.vessels}/${id}`).then(() => undefined);
}

function postRequired<T>(path: string, body: unknown): Promise<T> {
  return post<T>(path, body).then((result) => {
    if (result === null) {
      throw new ApiError(`${API_BASE}${path}`, 204, 'Backend returned no body');
    }
    return result;
  });
}
