# aurora-forecaster

The **inference kernel of the AURORA system**: a pure Python library that
turns a 5-day input tensor into a 3-day Antarctic sea-ice concentration (SIC)
forecast. A 5-day input tensor goes in, a 3-day SIC forecast comes out.

* No I/O beyond the frozen artifacts loaded once at import.
* No scheduling, no state, no network, no database, no rendering, no reprojection.
* No training code in the runtime path — the model is frozen and is never
  retrained or modified here.

```
from forecaster import predict, ForecastOutput

output = predict(input_tensor)      # [5, 10, 101, 361] -> ForecastOutput
```

That is the entire public API. Everything else in `src/` is internal.

## Repository layout

```
forecaster/
├── src/                  # the installable package (mapped to import name `forecaster`)
│   ├── __init__.py       # public exports: predict, ForecastOutput, ConvLSTM*
│   ├── model.py          # ConvLSTMCell + ConvLSTMForecaster (verbatim copy)
│   ├── predict.py        # predict() + ForecastOutput
│   ├── conformal.py      # frozen stratified conformal intervals
│   ├── confidence.py     # frozen p33/p66 confidence classes
│   ├── scaler.py         # frozen train-period standardization
│   ├── artifacts_loader.py  # the ONLY filesystem reader; loads once, caches
│   └── constants.py      # ROI, channel order, thresholds — no hardcoded numbers
├── artifacts/            # frozen weights + stats (see "Artifacts")
├── training/             # archival copy of the training/eval scripts — NOT imported
├── tests/                # pytest suite
├── pyproject.toml
├── __init__.py           # repo-root import shim (see note below)
└── README.md
```

`training/` is a **copy** of the original training/eval scripts
(`preprocess.py`, `dataset.py`, `run_final.py`, `eval.py`, `conformal_3f.py`,
`inference_2026.py`) kept for provenance. Nothing in `src/` imports it; it is
not part of the installed package.

> **Note — `forecaster/__init__.py` (repo-root shim).** The installable
> package lives in `src/` and is mapped onto the import name `forecaster`
> by `pyproject.toml` (`package-dir = {"forecaster" = "src"}`). When the
> *repository root* is itself on `sys.path` (e.g. `uvicorn` or
> `python -m pytest` started from the repo root) Python would otherwise
> resolve `import forecaster` to this directory as an empty namespace
> package, so the shim re-exports exactly the same public API. It contains
> no logic.

## Public API

```python
from forecaster import predict, ForecastOutput

output = predict(input_window)                      # defaults
output = predict(input_window, return_uncertainty=False)
```

| Name | Kind | Signature |
|------|------|-----------|
| `predict` | function | `predict(input_window: np.ndarray, return_uncertainty: bool = True) -> ForecastOutput` |
| `ForecastOutput` | dataclass | `median, combined_std, q05, q95, interval_half_width, confidence_class, metadata` |
| `ConvLSTMForecaster` | `nn.Module` | `(in_channels=10, hidden_channels=(32, 64), kernel_size=3)`, `[B,5,10,H,W] -> [B,3,H,W]`, 270,147 params (asserted at import) |
| `ConvLSTMCell` | `nn.Module` | `(input_channels, hidden_channels, kernel_size=3)` |

Nothing else is part of the public API.

## Input contract

`input_window` — `np.ndarray`, shape **`[5, 10, 101, 361]`**
(lookback days × channels × lat × lon), on the ROI grid
(lon −10°…80°E, lat −75°…−50°S, 0.25°, `constants.ROI_*`).

Any dtype is accepted and cast to `float32`; the array is **copied**, never
modified in place. The wrong shape raises `ValueError` naming the expected
shape. Cells may contain `NaN` (no-data/land) — they are replaced with `0`
*after* standardization, exactly as in training, and the count is logged.

Channels are in **raw physical units**, in the frozen order
(`constants.CHANNEL_NAMES`):

| # | Channel | Units | Standardization applied here |
|---|---------|-------|------------------------------|
| 0 | SIC | 0–1 | `(x - sic_mean) / sic_std` (`sic_mean.npy`/`sic_std.npy`) |
| 1 | u10 | m s⁻¹ | per-channel mean/std from `norm_stats.json` |
| 2 | v10 | m s⁻¹ | " |
| 3 | t2m | K | " |
| 4 | uo | m s⁻¹ | " |
| 5 | vo | m s⁻¹ | " |
| 6 | thetao | K | " |
| 7 | so | g kg⁻¹ | " |
| 8 | zos | m | " |
| 9 | SIC_prev_year | 0–1 | same scalars as channel 0 |

