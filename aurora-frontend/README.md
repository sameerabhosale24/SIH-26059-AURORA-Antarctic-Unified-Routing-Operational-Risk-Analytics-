# AURORA — Frontend

Operational map interface for research vessels transiting Cape Town → Maitri/Bharati.

This repository contains the **frontend only**: the foundation layer (Part 1),
the map layers, panels, controls and views (Part 2), and authentication with
fleet management (Part 3). There is **no backend anywhere in this workspace** —
nothing here invents data to fill the gap.

With no backend running, the app boots, renders the dark shell, shows an
`API: down / WS: closed` badge, sends an unauthenticated visitor to `/login`,
and logs a single `Failed to fetch ROI`. That is the correct first-launch
state: every store is `null` and nothing is fabricated.

---

## Stack

| Concern | Choice |
| --- | --- |
| UI | React 18 + TypeScript (strict) |
| Build | Vite 7 |
| Map | OpenLayers 9 (`ol@^9`, **not** MapLibre/Mapbox/Leaflet) |
| Projection | `proj4` — LCC registered as `EPSG:9802` |
| State | Zustand 5 |
| Styling | Tailwind CSS 3.4 |
| Charts | Recharts 3 |
| Forms | `react-hook-form` 7 + `zod` 4 via `@hookform/resolvers` |
| Transport | Native `fetch` + native `WebSocket` |
| Routing | react-router-dom 7 |

No runtime library beyond that list. No analytics, no mock data, no synthetic
fixtures anywhere in the tree. "Authentication" here means a bearer token the
backend issues — the client stores it, sends it, and signs out on a `401`; it
does not implement its own identity.

---

## Install and run

```bash
cd aurora-frontend
npm install
cp .env.example .env      # Windows: copy .env.example .env
npm run dev
```

Open http://localhost:5173.

Other scripts:

```bash
npm run typecheck   # tsc --noEmit, strict mode, zero errors expected
npm run build       # typecheck + production bundle into dist/
npm run preview     # serve the production bundle
```

> A `.env` file is **not** committed (see `.gitignore`). Create it before
> `npm run dev`, otherwise startup fails loudly with instructions — see below.

---

## Configuring the backend

Both variables are **required** and are read in exactly one place,
`src/config/env.ts`. No URL is hardcoded anywhere else in the codebase.

| Variable | Example | Purpose |
| --- | --- | --- |
| `VITE_API_BASE` | `http://localhost:8000` | REST base URL, no trailing slash, `http`/`https` |
| `VITE_WS_BASE` | `ws://localhost:8000` | WebSocket base URL, no trailing slash, `ws`/`wss` |

If either is missing or malformed, `env.ts` throws during module init, so the
app fails at startup with the offending variable named rather than throwing on
the first request. Vite only exposes `VITE_`-prefixed variables, and a change
requires a dev-server restart.

### Expected endpoints

Implemented in `src/services/api.ts`; paths are centralised in the exported
`API_PATHS` map so the backend can be realigned without touching call sites.

| Wrapper | Method + path | Returns |
| --- | --- | --- |
| `getRoi()` | `GET /api/roi` | `Roi` |
| `getVersion()` | `GET /api/version` | `DataVersion` |
| `getVesselLatest()` | `GET /api/vessel/latest` | `VesselState \| null` |
| `getAisLatest()` | `GET /api/ais/latest` | `AisTarget[]` |
| `getSicFrames()` | `GET /api/sic/frames?v=N` | `SicFramesResponse` |
| `getIcebergsCurrent()` | `GET /api/icebergs/current` | `Iceberg[]` |
| `getRouteCurrent(vesselId?)` | `GET /api/route/current?vessel_id=N` | `RouteRun \| null` |
| `getRouteHistory(limit)` | `GET /api/route/history?limit=N` | `RouteRun[]` |
| `getWeatherAtVessel(vesselId?)` | `GET /api/weather/vessel?vessel_id=N` | `WeatherPoint \| null` |
| `getAlarmsActive(vesselId?, since?)` | `GET /api/alarms?vessel_id=N&since=T` | `Alarm[]` |
| `getStations()` | `GET /api/stations` | `Station[]` |
| `ackAlarm(id, ackedBy)` | `POST /api/alarms/{id}/ack` | `Alarm` |
| `login(email, password)` | `POST /api/auth/login` | `LoginResponse` (token + user) |
| `getMe()` | `GET /api/auth/me` | `User \| null` |
| `logout()` | `POST /api/auth/logout` | `204` |
| `getVessels()` | `GET /api/vessels` | `Vessel[]` |
| `getVessel(id)` | `GET /api/vessels/:id` | `Vessel` |
| `createVessel(bp)` | `POST /api/vessels` | `Vessel` |
| `updateVessel(id, patch)` | `PATCH /api/vessels/:id` | `Vessel` |
| `deleteVessel(id)` | `DELETE /api/vessels/:id` | `204` |

