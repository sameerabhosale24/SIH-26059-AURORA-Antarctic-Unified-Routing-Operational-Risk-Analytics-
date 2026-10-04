/**
 * Route table.
 *
 * Three routes are public — `/` (the landing page), `/login` and `/register`
 * — because a stranger has no session to protect and nothing to read. Every
 * console route sits behind two guard layers:
 *
 *   RequireAuth  — is anyone signed in?
 *   RequireVessel — does the URL name a vessel?
 *
 * The four console views all carry `/:vesselId`, because a map with no ship
 * selected is not a view of anything; it is an error the operator should
 * never be shown. `/ships` sits outside that second guard precisely so a
 * missing or deleted vessel has somewhere to send them back to.
 */
import { Navigate, Route, Routes } from 'react-router-dom';

import { AuthBridge, RequireAuth, RequireVessel } from '@/components/guards';
import { AddShipPage } from '@/views/AddShipPage';
import { AnalysisView } from '@/views/AnalysisView';
import { LandingPage } from '@/views/LandingPage';
import { LoginPage } from '@/views/LoginPage';
import { OperationalView } from '@/views/OperationalView';
import { PlanningView } from '@/views/PlanningView';
import { RegisterPage } from '@/views/RegisterPage';
import { SettingsView } from '@/views/SettingsView';
import { ShipDetailPage } from '@/views/ShipDetailPage';
import { ShipsOverviewPage } from '@/views/ShipsOverviewPage';

export function AppRoutes(): JSX.Element {
  return (
    <>
      {/* Mounted once per app, inside the router so a 401 can navigate. */}
      <AuthBridge />

      <Routes>
        {/* Public: no session exists yet, so there is nothing to guard. */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/ships" element={<ShipsOverviewPage />} />
          <Route path="/ships/new" element={<AddShipPage />} />
          <Route path="/ships/:id" element={<ShipDetailPage />} />
          <Route path="/ships/:id/edit" element={<AddShipPage />} />

          <Route element={<RequireVessel />}>
            <Route path="/map/:vesselId" element={<OperationalView />} />
            <Route path="/planning/:vesselId" element={<PlanningView />} />
            <Route path="/analysis/:vesselId" element={<AnalysisView />} />
            <Route path="/settings/:vesselId" element={<SettingsView />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/ships" replace />} />
      </Routes>
    </>
  );
}