## Output contract

`ForecastOutput`, every field shaped `[3, 101, 361]` (day-1, day-2, day-3):

| Field | dtype | Range | Meaning |
|-------|-------|-------|---------|
| `median` | float32 | [0, 1] | Ensemble mean of the 3 per-seed MC-Dropout means. The point forecast. |
| `combined_std` | float32 | ≥ 0 | `sqrt(ens_std² + mc_std_avg²)` — ensemble spread + MC-Dropout spread. |
| `q05` | float32 | [0, 1] | `median − 1.645·combined_std`, clipped. **Raw Gaussian bound, not the conformal interval.** |
| `q95` | float32 | [0, 1] | `median + 1.645·combined_std`, clipped. Raw Gaussian bound. |
| `interval_half_width` | float32 | 0.00206 / 0.12617 | **Frozen stratified conformal half-width — the authoritative interval:** `[median − hw, median + hw]` clipped to [0, 1]. |
| `confidence_class` | uint8 | 0/1/2/255 | 0 = HIGH, 1 = MEDIUM, 2 = LOW (ice cells binned by frozen p33/p66 of `combined_std`), 255 = invalid cell. Valid open-ocean cells (median ≤ 0.15) default to HIGH. |
| `metadata` | dict | — | `model_version`, `seed_count` (3), `mc_passes` (20), `artifacts_path`, `predict_timestamp` (ISO-8601, recorded only — never used in any computation). |

Guarantees:

* **Deterministic** — `torch.manual_seed(0)` at the top of every call, so the
  20 MC-Dropout passes are reproducible for the same input.
* **Finite** — every field is checked before return; a `NaN`/`inf` raises
  `RuntimeError` with the cell coordinates instead of being returned.
* **Stateless** — no state between calls; a forecast is never fed back in as
  input. Each `predict()` is independent.
* **Bounded** — `median`, `q05`, `q95` are clipped to [0, 1] (the sigmoid head
  already bounds them; clamping is logged if it ever moves cells).
* `return_uncertainty=False` runs a single forward pass per seed and
  zero-fills `combined_std`, `q05`, `q95`, `interval_half_width`,
  `confidence_class`. Only use it if you do not consume those fields.

Uncertainty internals: 3 seeds × 20 MC-Dropout passes → per-seed mean/var →
ensemble mean/std, combined as above (same recipe as the original
`inference_2026.py` / `eval.py`).

## Artifacts

All artifacts live in `artifacts/` and are loaded **once**, at import time,
by `src/artifacts_loader.py` — the only module in the package that touches
the filesystem. `predict()` reads nothing.

| File | Source (original location) |
|------|----------------------------|
| `final_10ch_3f_seed{0,1,2}/best_model.pt` | `backend/runs/final_10ch_3f_seed{0,1,2}/best_model.pt` |
| `sic_mean.npy`, `sic_std.npy`, `norm_stats.json` | `backend/data/processed/` |
| `metrics_2025.json` (frozen conformal quantiles) | `backend/cache/metrics_2025.json` |
| `valid_mask.npy` | `backend/cache/valid_mask.npy` |
| `confidence_thresholds.json` (frozen p33/p66) | `frontend/data/confidence_thresholds.json` |

The artifact directory is resolved as: explicit argument → `SIC_ARTIFACTS_PATH`
environment variable → `<package>/artifacts`. The loaded instance is cached in
a module-level singleton, so repeated `predict()` calls never reload weights.

> Installed as editable (`pip install -e .`) — the supported mode — the package
> resolves `<package>/artifacts` inside this checkout. For a wheel install, or
> to point at a different artifact set, set `SIC_ARTIFACTS_PATH`; the package
> never searches for artifacts on its own.

**Missing artifacts raise.** If any file is absent, `FileNotFoundError` is
raised with the exact path; conformal quantiles and confidence thresholds
never fall back to hardcoded or recomputed values (the coverage guarantee
would silently break).

> **TODO (only if a file disappears):** `confidence_thresholds.json` is the
> one artifact historically at risk of being missing. It exists today — no
> artifact was stubbed while building this package. If it is ever removed,
> do **not** invent thresholds: regenerate them from the frozen 2026 test
> distribution (`p33`/`p66` of `combined_std` over ice cells) and commit the
> file; until then `predict()` will refuse to run with a clear error.