WebSocket channels are instantiated in `src/services/websocket.ts` and are
**not** connected on import: `/ws/vessel`, `/ws/ais`, `/ws/alarms`,
`/ws/weather`, `/ws/route`. Each reconnects with exponential backoff
(1 s base, 30 s cap), resets the backoff after a successful handshake, drops
non-JSON frames with a warning, and never buffers or replays messages — a
store resyncs over REST after reconnect.

### Endpoints assumed rather than specified

Six paths were not in the original endpoint contract and were chosen to fit
the surrounding naming. They are isolated in `API_PATHS` — confirm them against
the backend:

- `/api/roi`
- `/api/vessel/latest`
- `/api/ais/latest`
- `/api/weather/vessel`
- `/api/auth/{login,me,logout}`
- `/api/vessels` (and `/api/vessels/:id`)

**Auth contract assumed by the client:**

- `POST /api/auth/login` takes `{ email, password }` and returns
  `{ token, user: { id, email, role } }`. The token is stored in
  `localStorage` under `aurora.token` and sent as `Authorization: Bearer …`
  on every call.
- A `401` from any *other* endpoint clears the credential, remembers the path
  being attempted in `sessionStorage`, and navigates to `/login`. After a
  successful sign-in the operator is returned to that path.
- A `401` from the **login** endpoint is exempt: it is the answer to "is this
  password right", not a lost session, and redirecting `/login → /login`
  would swallow the error message.
- Network failures (backend down) never clear the token — `fetch` rejects
  before a status exists.
- `POST /api/auth/logout` is advisory; the credential is dropped locally
  regardless of the response, because the operator asked to sign out.

`SicFrameMeta.frame_extent` is taken verbatim from the backend as the
OpenLayers `imageExtent`. The frontend never recomputes it.

---

## Projection

The map is **Lambert Conformal Conic**, not Web Mercator.

```
+proj=lcc +lat_1=-45 +lat_2=-65 +lat_0=-55 +lon_0=35 +x_0=0 +y_0=0
+datum=WGS84 +units=m +no_defs
```

Defined in `src/config/projection.ts` and registered with proj4 as
**`EPSG:9802`**, then handed to OpenLayers via `ol/proj/proj4.register`. Once the
view projection is set, OpenLayers reprojects every layer automatically.

Conic projection because the operating area spans ~90° of longitude at high
southern latitudes, where Mercator badly distorts scale and shape. Standard
parallels at 45°S and 65°S keep the corridor near-conformal.

Exports:

- `registerLccProjection()` — idempotent; called by `createMap` and `App`
- `lccProjection()` — the OpenLayers `Projection`
- `toLCC(lonLat)` / `fromLCC(xy)` — WGS84 degrees ↔ LCC metres
- `lccExtent(roi)` — `[minX, minY, maxX, maxY]` in LCC metres, from the four
  ROI corners
- `lccTest()` — round-trip self-check

`src/utils/geo.ts` re-exports these as `wgs84ToLCC`, `lccToWgs84`,
`roiCenter` and `roiExtentLCC`.

**The ROI is never hardcoded.** `MapView` fetches it from `GET /api/roi`; the
map only exists once that succeeds.

Verify in the browser console (dev server only):

```js
__aurora.lccProjection()  // the registered Projection object
__aurora.lccTest()        // [lon, lat, x, y] → [35, -55, 0, 0]
```

---

## State

