"""Turn forecaster output into the frames the map consumes.

Nine frames per run — three horizons times three display modes — each with
a median, an uncertainty, and (when an observation exists) the observed
field and the difference.

The single hard requirement here is **NaN is transparent**. The SIC frame
is composited over the ENC base chart; a white or black box where the
coastline or the data gap is would read as ice to a navigator. Every code
path therefore routes NaN through ``cmap.set_bad(alpha=0)`` and
``savefig(transparent=True)``, and the test suite asserts the alpha channel.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.utils.constants import HORIZONS, LCC_PROJ, ROI_SHAPE
from app.utils.projection import reproject_roi_to_lcc

logger = logging.getLogger("aurora.display")

MODES = ("day", "dusk", "night")
FIELDS = ("median", "uncertainty", "actual", "diff")

#: Per-mode ramps. Day is green/yellow, dusk is muted green/amber, night is
#: red/orange — the night ramp keeps the bridge team's dark adaptation
#: intact, which is the entire reason three modes exist.
MODE_COLORS: dict[str, list[str]] = {
    "day": ["#0b3d1f", "#1f7a3f", "#5fbf6a", "#a8e05f", "#f2e44c", "#fff7b0"],
    "dusk": ["#3b2f1e", "#6b5630", "#9a8348", "#c4a55f", "#e0c073", "#f2e3b0"],
    "night": ["#3d0a0a", "#7a1414", "#b52a1a", "#e05a17", "#f39a2a", "#ffd18a"],
}

#: Diverging ramps for the difference field, white at zero.
MODE_DIFF_COLORS: dict[str, list[str]] = {
    "day": ["#1f7a3f", "#8fd19a", "#ffffff", "#f2e44c", "#d94801"],
    "dusk": ["#6b5630", "#a99372", "#ffffff", "#e0c073", "#8a4b1f"],
    "night": ["#b52a1a", "#e08a6a", "#ffffff", "#f39a2a", "#ffd18a"],
}

UNCERTAINTY_FLOOR = 0.02
DIFF_FLOOR = 0.05


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def frames_root() -> Path:
    return Path(get_settings().STORAGE_ROOT) / "sic_frames"


def arrays_root() -> Path:
    return Path(get_settings().STORAGE_ROOT) / "sic_arrays"


def frames_dir(day: date) -> Path:
    return frames_root() / day.isoformat()


def arrays_dir(day: date) -> Path:
    return arrays_root() / day.isoformat()


def frame_filename(horizon: int, mode: str, field: str) -> str:
    """``1_day_median.png`` — horizon is 1-based, mode and field are lower."""
    return f"{horizon}_{mode}_{field}.png"


def frame_url(day: date, horizon: int, mode: str, field: str) -> str:
    return f"/api/sic/frame/{day.isoformat()}/{frame_filename(horizon, mode, field)}"


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _cmap(mode: str, field: str):
    from matplotlib.colors import LinearSegmentedColormap

    colors = MODE_DIFF_COLORS[mode] if field == "diff" else MODE_COLORS[mode]
    cmap = LinearSegmentedColormap.from_list(f"aurora_{mode}_{field}", colors)
    cmap.set_bad(alpha=0)  # NaN renders fully transparent — never white/black
    return cmap


def _normalize(array: np.ndarray, field: str) -> tuple[float, float]:
    finite = array[np.isfinite(array)]
    if field in ("median", "actual"):
        return 0.0, 1.0
    if field == "uncertainty":
        peak = float(finite.max()) if finite.size else 0.0
        return 0.0, max(peak, UNCERTAINTY_FLOOR)
    # diff — symmetric around zero so "less ice" and "more ice" look equal.
    peak = float(np.abs(finite).max()) if finite.size else 0.0
    span = max(peak, DIFF_FLOOR)
    return -span, span


def _write_png(path: Path, array: np.ndarray, mode: str, field: str,
               extent_lcc: list[float]) -> None:
    """Render one LCC frame. ``extent_lcc`` is ``[xmin, ymin, xmax, ymax]``
    in projected metres — the array has already left geographic space, so
    lat/lon bounds would be meaningless here."""
    plt = _matplotlib()
    from matplotlib.colors import ListedColormap

    cmap = _cmap(mode, field)
    if not isinstance(cmap, ListedColormap) and not hasattr(cmap, "set_bad"):
        raise TypeError("colormap must support set_bad")

    masked = np.ma.masked_invalid(np.asarray(array, dtype=np.float64))
    vmin, vmax = _normalize(array, field)

    height, width = array.shape
    fig = plt.figure(figsize=(width / 100.0, height / 100.0), dpi=100)
    axes = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    left, bottom, right, top = extent_lcc
    axes.imshow(
        masked,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        origin="upper",
        interpolation="nearest",
        # imshow wants [left, right, bottom, top], not the rasterio order.
        extent=[left, right, bottom, top],
        aspect="auto",
    )
    axes.set_axis_off()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, transparent=True, dpi=100)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def render_frames(
    output,
    target_date: date,
    *,
    version: int,
    staleness: dict | None = None,
    penalty_applied: float = 0.0,
    interval_widened: bool | None = None,
    actual: np.ndarray | None = None,
) -> dict:
    """Render every frame for one forecast and write the manifest.

    Parameters
    ----------
    output
        Anything exposing ``median`` and ``interval_half_width`` as
        ``[3, 101, 361]`` arrays — in practice a ``ForecastOutput``.
    actual
        Observed SIC for the three horizons. Either ``[3, 101, 361]``, a
        single ``[101, 361]`` shared by all horizons, or ``None``. When
        ``None`` the ``actual``/``diff`` frames are skipped rather than
        rendered from fabricated observations.
    """
    median = np.asarray(output.median, dtype=np.float32)
    half_width = np.asarray(output.interval_half_width, dtype=np.float32)

    if median.shape != (HORIZONS, *ROI_SHAPE):
        raise ValueError(f"median must be {(HORIZONS, *ROI_SHAPE)}, got {median.shape}")
    if half_width.shape != median.shape:
        raise ValueError(
            f"interval_half_width shape {half_width.shape} does not match "
            f"median {median.shape}"
        )
    if interval_widened is None:
        interval_widened = penalty_applied > 0.0
    if staleness is None:
        staleness = {}

    actual_stack = _coerce_actual(actual, median.shape)

    day_dir = frames_dir(target_date)
    day_dir.mkdir(parents=True, exist_ok=True)
    array_dir = arrays_dir(target_date)
    array_dir.mkdir(parents=True, exist_ok=True)

    # One projection for the whole run: every horizon shares the ROI grid, so
    # the extent is identical across all nine frames.
    _, extent_lcc = reproject_roi_to_lcc(median[0])

    frames: list[dict] = []
    written: list[Path] = []
    for horizon_index in range(HORIZONS):
        horizon = horizon_index + 1  # 1-based in every filename and URL
        lcc_median, _ = reproject_roi_to_lcc(median[horizon_index])
        lcc_uncertainty, _ = reproject_roi_to_lcc(half_width[horizon_index])
        lcc_actual = (
            reproject_roi_to_lcc(actual_stack[horizon_index])[0]
            if actual_stack is not None
            else None
        )
        lcc_diff = (
            lcc_median - lcc_actual if lcc_actual is not None else None
        )

        for mode in MODES:
            entry = {
                "horizon": horizon,
                "mode": mode,
                "median_url": frame_url(target_date, horizon, mode, "median"),
                "uncertainty_url": frame_url(target_date, horizon, mode, "uncertainty"),
                "extent_lcc": list(extent_lcc),
            }

            median_png = day_dir / frame_filename(horizon, mode, "median")
            uncertainty_png = day_dir / frame_filename(horizon, mode, "uncertainty")
            _write_png(median_png, lcc_median, mode, "median", extent_lcc)
            _write_png(uncertainty_png, lcc_uncertainty, mode, "uncertainty", extent_lcc)
            written += [median_png, uncertainty_png]

            if lcc_actual is not None:
                actual_png = day_dir / frame_filename(horizon, mode, "actual")
                diff_png = day_dir / frame_filename(horizon, mode, "diff")
                _write_png(actual_png, lcc_actual, mode, "actual", extent_lcc)
                _write_png(diff_png, lcc_diff, mode, "diff", extent_lcc)
                written += [actual_png, diff_png]
                entry["actual_url"] = frame_url(target_date, horizon, mode, "actual")
                entry["diff_url"] = frame_url(target_date, horizon, mode, "diff")

            frames.append(entry)

    # Raw arrays, for archival and for anything that wants numbers rather
    # than pixels.
    _save_npy(array_dir / "median.npy", median)
    _save_npy(array_dir / "uncertainty.npy", half_width)
    if actual_stack is not None:
        _save_npy(array_dir / "actual.npy", actual_stack)

    manifest = {
        "date": target_date.isoformat(),
        "version": int(version),
        "projection": LCC_PROJ,
        "frames": frames,
        "staleness": staleness,
        "interval_widened": bool(interval_widened),
        "penalty_applied": float(penalty_applied),
        "has_actual": actual_stack is not None,
        "png_count": len(written),
    }
    manifest_path = day_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False), encoding="utf-8")

    logger.info(
        "rendered %d PNGs + manifest for %s (version %s, penalty %.3f, widened=%s)",
        len(written), target_date.isoformat(), version, penalty_applied, interval_widened,
    )
    return manifest


def _coerce_actual(actual: np.ndarray | None, shape: tuple[int, int, int]) -> np.ndarray | None:
    if actual is None:
        return None
    array = np.asarray(actual, dtype=np.float32)
    if array.shape == shape:
        return array
    if array.shape == ROI_SHAPE:
        return np.repeat(array[np.newaxis, ...], shape[0], axis=0)
    raise ValueError(
        f"actual must be {shape} or {ROI_SHAPE}, got {array.shape}"
    )


def _save_npy(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.ascontiguousarray(array, dtype=np.float32))


def read_manifest(day: date) -> dict | None:
    path = frames_dir(day) / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover — corrupt manifest
        logger.exception("could not read manifest for %s", day.isoformat())
        return None


def latest_manifest() -> tuple[date, dict] | None:
    """Newest manifest on disk, for health reporting."""
    root = frames_root()
    if not root.is_dir():
        return None
    for entry in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            day = date.fromisoformat(entry.name)
        except ValueError:
            continue
        manifest = read_manifest(day)
        if manifest is not None:
            return day, manifest
    return None


def forecast_date_window(target_date: date) -> list[date]:
    """The three days a forecast made for ``target_date`` describes."""
    return [target_date + timedelta(days=offset) for offset in range(1, HORIZONS + 1)]
