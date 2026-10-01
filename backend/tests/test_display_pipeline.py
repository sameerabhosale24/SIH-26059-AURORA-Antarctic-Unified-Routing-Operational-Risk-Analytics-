"""Tests for the display pipeline — nine PNG frames per forecast.

The property with a navigational consequence is transparency: NaN must come
out of the PNG as alpha 0, because a white box where the coastline is would
be read as ice. That assertion is made against actual decoded pixels, not
against the intent of the code.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.services import display_pipeline as dp
from app.utils.constants import HORIZONS, ROI_SHAPE

TARGET = date(2026, 3, 15)
TOTAL_FRAMES = 3 * 3  # horizons x modes


class FakeOutput:
    """Minimal stand-in for ``ForecastOutput`` — same attribute contract."""

    def __init__(self, median, half_width):
        self.median = median
        self.interval_half_width = half_width


@pytest.fixture
def output():
    rng = np.random.default_rng(7)
    median = rng.random((HORIZONS, *ROI_SHAPE), dtype=np.float32)
    half_width = rng.random((HORIZONS, *ROI_SHAPE), dtype=np.float32) * 0.1
    return FakeOutput(median, half_width)


def read_png(path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg

    return mpimg.imread(path)


# ---------------------------------------------------------------------------
# Filenames and URLs
# ---------------------------------------------------------------------------
def test_frame_filename_is_1_based_and_lower():
    assert dp.frame_filename(1, "day", "median") == "1_day_median.png"
    assert dp.frame_filename(3, "night", "diff") == "3_night_diff.png"


def test_frame_url_points_at_the_api_route():
    url = dp.frame_url(TARGET, 2, "dusk", "uncertainty")
    assert url == "/api/sic/frame/2026-03-15/2_dusk_uncertainty.png"


def test_forecast_date_window_holds_three_days():
    assert dp.forecast_date_window(TARGET) == [
        date(2026, 3, 16), date(2026, 3, 17), date(2026, 3, 18),
    ]


# ---------------------------------------------------------------------------
# Rendering without observations
# ---------------------------------------------------------------------------
def test_renders_nine_frames_without_actual(output, storage_root):
    manifest = dp.render_frames(output, TARGET, version=1, staleness={"sic_max_age_days": 0})

    assert len(manifest["frames"]) == TOTAL_FRAMES
    assert manifest["has_actual"] is False
    # Two fields per frame (median + uncertainty): actual/diff are skipped
    # rather than rendered from an invented observation.
    assert manifest["png_count"] == TOTAL_FRAMES * 2
    for entry in manifest["frames"]:
        assert "actual_url" not in entry
        assert "diff_url" not in entry

    for entry in manifest["frames"]:
        assert (dp.frames_dir(TARGET) / dp.frame_filename(
            entry["horizon"], entry["mode"], "median")).exists()
        assert (dp.frames_dir(TARGET) / dp.frame_filename(
            entry["horizon"], entry["mode"], "uncertainty")).exists()

    assert not (dp.arrays_dir(TARGET) / "actual.npy").exists()
    assert (dp.arrays_dir(TARGET) / "median.npy").exists()
    assert (dp.arrays_dir(TARGET) / "uncertainty.npy").exists()


def test_renders_twelve_fields_per_horizon_set_with_actual(output, storage_root, roi_shape):
    actual = np.full(roi_shape, 0.4, np.float32)
    manifest = dp.render_frames(output, TARGET, version=2, actual=actual)

    assert len(manifest["frames"]) == TOTAL_FRAMES
    assert manifest["has_actual"] is True
    assert manifest["png_count"] == TOTAL_FRAMES * 4
    for entry in manifest["frames"]:
        assert "actual_url" in entry
        assert "diff_url" in entry

    stored = np.load(dp.arrays_dir(TARGET) / "actual.npy")
    assert stored.shape == (HORIZONS, *ROI_SHAPE)
    assert np.allclose(stored, 0.4)
    # A single 2-D observation is broadcast, never mixed with fabricated values.
    assert np.array_equal(stored[0], stored[2])


def test_manifest_records_staleness_and_penalty(output, storage_root):
    manifest = dp.render_frames(
        output, TARGET, version=5,
        staleness={"max_staleness_days": 4, "sic_persistence_days": 3},
        penalty_applied=0.2,
    )

    assert manifest["version"] == 5
    assert manifest["date"] == "2026-03-15"
    assert manifest["staleness"] == {"max_staleness_days": 4, "sic_persistence_days": 3}
    assert manifest["penalty_applied"] == pytest.approx(0.2)
    # A penalty wider than zero means the interval was widened.
    assert manifest["interval_widened"] is True


def test_interval_widened_defaults_to_false_without_penalty(output, storage_root):
    manifest = dp.render_frames(output, TARGET, version=1)
    assert manifest["interval_widened"] is False


# ---------------------------------------------------------------------------
# Shape validation
# ---------------------------------------------------------------------------
def test_rejects_wrong_median_shape(output, storage_root):
    bad = FakeOutput(np.zeros((3, 50, 50), np.float32), output.interval_half_width)
    with pytest.raises(ValueError, match="median"):
        dp.render_frames(bad, TARGET, version=1)


def test_rejects_mismatched_interval_shape(output, storage_root):
    bad = FakeOutput(output.median, np.zeros((HORIZONS, 50, 50), np.float32))
    with pytest.raises(ValueError, match="interval_half_width"):
        dp.render_frames(bad, TARGET, version=1)


def test_rejects_unrecognised_actual_shape(output, storage_root, roi_shape):
    with pytest.raises(ValueError, match="actual"):
        dp.render_frames(output, TARGET, version=1, actual=np.zeros((7, 7), np.float32))


# ---------------------------------------------------------------------------
# NaN is transparent
# ---------------------------------------------------------------------------
def test_nan_renders_as_fully_transparent_pixels(roi_shape):
    """The whole reason ``set_bad(alpha=0)`` exists.

    A NaN block in the source must decode to alpha 0 — a white or black box
    over the ENC base chart would be read as ice.
    """
    array = np.full(roi_shape, 0.6, np.float32)
    array[20:40, 50:90] = np.nan
    assert np.isnan(array).any()

    path = dp.frames_dir(TARGET) / "probe.png"
    # extent is [xmin, ymin, xmax, ymax]; the values only affect the aspect,
    # not which pixels carry alpha, so a unit box is enough here.
    dp._write_png(path, array, "day", "median", [-1.0, -1.0, 1.0, 1.0])

    png = read_png(path)
    assert png.shape[:2] == array.shape, "PNG pixel grid must match the array"
    assert png.shape[2] == 4, "PNG must carry an alpha channel"

    alpha = png[:, :, 3]
    nan_pixels = ~np.isfinite(array)
    assert alpha[nan_pixels].max() == 0.0, "NaN must be fully transparent"
    assert alpha[np.isfinite(array)].min() > 0.5, "valid data must stay visible"


def test_nan_survives_reprojection_and_stays_transparent(output, storage_root):
    """End to end: NaN goes into render_frames and comes out transparent."""
    median = np.full((HORIZONS, *ROI_SHAPE), 0.7, np.float32)
    median[0, 30:50, 100:160] = np.nan
    half_width = np.full((HORIZONS, *ROI_SHAPE), 0.05, np.float32)
    dp.render_frames(FakeOutput(median, half_width), TARGET, version=1)

    from app.utils.projection import reproject_roi_to_lcc

    lcc, _ = reproject_roi_to_lcc(median[0])
    nan_mask = ~np.isfinite(lcc)
    assert nan_mask.any(), "the NaN block should survive reprojection"

    png = read_png(dp.frames_dir(TARGET) / dp.frame_filename(1, "day", "median"))
    assert png.shape[:2] == lcc.shape

    alpha = png[:, :, 3]
    # Erode the mask by one pixel: imshow and the array can disagree at the
    # very edge of a masked region, but the interior must be transparent.
    core = np.zeros_like(nan_mask)
    core[1:-1, 1:-1] = (
        nan_mask[1:-1, 1:-1]
        & nan_mask[:-2, 1:-1] & nan_mask[2:, 1:-1]
        & nan_mask[1:-1, :-2] & nan_mask[1:-1, 2:]
    )
    if core.any():
        assert alpha[core].max() == 0.0
    else:  # pragma: no cover — the block is smaller than 3 px in some grids
        assert alpha[nan_mask].mean() > 0.9


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------
def test_manifest_round_trip(output, storage_root):
    written = dp.render_frames(output, TARGET, version=9)
    read_back = dp.read_manifest(TARGET)
    assert read_back == written
    assert read_back["version"] == 9


def test_missing_manifest_returns_none(storage_root):
    assert dp.read_manifest(date(1999, 1, 1)) is None
    assert dp.latest_manifest() is None


def test_latest_manifest_finds_newest_day(output, storage_root):
    dp.render_frames(output, date(2026, 3, 10), version=1)
    dp.render_frames(output, date(2026, 3, 12), version=2)

    found_day, manifest = dp.latest_manifest()
    assert found_day == date(2026, 3, 12)
    assert manifest["version"] == 2