Every *data* store follows one contract (`src/stores/createDataStore.ts`):

```ts
{ data, lastUpdated, error, set(data), setError(msg), clear() }
```

- `data` starts `null` and is never a zero-filled object or placeholder array.
- `lastUpdated` is client arrival time (`Date.now()`), not the producer's `ts`.
  Staleness is about how long *we* have been blind.
- `error` never replaces `data`, so a transient blip does not blank the screen.
- `clear()` resets for vessel change / sign-out.

`userStore` and `shipsStore` are deliberately *not* data stores: a session and
a fleet collection have loading/submitting semantics that `data`/`lastUpdated`
would misrepresent, so they carry their own fields.

| Store | Payload | Extra |
| --- | --- | --- |
| `vesselStore` | `VesselState \| null` | `vesselId`, `blueprint`, `setVessel`, `clearVessel` |
| `aisStore` | `AisTarget[] \| null` | full replacement per frame |
| `sicStore` | `SicFramesResponse \| null` | `version`, `selectedHorizon`, `setHorizon`, `setManifest` |
| `icebergStore` | `Iceberg[] \| null` | — |
| `weatherStore` | `WeatherPoint \| null` | — |
| `alarmStore` | `Alarm[] \| null` | `ackLocal(id)` (optimistic) |
| `routeStore` | `RouteRun \| null` | `history`, `setHistory` |
| `dataStore` | — | `versions`, `apiStatus`, `wsStatus`, setters |
| `uiStore` | — | `mode`, `projection`, `followShip`, `layerVisibility`, `layerOpacity` |
| `userStore` | — | `user`, `token`, `status`, `error`, `signIn`, `signOut`, `refresh`, `clearSession` |
| `shipsStore` | — | `list`, `loading`, `error`, `loadedAt`, fetch/create/patch/remove, `reset` |

`dataStore.apiStatus` starts `'down'` and `wsStatus` starts `{}` — hence the
`API: down / WS: closed` badge before anything connects.

### Staleness

`src/config/constants.ts` holds the thresholds (seconds):

| Key | Threshold | Cadence label |
| --- | --- | --- |
| `GPS` | 5 | Real-time |
| `AIS` | 60 | Real-time |
| `weather` | 1800 | 5 minutes |
| `SIC` | 129600 | Daily |
| `icebergs` | 172800 | Daily |
| `route` | 21600 | 6 hours |
| `enc` | 2592000 | — |

```ts
const { isStale, isMissing, ageSeconds } = useStaleness('GPS');
```

`isMissing` = never received → empty state, red health dot. `isStale` = older
than threshold → render faded with a yellow STALE badge. The hook re-evaluates
every second so a source crosses into STALE without a manual refresh.

Also in `constants.ts`: `UPDATE_CADENCE`, `VERSION_POLL_INTERVAL_MS`
(600 000), `WS_RECONNECT_BASE_MS` (1 000), `WS_RECONNECT_MAX_MS` (30 000),
`STALENESS_TICK_MS`, `FOLLOW_SHIP`. Tune thresholds there, not in components.

### Version poller

`startVersionPoller(intervalMs)` polls `GET /api/version` immediately and then
every `VERSION_POLL_INTERVAL_MS`, emitting `(version, changed)` to
`onVersionChange` subscribers. Errors are logged and swallowed — a backend
outage must not surface as an unhandled rejection.

The poller is deliberately **side-effect free**: it touches no store. Part 2
wires `onVersionChange` → store refetches in `App.tsx`. Note that the first
successful poll has no prior snapshot to diff against, so it reports **every**
key in `changed`; this lets first load and "republished" share one code path.

---

## Empty-state rule

The empty state is the default at first launch. Real data appears only when the
backend provides it.

- Missing numbers render `—` (`EM_DASH` in `src/utils/formatting.ts`), never `0`.
- `fmtNum` / `fmtCoord` / `fmtPosition` / `fmtTime` / `fmtAge` all return `—`
  for null, undefined, `NaN` and `Infinity`.
- `MapView` renders `Map unavailable — waiting for backend configuration` when
  the ROI fetch fails. It does not retry aggressively — the version poller and
  the API health signal own recovery.
