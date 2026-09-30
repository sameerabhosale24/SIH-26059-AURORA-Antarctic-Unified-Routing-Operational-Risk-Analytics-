/**
 * Route guards and the auth bridge.
 *
 * Guards answer exactly one question each so their render is free of policy:
 * `RequireAuth` "is anyone signed in?", `RequireVessel` "did the URL name a
 * vessel?". Everything about *fetching* that vessel belongs to the view, which
 * knows what a failure looks like on a map.
 */
import { useEffect } from 'react';
import { Navigate, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';

import { useShipsStore } from '@/stores/shipsStore';
import { useUserStore } from '@/stores/userStore';
import { useVesselStore } from '@/stores/vesselStore';
import { setUnauthorizedHandler, storeIntendedPath } from '@/services/session';

/**
 * Sign in, or hand over the path we were trying to reach.
 *
 * The path is stored *before* the redirect so a 401 from deep inside a map
 * view and a plain first visit behave identically: after login the operator
 * lands where they meant to be, not on a generic dashboard.
 */
export function RequireAuth(): JSX.Element {
  const user = useUserStore((state) => state.user);
  const location = useLocation();

  if (user === null) {
    storeIntendedPath(`${location.pathname}${location.search}`);
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

/**
 * The URL must carry `:vesselId`.
 *
 * Validation of *which* vessel that is (exists? mine? readable?) is left to
 * the view — a guard cannot distinguish "404" from "backend is down", and
 * showing "not found" while the API is unreachable would be a lie.
 */
export function RequireVessel(): JSX.Element {
  const { vesselId } = useParams();

  if (!vesselId || !/^\d+$/.test(vesselId)) {
    return <Navigate to="/ships" replace />;
  }

  return <Outlet />;
}

/**
 * Connects a 401 from the API layer to the router.
 *
 * Mounted inside the router because navigation needs router context the API
 * module must not depend on. Signing out here also drops the fleet cache: the
 * next operator must not see the previous one's ships, even for a frame.
 */
export function AuthBridge(): null {
  const navigate = useNavigate();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      useUserStore.getState().clearSession();
      useShipsStore.getState().reset();
      useVesselStore.getState().clearVessel();
      navigate('/login', { replace: true });
    });

    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  return null;
}
