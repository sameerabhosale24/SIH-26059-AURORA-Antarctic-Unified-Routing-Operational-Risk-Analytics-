# AURORA backend

FastAPI service behind the AURORA console: authentication, vessel management,
the Antarctic data infrastructure (ingest → regrid → input window → forecast →
display), the A* route optimiser, the alarm rules, the REST resources the map
reads, five WebSocket channels, the GPS/AIS relays, and `GET /api/health`.

## Run

```bash
docker compose up -d          # from the repo root: aurora-postgres + aurora-redis
cd backend
pip install -r requirements.txt
python -m alembic upgrade head
python scripts/seed_stations.py        # data/stations.json  → GET /api/stations
python scripts/download_coastline.py   # data/coastline.geojson → GET /api/coastline
python scripts/seed_demo_user.py       # operator@aurora.demo / aurora123
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Windows shortcut: `start-api.cmd`.

Then:

```bash
curl http://127.0.0.1:8000/api/health
```

## Layout

```
backend/
  app/
    main.py            FastAPI app, lifespan (DB/Redis/forecaster probes,
                       scheduler, relay tasks), /api/health
    config.py          Settings, read from the environment then .env
    api/
      auth.py, vessels.py   accounts and blueprints
      reference.py          /roi /stations /coastline /enc/*
      version.py            /version
      sic.py                /sic/frames, /sic/frame/{day}/{file}
      telemetry.py          /vessel/latest, /ais/latest
      route.py              /route/current /route/history /route/accept
      icebergs.py           /icebergs/current
      weather.py            /weather/vessel
      alarms.py             /alarms, /alarms/{id}/ack
      scope.py              which ship a request is about (ownership rules)
    schemas/           Pydantic response models, one per resource
    ws/                the five WebSocket channels and their Redis fan-out
    adapters/          one module per data source; the only place that knows
                       about NSIDC / ERA5 / CMEMS / CS2SMOS / IBCSO / BYU / ENC
    services/
      field_storage.py     the on-disk store: fields/<source>/YYYY-MM-DD.npy
      input_assembly.py    [5, 10, 101, 361] window + staleness record
      display_pipeline.py  9 PNG frames per forecast + manifest.json
      sic_scheduler.py     the daily cycle: fetch → regrid → predict → render
      version_service.py   data_version bookkeeping (synchronous, by design)
      route_optimizer.py   cost grid, hard blocks, A*, metrics, Pareto variants
      route_service.py     route/run persistence and serialization
      alarm_engine.py      the seven rules (six alarm types)
      alarm_service.py     alarm list/ack/publish
      cpa_engine.py        closest point of approach and time to CPA
      iceberg_proximity.py latest sightings, drift cones, distance grid
      weather_poller.py    sample ERA5 at the own ship on a timer
      vessel_service.py    own-ship state writes and reads
      ais_service.py       AIS target writes, enrichment, publication
      storage_manager.py   retention and disk usage
      relays/              gps_relay (NMEA over TCP), ais_relay (AISStream)
    schedulers/        APScheduler jobs (see below)
    utils/             constants, grid, projection, rasters, geo — no hand-
                       rolled latitude vectors anywhere else
  alembic/             migrations
  data/                runtime output, gitignored (see below)
  scripts/             download_ibcso.py, download_coastline.py,
                       seed_demo_user.py, seed_stations.py
  tests/
```

## Data flow

```
adapters.fetch(day)          async, one per source, source-specific CRS
        │
        ▼
adapter.regrid(raw)          onto the single 0.25° ROI grid [101, 361]
        │
        ▼
field_storage.write_field    data/fields/{sic,weather,currents,ice_thickness}/YYYY-MM-DD.npy
        │
        ▼
input_assembly               data/fields/ only — forecasts are never an input
        │                    [5 days × 10 channels × 101 × 361] + staleness dict
        ▼
forecaster.predict           [3, 101, 361] median + interval + confidence
        │
        ▼
display_pipeline             data/sic_frames/<date>/*.png + manifest.json
                             data/sic_arrays/<date>/*.npy
```

The ROI grid is fixed by the forecaster's weights:

```
lat = -75.125 + arange(101) * 0.25      # row 0 is the SOUTHERN edge
lon = -10.125 + arange(361) * 0.25
```

`app/utils/grid.py` is the only place that constructs those vectors. Row 0 =
south is the convention every adapter writes and every renderer reads, so
anything that hands an array to GDAL has to declare a south-up transform.

## Scheduling

| Job | When | What |
|---|---|---|
| `job_sic_daily` | daily, `DAILY_JOB_HOUR` (03:00) | `run_sic_cycle()` — fetch, regrid, assemble, predict, render, publish. Clears `data/raw_temp/` before the first download |
| `job_thickness_weekly` | Mondays 04:00 | refresh CS2SMOS thickness |
| `job_freshness_check` | hourly | raise alarms when any configured source goes quiet |
| `job_route_optimize` | `ROUTE_JOB_HOURS` (00,06,12,18) | re-plan the own ship's route and publish the run |
| `job_alarm_pass` | every `ALARM_POLL_SECONDS` (60) | evaluate all seven rules; idempotent, so a still-true condition does not raise a second alarm |
| `job_cleanup_daily` | daily, `CLEANUP_JOB_HOUR` (04:00) | apply SIC frame retention, empty `raw_temp`, report disk usage |

The cycle can be driven by hand:

```bash
python -m app.services.sic_scheduler --dry-run            # no writes
python -m app.services.sic_scheduler --date 2026-03-15
python -m app.services.route_optimizer --vessel-id 1 --dry-run
```

Staleness gates (documented deviation): a source older than
`FORECASTER_MAX_STALENESS_DAYS` (7) still publishes, marked degraded; older
than `FORECASTER_DEGRADED_DAYS` (10) it does not publish and raises a
`forecast_stale` alarm. The thresholds are deliberately separate — the
prompt's single threshold could both forbid and require publishing on the
same day.

## Endpoints

| Method + path | Access | Answer when there is no data |
|---|---|---|
| `GET /api/health` | open | always 200 |
| `GET /api/roi`, `/api/version`, `/api/stations`, `/api/coastline`, `/api/enc/manifest`, `/api/sic/frames`, `/api/icebergs/current` | open | 204 (coastline), `[]`, `{}` |
| `GET /api/sic/frame/{day}/{file}` | open | 404 |
| `GET /api/vessel/latest`, `/api/weather/vessel` | session | 204 |
| `GET /api/ais/latest`, `/api/route/current`, `/api/route/history`, `/api/alarms` | session | `[]` |
| `POST /api/route/accept`, `/api/alarms/{id}/ack` | session | 404 |
| `POST /api/auth/*`, `/api/vessels/*` | as implemented in PART 1 | — |

Which ship a session is about is resolved by `app/api/scope.py`: an explicit
`?vessel_id=` is ownership-checked, otherwise the caller's own ship. An
operator with no vessels gets the empty answers above rather than someone
else's telemetry.

### WebSockets

`/ws/vessel`, `/ws/ais`, `/ws/alarms`, `/ws/weather`, `/ws/route` — each
sends the last known value on connect, then every Redis publication on its
channel. Messages carry no auth token, which is a known limitation: the
channels expose only what the same session would get over REST, but they are
not themselves authenticated.

## Storage

```
data/
  fields/sic/YYYY-MM-DD.npy            float32 [101, 361], NaN = no data
  fields/weather/YYYY-MM-DD.npy        float32 [3, 101, 361]
  fields/currents/YYYY-MM-DD.npy       float32 [5, 101, 361]
  fields/ice_thickness/YYYY-MM-DD.npy  float32 [C, 101, 361]
  fields/bathymetry.npy                static, positive-down depth
  sic_frames/<date>/{1_day_median.png, ..., manifest.json}
  sic_arrays/<date>/{median,uncertainty,actual}.npy
  stations.json                        written by scripts/seed_stations.py
  coastline.geojson                    written by scripts/download_coastline.py
  enc/                                 S-57 cells (none parsed yet)
  raw_temp/                            download scratch; emptied at fetch start
  raw_permanent/                       downloads worth keeping
```

All of `data/` is gitignored except the `.gitkeep` placeholders. Missing data
is `None` or NaN throughout — no path returns zeros for "unknown".

Retention is enforced in the database, not by the application:

| Table | Compressed after | Dropped after |
|---|---|---|
| `vessel_state` | 7 days (segmentby `vessel_id`) | 180 days |
| `ais_track` | 7 days (segmentby `mmsi`) | 30 days |

`data/sic_frames/` is trimmed to `SIC_FRAMES_RETENTION_DAYS` by
`job_cleanup_daily`. `GET /api/health` reports every subtree's size and
flags the ones over `WARN_SIC_FRAMES_MB` / `WARN_FIELDS_MB`.

## Configuration

`backend/.env` (never committed). Copy `.env.example`.

| Key | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | required services |
| `AURORA_JWT_SECRET` | required; the process refuses to start without it |
| `STORAGE_ROOT` | defaults to `./data` |
| `NSIDC_USERNAME/PASSWORD` | NSIDC Sea Ice Index |
| `CDSAPI_URL/KEY` | ERA5 / ERA5T |
| `CMEMS_USERNAME/PASSWORD` | CMEMS currents **and** CS2SMOS thickness |
| `AISSTREAM_API_KEY` | AIS live positions |
| `BYU_SCP_URL`, `GPS_HOST/PORT` | iceberg SCP, NMEA over TCP |
| `SIC_ARTIFACTS_PATH` | forecaster weights; auto-detected when unset |
| `FORECASTER_MAX_STALENESS_DAYS`, `FORECASTER_DEGRADED_DAYS` | publish gates |
| `OWN_SHIP_VESSEL_ID` | the ship the relays, route job and weather poller act on |
| `ROUTE_UKC_MARGIN_M`, `ROUTE_WEIGHT_*` | hard-block margin and cost weights |
| `ROUTE_JOB_HOURS`, `ROUTE_MAX_EXPANSIONS`, `ROUTE_ALT_MAX_OVERLAP` | planner cadence and bounds |
| `ALARM_CPA_NM`, `ALARM_OFF_COURSE_NM`, `ALARM_ICEBERG_NM` | rule thresholds |
| `ALARM_STALENESS_HOURS`, `ALARM_REARM_HOURS`, `ALARM_POLL_SECONDS` | staleness, re-arm, pass interval |
| `AIS_FRESHNESS_MINUTES`, `RELAY_RECONNECT_SECONDS` | AIS target lifetime, relay backoff |
| `SIC_FRAMES_RETENTION_DAYS`, `CLEANUP_JOB_HOUR` | frame retention job |
| `WARN_SIC_FRAMES_MB`, `WARN_FIELDS_MB` | disk-usage warning lines |

Every credential is optional. An adapter with no credentials is *not
configured*: it logs once, returns nothing, and is reported as such by
`/api/health`. No adapter ever fabricates a field.

## Testing

```bash
cd backend
python -m pytest tests -q
```

No PostgreSQL, Redis or network access is needed; `STORAGE_ROOT` is redirected
to a temporary directory per test. The suite covers the input window, the
display pipeline, the route planner (hard blocks, A*, infeasibility, variant
separation) and the alarm rules (each rule firing, and each rule staying
silent when its data is absent).