- SIC will render a grey placeholder plus `SIC FORECAST UNAVAILABLE` when no
  frame loads or the version is > 36 h old. Part 2.

---

## Project structure

```
aurora-frontend/
├── index.html
├── package.json
├── tsconfig.json                 strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes
├── vite.config.ts                envPrefix: ['VITE_'], '@' -> src
├── tailwind.config.js            content: ./index.html, ./src/**/*.{ts,tsx}
├── postcss.config.js
├── .env.example                  VITE_API_BASE / VITE_WS_BASE
└── src/
    ├── main.tsx                  entry: BrowserRouter + StrictMode
    ├── App.tsx                   shell, chrome visibility, version poller lifecycle
    ├── router.tsx                11 routes behind RequireAuth / RequireVessel
    ├── index.css                 Tailwind layers, dark base theme
    ├── config/
    │   ├── constants.ts          thresholds, cadences, backoff, follow-ship
    │   ├── env.ts                VITE_* validation (throws if missing)
    │   └── projection.ts         LCC definition + proj4/OL registration
    ├── types/                    vessel ais iceberg route weather alarm version common,
    │                             auth (User, LoginResponse), ship (Vessel blueprint)
    ├── services/
    │   ├── api.ts                typed fetch client, ApiError, API_PATHS, auth + fleet
    │   ├── session.ts            token/user storage, intended path, 401 handler channel
    │   ├── websocket.ts          AuroraWebSocket + 5 channel singletons
    │   ├── dataSync.ts           boot: initial REST load, WS init, version + vessel refetch
    │   └── versionPoller.ts      10-min /api/version poller
    ├── stores/                   11 Zustand stores + createDataStore, wsBinding, toast
    ├── hooks/
    │   ├── useStaleness.ts       isStale / isMissing / ageSeconds + isSourceStale
    │   ├── useVesselRecord.ts    load one blueprint by id (loading / missing / failed)
    │   └── useWebSocket.ts       connect + dispatch to a store
    ├── map/
    │   ├── mapSetup.ts           createMap, applyProjectionPreset, setFollowShip
    │   ├── MapView.tsx           ROI, layer lifecycle, stale fade, projection, tick
    │   └── layers/               13 layers x {Source, Style, Layer} + index/types/shared
    ├── controls/                 ProjectionSwitcher, FollowShipToggle
    ├── components/               ViewNav, ToastHost, guards (RequireAuth/Vessel, AuthBridge),
    │                             VesselGate, ui/{Panel,Stat,Badge,EmptyState}
    ├── views/                    Operational / Planning / Analysis / Settings,
    │                             Login, ShipsOverview, AddShip, ShipDetail, shipSections
    ├── panels/                   StatusBar, Conning, Alarm, Route, Forecast, Freshness,
    │                             Legend, LayerManager, TimeSlider
    └── utils/                    formatting.ts, geo.ts
```

---

## Part 2

### Map layers

`src/map/layers/index.ts` is the single registry; `MapView` (creation order)
and `LayerManager` (display order) both read it.

| id | title | data source | palette keys | staleness | default |
|----|-------|-------------|--------------|-----------|---------|
| `enc` | ENC chart | `GET /api/enc/manifest` + raw S-57 cells, `@s57-parser/s57` → `toGeoJSON`, portrayed by `@s57-parser/s52-render` | S-52 verbatim (`background`, `land`, `shallowWater`, `deepWater`, `coastline`, `depthContour`, `hazard`, `text`, `restricted`, `light`) | `enc` | on |
| `coastline` | Coastline | `GET /api/coastline` GeoJSON | `coastline` | — | on |
| `grid` | Graticule | generated 5° lines + 10° labels | `depthContour`, `text` | — | off |
| `station` | Stations | `GET /api/stations` | `station` | — | on |
| `sic` | Sea ice | `GET /api/sic/frames` → `frame_url` `ImageStatic` | `sicIce` (+ `SIC_IMAGE_FILTER` on the canvas) | `SIC` | on |
| `sicUncertainty` | SIC uncertainty | `interval_url` (null → layer absent) | `uncertainty` (+ `UNCERTAINTY_IMAGE_FILTER`) | `SIC` | off |
| `icebergDrift` | Drift cones | `drift_cone` GeoJSON polygon, verbatim | `iceberg` | `icebergs` | on |
| `iceberg` | Icebergs | `GET /api/icebergs/current` | `iceberg` | `icebergs` | on |
| `routeAlt` | Alternative routes | `RouteRun.routes` minus the recommended one | `routeAlt` | `route` | on |
| `route` | Recommended route | `RouteRun.routes` where `is_recommended` | `route` | `route` | on |
| `alarmZone` | Alarms | `payload.zone ?? payload.geometry` (never inferred) | `alarm.critical` / `alarm.warning` / `alarm.caution` | — | on |
| `ais` | AIS targets | `WS /ws/ais` | `ais.none` / `.low` / `.medium` / `.high` | `AIS` | on |
| `ownShip` | Own ship | `WS /ws/vessel` | `vessel` | `GPS` | on |

