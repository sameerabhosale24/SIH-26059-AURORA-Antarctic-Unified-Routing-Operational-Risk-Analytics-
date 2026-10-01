# AURORA backend

FastAPI service behind the AURORA console: authentication, vessel management,
the Antarctic data infrastructure (ingest → regrid → input window → forecast →
display), and `GET /api/health`.

Route optimisation, the WebSocket relays and the REST resource endpoints are
PART 2 and are not in this tree yet.

## Run

```bash
docker compose up -d          # from the repo root: aurora-postgres + aurora-redis
cd backend
pip install -r requirements.txt
python -m alembic upgrade head
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
    main.py            FastAPI app, lifespan (DB/Redis/forecaster probes, scheduler)
    config.py          Settings, read from the environment then .env
    api/               auth, vessels  (PART 2 adds routes, alarms, frames)
    adapters/          one module per data source; the only place that knows
                       about NSIDC / ERA5 / CMEMS / CS2SMOS / IBCSO / BYU / ENC
    services/
      field_storage.py     the on-disk store: fields/<source>/YYYY-MM-DD.npy
      input_assembly.py    [5, 10, 101, 361] window + staleness record
      display_pipeline.py  9 PNG frames per forecast + manifest.json
      sic_scheduler.py     the daily cycle: fetch → regrid → predict → render
      version_service.py   data_version bookkeeping (synchronous, by design)
    schedulers/        APScheduler jobs: daily SIC, weekly thickness, freshness
    utils/             constants, grid, projection, rasters — no hand-rolled
                       latitude vectors anywhere else
  alembic/             migrations
  data/                runtime output, gitignored (see below)
  scripts/             download_ibcso.py, seed_demo_user.py
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
| `job_sic_daily` | daily, `DAILY_JOB_HOUR` (03:00) | `run_sic_cycle()` — fetch, regrid, assemble, predict, render, publish |
| `job_thickness_weekly` | Mondays 04:00 | refresh CS2SMOS thickness |
| `job_freshness_check` | hourly | raise alarms when any configured source goes quiet |

The cycle can be driven by hand:

```bash
python -m app.services.sic_scheduler --dry-run            # no writes
python -m app.services.sic_scheduler --date 2026-03-15
```

Staleness gates (documented deviation): a source older than
`FORECASTER_MAX_STALENESS_DAYS` (7) still publishes, marked degraded; older
than `FORECASTER_DEGRADED_DAYS` (10) it does not publish and raises a
`forecast_stale` alarm. The thresholds are deliberately separate — the
prompt's single threshold could both forbid and require publishing on the
same day.

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
```

All of `data/` is gitignored except the `.gitkeep` placeholders. Missing data
is `None` or NaN throughout — no path returns zeros for "unknown".

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

Every credential is optional. An adapter with no credentials is *not
configured*: it logs once, returns nothing, and is reported as such by
`/api/health`. No adapter ever fabricates a field.

## Testing

```bash
cd backend
python -m pytest tests -q
```

No PostgreSQL, Redis or network access is needed; `STORAGE_ROOT` is redirected
to a temporary directory per test.