## What the backend does around this library

The forecaster is a leaf dependency. The backend owns everything else:

1. **Assemble the input window** with persistence fill — SIC is anchored to
   real observations, *never* to prior forecasts (no forecast feedback).
2. **Call `predict()` once per day** with the `[5, 10, 101, 361]` window.
3. **Apply the staleness penalty to `interval_half_width`** — the backend
   widens intervals for stale forcing; the frozen conformal quantiles
   themselves are never touched.
4. **Reproject to LCC and render PNGs** — the library returns arrays in ROI
   lat/lon; reprojection and rendering are backend/frontend concerns.
5. **Persist frames and bump the version.**
6. Optionally classify staleness/freshness, schedule runs, talk to databases
   or download forcing data — none of which this package does.

## Known limitations

* **Day-3 is worse than persistence** (ratio 1.11 / 1.03 in 2025 / 2026);
  day-2 is at best parity. The product defaults to day-1/day-2.
* **MIZ-only coverage dropped from 0.959 to 0.880 in 2026** when the frozen
  2025 quantiles met a harder season (all-valid coverage stayed calibrated).
* **Coastal NaN band** within ~50–100 km of the coastline (NSIDC CDR v6 land
  contamination) — no training signal there; `valid_mask` marks these cells
  and `confidence_class` reports them as 255.
* **25 km resolution does not resolve leads** (1–10 km) or fine MIZ structure.
* **Single region:** 10°W–80°E only; other sectors would need retraining.
* **Reanalysis latency is not simulated** — training used same-day ERA5.

## What this package NEVER does

Enforced by tests (`tests/test_no_io.py` and friends) and by design:

1. **Never reads data from the filesystem at runtime**, except the frozen
   artifacts loaded once at import.
2. **Never knows the current date.** The function only sees the 5-day tensor;
   `datetime.now(timezone.utc)` is recorded as `predict_timestamp` metadata
   and never used in a computation.
3. **Never imports from `backend/` or `frontend/`** — it is a leaf dependency.
4. **Never downloads data** — no `httpx`, `requests`, `urllib`, `cdsapi`,
   `earthaccess`, `copernicusmarine`.
5. **Never writes to a database** — no SQLAlchemy, psycopg, Redis.
6. **Never renders PNGs** — no matplotlib, Pillow, rasterio. The backend
   renders; this package returns arrays.
7. **Never reprojects** — no pyproj, no pyresample. The tensor is in ROI
   lat/lon; the backend converts to LCC.
8. **Never schedules itself** — no APScheduler, cron, `threading.Timer`.
9. **Never widens intervals for staleness** — the conformal quantiles are
   frozen; the backend applies the staleness penalty after receiving output.
10. **Never retrains** — no optimizer, no `loss.backward()`, no training loop
    in the runtime path. Training lives in `training/` and is not imported.
11. **Never feeds forecast output back as SIC input** — `predict()` takes an
    input window and returns an output; it stores no state between calls and
    each call is independent.
12. **Never modifies the input tensor in place** — it is copied before
    standardizing.
13. **Never returns `NaN` or `inf`** — every output field is asserted finite
    before return; a violation raises `RuntimeError` with the cell
    coordinates.

Dependency allowlist (`pyproject.toml`): `numpy>=1.24`, `torch>=2.0`. Nothing
that could do I/O, network, database, or visualization is declared.

## Tests

```
cd forecaster
pip install -e .[dev]
pytest tests/ -v
```

| Test | Checks |
|------|--------|
| `test_artifacts_load.py` | complete artifact set loads; each missing file raises `FileNotFoundError` with its path |
| `test_predict_shape.py` | end-to-end zero-input forecast: shapes, dtypes, finiteness, [0, 1] bounds, metadata |
| `test_predict_errors.py` | wrong lookback/channel/spatial shapes raise `ValueError`; `int32` input is cast |
| `test_conformal.py` | frozen quantiles load; stratified half-width applied per cell (median *and* true-SIC stratum selectors) |
| `test_confidence.py` | p33/p66 bins → 0/1/2, invalid → 255, open ocean → HIGH, missing file raises |
| `test_no_forecast_feedback.py` | two calls with the same input are bitwise identical; input is never mutated |
| `test_no_io.py` | static scan of `src/` for forbidden imports/constructs (training/ exempt) |

All tests run against the real frozen artifacts.