Z-order is documented in `layers/index.ts`: chart 10–20, reference 30,
rasters 40–41, routes 55–60, positions 70–85, alarms 90, own ship 95.

### Panels

| panel | reads | notes |
|-------|-------|-------|
| `StatusBar` | `vesselStore`, `dataStore` (api/ws), `useStaleness` ×7 | health dot per source, `NO GPS` past 5 s |
| `ConningPanel` | `vesselStore`, `weatherStore` | own-ship instruments + metocean, em dash for null |
| `AlarmPanel` | `alarmStore`, `api.ackAlarm` | severity order from the store, optimistic ack |
| `RoutePanel` | `routeStore` | candidate table + `is_recommended` callout |
| `ForecastTable` | `routeStore`, `icebergStore` | waypoint rows; ice = nearest iceberg ≤100 nm |
| `DataFreshnessPanel` | `useStaleness` ×7 + every store's `error` | drawer, opened from the operational view |
| `LegendPanel` | `uiStore.displayMode`, `LAYERS` | swatches read the live palette |
| `LayerManager` | `uiStore.layerVisibility` / `layerOpacity` | grouped by `CATEGORY_ORDER` |
| `TimeSlider` | `sicStore.setHorizon` | D+1 / D+2 / D+3, matches a published frame only |

### Wiring

- **Boot** — `initDataSync()` in `App`: one `Promise.allSettled` REST load of
  every store, then each store's `init()` connects its WebSocket channel
  (`vessel`, `ais`, `weather`, `route`, `alarms`), then it subscribes to the
  version poller. Individual failures are recorded on the owning store rather
  than failing the boot.
- **Version → refetch → toast** — `onVersionChange` refetches only the store
  whose key changed and raises `SIC forecast updated` / `Iceberg positions
  updated` / `Weather updated` / `Chart cells updated`. The first poll reports
  every key as changed and is deliberately swallowed. Nothing reloads the page
  or discards view state.
- **Route update** — a pushed run with a new id toasts *Route updated — review
  N alternatives*, and `routeLayer` restarts a 500 ms reveal
  (`startRouteTransition`, a rAF loop driving `layer.changed()` because
  OpenLayers does not re-run style functions on the passage of time).
- **AIS ageing** — targets fade to 50 % past `FADE_AFTER_SECONDS` and are
  dropped past `REMOVE_AFTER_SECONDS`; colour comes from the backend `risk`
  field. The layer opts into `recomputeOnTick` so ageing happens while the map
  is otherwise idle.
- **Own ship** — `NO GPS` in the status bar and a 50 % opacity fade on the
  layer past `STALENESS_THRESHOLDS.GPS` (5 s), detected by `isSourceStale` on
  the same 1 Hz tick that ages AIS.
- **Analysis** — Recharts `LineChart` over route-run history (fuel estimate and
  risk score of the recommended route per run).

### Known gaps (shown as gaps, not filled with invented data)

- **ForecastTable SIC / wind / wave** are `—`: no endpoint returns a
  per-waypoint forecast. The footnote on the panel says so.
- **`currents` has no consumer store.** A republished `currents` version is
  logged, not toasted, because no panel reads it.
- **Analysis does not chart SIC or UKC** — neither has a time series in the API
  (SIC is three discrete horizon frames, UKC is a latest reading).

