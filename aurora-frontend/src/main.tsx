/**
 * AURORA frontend entry point.
 *
 * Import order matters:
 *  - `config/env` is imported transitively and throws if VITE_API_BASE /
 *    VITE_WS_BASE are missing, so misconfiguration fails at startup rather
 *    than on the first request.
 *  - Tailwind is imported here so its base layer is present before any
 *    component renders.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { lccProjection, lccTest, registerLccProjection } from './config/projection';
import './index.css';

const container = document.getElementById('root');

if (!container) {
  throw new Error('AURORA: #root element is missing from index.html');
}

// Dev-only console bridge so the projection can be verified without opening
// the layer inspector:
//
//   __aurora.lccProjection() // the registered OpenLayers Projection object
//   __aurora.lccTest()       // round-trip transform of the projection origin
if (import.meta.env.DEV) {
  registerLccProjection();

  Object.defineProperty(globalThis, '__aurora', {
    value: {
      lccProjection,
      lccTest,
      registerLccProjection,
    },
    configurable: true,
  });
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
