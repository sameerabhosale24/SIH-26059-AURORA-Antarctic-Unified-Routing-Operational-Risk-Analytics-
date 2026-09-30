/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the AURORA REST API, e.g. `http://localhost:8000` (no trailing slash). */
  readonly VITE_API_BASE: string;
  /** Base URL of the AURORA WebSocket streams, e.g. `ws://localhost:8000` (no trailing slash). */
  readonly VITE_WS_BASE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