---

## Part 3 — Authentication and fleet

The fleet pages, the session, and the `/:vesselId` route contract. Everything
map- and panel-related is untouched; views gained a gate, not new internals.

### Routes

| Path | Guard | Page |
| --- | --- | --- |
| `/login` | — (redirects away if signed in) | `LoginPage` |
| `/` | — | redirects to `/ships` |
| `/ships` | `RequireAuth` | `ShipsOverviewPage` |
| `/ships/new` | `RequireAuth` | `AddShipPage` |
| `/ships/:id` | `RequireAuth` | `ShipDetailPage` |
| `/ships/:id/edit` | `RequireAuth` | `AddShipPage` (same component) |
| `/map/:vesselId` | `RequireAuth` + `RequireVessel` | `OperationalView` |
| `/planning/:vesselId` | `RequireAuth` + `RequireVessel` | `PlanningView` |
| `/analysis/:vesselId` | `RequireAuth` + `RequireVessel` | `AnalysisView` |
| `/settings/:vesselId` | `RequireAuth` + `RequireVessel` | `SettingsView` |
| anything else | — | redirects to `/ships` |

`RequireAuth` stores `pathname + search` in `sessionStorage` before
redirecting, so a 401 from inside a map view and a plain first visit both
land where the operator was heading after sign-in.

`RequireVessel` only checks that the URL segment *is* a number. Whether that
vessel exists is decided by `VesselGate`, because a guard cannot tell
"deleted" from "backend unreachable" and must not claim the former.

### Stores

| Store | Owns |
| --- | --- |
| `userStore` | `user`, `token`, `status`, `error`; `signIn`, `signOut`, `refresh`, `clearSession` |
| `shipsStore` | `list`, `loading`, `error`, `loadedAt`; `fetchShips`, `fetchShip`, `createShip`, `patchShip`, `removeShip`, `reset` |
| `vesselStore` | existing `VesselState` telemetry **plus** `vesselId`, `blueprint`, `setVessel`, `clearVessel` |

`userStore` hydrates from `localStorage` **at module load**, not in an effect.
An effect-based restore would bounce a reloading operator to `/login` for one
frame — acceptance step 6 requires the session to survive a reload.

`vesselStore.setVessel` clears the telemetry slice when the id changes: live
state from the previous ship must never be plotted against the new ship's
blueprint.

### Vessel wiring

Each of the four views wraps its content in `VesselGate`, which fetches
`GET /api/vessels/:id`, calls `setVessel`, and renders a blocking panel
(loading / not found / not loaded, with **Retry** and **Back to fleet**) until
the blueprint is in the store. The map and the panels are not mounted until
then.

`dataSync` reads `vesselStore.vesselId` at call time for
`getRouteCurrent` / `getAlarmsActive` / `getWeatherAtVessel`, and subscribes
to vessel changes so switching ship re-fetches those three immediately instead
of waiting for the next version poll. With no vessel selected the first load
is unscoped and is superseded by that subscription.

`StatusBar` shows `blueprint.name` (with `vessel_id` beside it) and the
signed-in email with **Sign out**, which clears the session, the fleet cache
and the selected vessel, then returns to `/login`.

### Vessel blueprint sheet

`src/views/shipSections.ts` is the single description of the eight sections —
27 fields, labels, units, required flags and tooltips. Both `AddShipPage`
(validation, controls) and `ShipDetailPage` (read-only mirror) render from it,
so "what I typed" and "what I saved" can never use different words.

Validation is zod (`react-hook-form` + `@hookform/resolvers`). Numbers arrive
via `setValueAs`, where blank and garbage both become `undefined`: optional
fields then validate as "not provided", required ones fall through to
`Enter a number`. Empty text means *not provided*, never `0`.

### Known gaps (Part 3)

- **The backend does not exist.** No auth, no vessels endpoints, no seed user.
  Every network call fails honestly: the fleet page shows its retry banner, the
  vessel gate shows "Vessel not loaded", the sign-in form shows
  "Cannot reach the AURORA backend. Is it running?". Nothing is faked to make
  the pages look populated.
- **The 13-step browser acceptance is deferred** until the API exists. What
  was verified instead is listed under "Verification status".
