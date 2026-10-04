"""Turn forecaster output into the frames the map consumes.

Three frames per run — one per horizon — each with a median, an
uncertainty, and (when an observation exists) the observed field and the
difference. AURORA renders a single presentation, so there is no per-mode
render pass and no ``_dusk``/``_night`` file on disk: a frame is named
``{horizon}_{field}.png``.

The single hard requirement here is **NaN is transparent**. The SIC frame
is composited over the base chart; a white or black box where the
coastline or the data gap is would read as ice to a navigator. Every code
path therefore routes NaN through ``cmap.set_bad(alpha=0)`` and
``savefig(transparent=True)``, and the test suite asserts the alpha channel.

The canvas is the second half of that requirement. A frame painted on the
SIC grid (``[101, 361]``, 10°W–80°E, 75°S–50°S) ends where the data ends, so
the layer landed on the map as a rectangle with a hard edge at 50°S. Frames
are now painted on the **route grid** (``[185, 321]``, 0.3°): the SIC field
is placed into it, every cell the SIC grid does not cover stays NaN, and the
PNG's ``extent_lcc`` is the route grid's LCC extent. The image therefore
covers the whole Cape Town → Antarctica corridor while the ice itself simply
runs out into transparency instead of into an edge.

The third requirement is that **only cells the forecaster considers valid are
drawn at all**. ``valid_mask.npy`` (26,498 of 36,461 cells) marks the coastal
band and the land-contaminated cells the model is not trained to speak about;
its cells are set to NaN alongside the geographic gaps, before any
reprojection, so they render transparent instead of as a grey wedge across
the continent. Masking after reprojection would leave the contaminated cells
in the resampled field, which is exactly the artefact being removed.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.utils.constants import HORIZONS, LCC_PROJ, ROI_SHAPE
from app.utils.grid import place_sic_in_route_grid_nan
from app.utils.projection import reproject_route_to_lcc, route_lcc_bounds

logger = logging.getLogger("aurora.display")

#: The only presentation AURORA renders. Kept as a manifest field so a
#: reader can tell what the frame was drawn for without guessing.
PRESENTATION = "day"
FIELDS = ("median", "uncertainty", "actual", "diff")

#: SIC ramp: open water in AURORA's ocean blue, full concentration in white.
#: Positions are the class boundaries the forecast is read against, so they
#: are honoured rather than being spread evenly across 0..1.
SIC_STOPS: list[tuple[float, str]] = [
    (0.00, "#1E6091"),
    (0.15, "#3A8AB8"),
    (0.35, "#6BB6D9"),
    (0.55, "#A8D4E8"),
    (0.75, "#D6EAF3"),
    (0.90, "#F0F6FA"),
    (1.00, "#FFFFFF"),
]

#: Diverging ramp for the difference field, white at zero.
DIFF_STOPS: list[tuple[float, str]] = [
    (0.0, "#1f7a3f"),
    (0.25, "#8fd19a"),
    (0.5, "#ffffff"),
    (0.75, "#f2e44c"),
    (1.0, "#d94801"),
]

#: Resolution of a ramp when it is baked into a `ListedColormap`.
RAMP_SIZE = 256

UNCERTAINTY_FLOOR = 0.02
DIFF_FLOOR = 0.05

#: The forecaster's cell-validity mask, shipped with the trained artifacts.
VALID_MASK_FILENAME = "valid_mask.npy"


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


def _artifacts_dir() -> Path | None:
    """Directory holding the trained artifacts, or ``None`` if it is absent.

    Resolution mirrors ``main._probe_forecaster``: the environment override
    first (exported when the probe finds a real directory), then the
    configured default from the backend's own working directory. A missing
    directory is not an error — the frames still render, just unmasked, and
    the warning says which.
    """
    candidates: list[Path] = []
    env = os.environ.get("SIC_ARTIFACTS_PATH")
    if env:
        candidates.append(Path(env))

    configured = Path(get_settings().SIC_ARTIFACTS_PATH)
    candidates += [configured, Path.cwd() / configured, configured.resolve()]

    for candidate in candidates:
        try:
            if (candidate / VALID_MASK_FILENAME).is_file():
                return candidate
        except OSError:  # pragma: no cover — unreadable path
            continue
    return None


def _load_valid_mask() -> np.ndarray | None:
    """``valid_mask.npy`` as a boolean ``[101, 361]`` grid, or ``None``."""
    root = _artifacts_dir()
    if root is None:
        logger.warning(
            "%s not found in the forecaster artifacts; SIC frames will be "
            "rendered unmasked",
            VALID_MASK_FILENAME,
        )
        return None

    try:
        mask = np.load(root / VALID_MASK_FILENAME)
    except (OSError, ValueError) as exc:  # pragma: no cover — corrupt artifact
        logger.warning("could not read %s (%s); rendering unmasked", root / VALID_MASK_FILENAME, exc)
        return None

    mask = np.asarray(mask, dtype=bool)
    if mask.shape != tuple(ROI_SHAPE):
        logger.warning(
            "%s has shape %s, expected %s; rendering unmasked",
            VALID_MASK_FILENAME, mask.shape, tuple(ROI_SHAPE),
        )
        return None

    logger.info("valid_mask loaded from %s (%d/%d cells valid)", root, int(mask.sum()), mask.size)
    return mask


def _apply_valid_mask(
    mask: np.ndarray | None,
    *arrays: np.ndarray | None,
) -> tuple[np.ndarray | None, ...]:
    """NaN every cell the mask rejects, before reprojection.

    Copies on purpose: the arrays may be views of the caller's
    ``ForecastOutput``, and masking must not write back into it. Applied to
    median, uncertainty and actual alike — a half-width over an invalid cell
    is as meaningless as a median over one. The confidence field never comes
    through here; the forecaster already writes 255 for those cells.
    """
    if mask is None:
        return arrays

    masked: list[np.ndarray | None] = []
    for array in arrays:
        if array is None:
            masked.append(None)
            continue
        copy = np.array(array, dtype=np.float32, copy=True)
        copy[..., ~mask] = np.nan
        masked.append(copy)
    return tuple(masked)


def frame_filename(horizon: int, field: str) -> str:
    """``1_median.png`` — horizon is 1-based, field is lower.

    There is no mode segment: one presentation, one file per field.
    """
    return f"{horizon}_{field}.png"


def frame_url(day: date, horizon: int, field: str) -> str:
    return f"/api/sic/frame/{day.isoformat()}/{frame_filename(horizon, field)}"


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _ramp(stops: list[tuple[float, str]]) -> np.ndarray:
    """Sample a stop list into an ``(RAMP_SIZE, 3)`` array of 0..1 RGB."""
    from matplotlib.colors import to_rgb

    positions = np.array([position for position, _ in stops], dtype=np.float64)
    channels = np.array([to_rgb(colour) for _, colour in stops], dtype=np.float64)
    samples = np.linspace(0.0, 1.0, RAMP_SIZE)
    return np.stack(
        [np.interp(samples, positions, channels[:, index]) for index in range(3)],
        axis=1,
    )


def _cmap(field: str):
    from matplotlib.colors import ListedColormap

    colours = _ramp(DIFF_STOPS if field == "diff" else SIC_STOPS)
    cmap = ListedColormap(colours, name=f"aurora_{field}")
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


def _write_png(path: Path, array: np.ndarray, field: str,
               extent_lcc: list[float]) -> None:
    """Render one LCC frame. ``extent_lcc`` is ``[xmin, ymin, xmax, ymax]``
    in projected metres — the array has already left geographic space, so
    lat/lon bounds would be meaningless here."""
    plt = _matplotlib()
    from matplotlib.colors import ListedColormap

    cmap = _cmap(field)
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


def _to_route_lcc(array: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """SIC-grid field -> route-grid canvas -> LCC frame.

    Two steps on purpose. Placing first is what gives the frame a NaN margin
    on every side — the canvas is larger than the SIC region, so the ice runs
    out into transparency instead of into the PNG's own edge. Warping straight
    from the SIC grid would keep the rectangle, only reprojected.
    """
    return reproject_route_to_lcc(place_sic_in_route_grid_nan(array))


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

    # Before any reprojection: invalid cells become NaN here so they stay
    # transparent through the place/resample/LCC steps instead of being
    # resampled into the field as ordinary values.
    median, half_width, actual_stack = _apply_valid_mask(
        _load_valid_mask(), median, half_width, actual_stack
    )

    day_dir = frames_dir(target_date)
    day_dir.mkdir(parents=True, exist_ok=True)
    array_dir = arrays_dir(target_date)
    array_dir.mkdir(parents=True, exist_ok=True)

    # One canvas for the whole run: every horizon shares the route grid, so
    # the published extent is identical across all three frames and matches
    # the array every PNG below is rendered from.
    extent_lcc = list(route_lcc_bounds())

    frames: list[dict] = []
    written: list[Path] = []
    for horizon_index in range(HORIZONS):
        horizon = horizon_index + 1  # 1-based in every filename and URL
        lcc_median, _ = _to_route_lcc(median[horizon_index])
        lcc_uncertainty, _ = _to_route_lcc(half_width[horizon_index])
        lcc_actual = (
            _to_route_lcc(actual_stack[horizon_index])[0]
            if actual_stack is not None
            else None
        )
        lcc_diff = (
            lcc_median - lcc_actual if lcc_actual is not None else None
        )

        entry = {
            "horizon": horizon,
            "mode": PRESENTATION,
            "median_url": frame_url(target_date, horizon, "median"),
            "uncertainty_url": frame_url(target_date, horizon, "uncertainty"),
            "extent_lcc": list(extent_lcc),
        }

        median_png = day_dir / frame_filename(horizon, "median")
        uncertainty_png = day_dir / frame_filename(horizon, "uncertainty")
        _write_png(median_png, lcc_median, "median", extent_lcc)
        _write_png(uncertainty_png, lcc_uncertainty, "uncertainty", extent_lcc)
        written += [median_png, uncertainty_png]

        if lcc_actual is not None:
            actual_png = day_dir / frame_filename(horizon, "actual")
            diff_png = day_dir / frame_filename(horizon, "diff")
            _write_png(actual_png, lcc_actual, "actual", extent_lcc)
            _write_png(diff_png, lcc_diff, "diff", extent_lcc)
            written += [actual_png, diff_png]
            entry["actual_url"] = frame_url(target_date, horizon, "actual")
            entry["diff_url"] = frame_url(target_date, horizon, "diff")

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