- **"Last used" on a fleet card is `updated_at`.** The database has no
  usage-tracking column and the brief forbids inventing fields beyond the
  schema, so the most recently touched timestamp stands in and reads "Never"
  when the record has never been stamped.
- **`getRouteHistory` is not vessel-scoped.** The brief scoped current route,
  alarms and weather; history has no `vessel_id` parameter in the contract.

---

## Deviations from the Part 1 brief

Recorded so they are not mistaken for oversights:

1. **`ol/extent.fit` does not exist in OpenLayers 9.** The brief asked for it;
   OL 9 removed it from the public API. `createMap` uses `View.fit(extent, {
   size, padding })`, which is the supported equivalent and is wrapped in
   try/catch so a zero-size container cannot break map construction.
2. **`getMap(): Map | null`.** The brief specified `ol.Map`. It must be nullable
   — no map exists before `createMap` runs — and lying about that would push a
   null check into every Part 2 call site.
3. **`@types/node` added as a dev dependency.** Required for `node:url` in
   `vite.config.ts`.
4. **`@types/proj4` is a deprecated stub** (proj4 ≥ 2.8 ships its own types) and
   is kept only because it was explicitly requested. It shadows nothing.
5. **`proj4js-definitions` is not installed** — it was absent from the Part 1
   dependency list. `+datum=WGS84` resolves from proj4's built-in WGS84 datum, so
   the LCC definition is complete. Add it if the backend needs extra EPSG codes.
6. **Tailwind pinned to 3.4.** `npx tailwindcss init -p` and the `content`
   array are v3 APIs; v4 replaces them with `@tailwindcss/postcss` and
   `@import "tailwindcss"`. The two config files were written directly rather
   than by the CLI, which is equivalent output.
7. **Types use named GeoJSON imports** (`import type { LineString } from
   'geojson'`). `@types/geojson` declares `export as namespace GeoJSON`, so a
   bare `GeoJSON.X` reference resolves to that global instead of the re-export in
   `types/common.ts`, and TypeScript then flags the import as unused. The
   re-export in `common.ts` is preserved as specified.
8. **`enc` has a store (`encStore`), added in Part 2** — the manifest is a real
   endpoint (`GET /api/enc/manifest`), so `useStaleness('enc')` now reports
   real freshness instead of the permanent "missing" of Part 1.
9. **`MapView` is mounted by `OperationalView` and `PlanningView`.** It is the
   same component and the same store state; each route owns its own map
   instance so a view switch tears the old one down rather than leaking it.
10. **`dataStore.setApiStatus` takes the `ApiStatus` union**, not `string`, so a
    typo is a compile error.
11. **A local `.env` exists** so the app runs immediately in this workspace. It
    is gitignored; `npm run dev` on a fresh clone needs `cp .env.example .env`.

### Part 2 deviations

12. **WGS84 is declared as OpenLayers' *user projection*, and `View` takes
    lon/lat because of it.** `declareUserProjection()` calls
    `setUserProjection('EPSG:4326')`, so every `View` entry point that runs
    through `fromUserCoordinate` — `setCenter`, `fit`, `animate`,
    `calculateExtent`, the constructor — expects **lon/lat**, not LCC metres.
    The `toLCC()` calls this implied were double transforms and were removed.
    Consequences verified against the OL 9 sources:
    - `MousePosition` *overrides* (does not chain) its transform when a user
      projection exists, so it always renders lon/lat and its `projection`
      option is inert (kept for intent).
    - **Image layers ignore the user projection** — `ImageStatic` and its
      renderer never call `getUserProjection()` — so `imageExtent` must be in
      view-projection units. `imageExtentFor()` passes `frame_extent` through
      verbatim under LCC and round-trips it (`LCC → WGS84 → view`) otherwise.
13. **`ol/layer/Graticule` is not used.** It exposes no public setter for its
    per-feature line style, so a display-mode restyle would silently leave the
    graticule in the day palette. The grid is generated as an ordinary
    `VectorSource` (`grid/gridSource.ts`) so `restyle` works like every other
    layer.
14. **`LayerGroup` has no `addLayer`/`removeLayer`.** Layers are pushed and
    removed on `group.getLayers()`, its `Collection`.
15. **`VectorSource`/`VectorLayer` generics are the *feature* type**, not the
    source type, and `VectorSource` has no `projection` option — geometries are
    lon/lat and the user projection does the rest.
16. **Staleness fades by multiplication:** effective opacity is
    `layerOpacity(layer) × STALE_LAYER_OPACITY` when the layer's
    `stalenessKey` is stale, so a manual opacity slider and the stale rule
    compose instead of one overwriting the other. Detection lives in
    `isSourceStale()` (non-hook) because OpenLayers sets opacity outside
    React's render cycle.
17. **`ForecastTable`, `AnalysisView` and the `currents` version key show
    gaps rather than filled-in numbers** — see "Known gaps" above. No
    endpoint was invented to close them.
18. **`Panel` takes an optional `className` forwarded to its shell.** Part 1's
    `PanelProps` had it, but the individual panels did not pass it through,
    which made flex/grid placement impossible from a view.

### Part 3 deviations

19. **`getRouteCurrent`, `getAlarmsActive` and `getWeatherAtVessel` gained an
    optional `vesselId`.** The brief says to pass it; the Part 1 signatures
    took none. Optional keeps every existing unscoped call site compiling and
    lets the first boot load before a vessel is chosen.
20. **Network failures are not wrapped in `ApiError`.** `fetch` rejections
    propagate untouched, so an unreachable backend is never mistaken for a
    rejected credential and cannot sign the operator out mid-work.
21. **The console chrome is hidden while signed out.** The brief specified the
    `/login` redirect; it did not say the status bar, health dots and view nav
    should sit beside the sign-in form advertising controls nobody can use.
22. **`ViewNav` disables the four view links until a vessel is selected**,
    instead of linking to routes `RequireVessel` would immediately bounce back
    from. A "Fleet" entry was added for the same reason: `/ships` is now a
    real destination, not a page you can only reach by the logo.
23. **Session in `localStorage`, intended path in `sessionStorage`.** The
    session must survive a reload (step 6); where the operator was heading
    must not survive a browser restart, or a stale path from last week would
    catch them after sign-in.
24. **Add and edit are one component** (`AddShipPage`, keyed on
    `vessel?.id ?? 'new'`). The brief listed them as separate pages; two
    copies of a 27-field sheet is two places for a validation rule to drift.

---

## Verification status

- `npx tsc --noEmit` — passes, zero errors, strict mode (`noUnusedLocals`,
  `noUnusedParameters`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`).
- `npm run build` — passes (`tsc --noEmit && vite build`).
- ROI/`projection` maths — verified numerically: `[35, -55]` → `[0, 0]` metres
  under `EPSG:9802`, inverse returns `[35, -55]`.
- **Headless-Chrome checks (CDP harness) pass with zero uncaught exceptions**
  against a stopped backend. Observed:
  - `/` → `/login`; the login page carries no status bar and no view nav.
  - Submitting valid-shaped credentials with the backend down leaves the
    operator on `/login` with `Cannot reach the AURORA backend. Is it running?`.
  - With an injected session, `/ships` renders, shows the error banner plus
    **Retry**, and *not* an "add your first vessel" empty state.
  - `/map/1` without a session → `/login`. With a session and the backend down
    → `Vessel not loaded` + `Failed to fetch` + **Retry** + **Back to fleet**.
  - `/ships/new` renders 8 sections, 27 inputs and 40 tooltips. An empty
    submit produces 13 field errors; a fully populated submit produces none
    and fails honestly at the network with the banner alert.
  - Reload keeps the session; **Sign out** returns to `/login` and empties
    `aurora.token` / `aurora.user`.
- **Still blocked on the backend** (deferred, not skipped): the 13-step
  acceptance list — real login, vessel CRUD round-trip, route/alarms/weather
  actually scoped by `vessel_id`, and the SIC frame renderer from ISSUE 1.
- **Map layers in-browser** remain partially unobservable for the same
  reason: `createMap()` never runs while `GET /api/roi` fails, so the
  day/dusk/night chrome switch is verified on the shell but the canvas is not.

## Licence

MIT — see `../LICENSE`.
