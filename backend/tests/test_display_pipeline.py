"""Tests for the display pipeline — three PNG frames per forecast.

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
TOTAL_FRAMES = 3  # horizons, one presentation each


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
    assert dp.frame_filename(1, "median") == "1_median.png"
    assert dp.frame_filename(3, "diff") == "3_diff.png"


def test_frame_url_points_at_the_api_route():
    url = dp.frame_url(TARGET, 2, "uncertainty")
    assert url == "/api/sic/frame/2026-03-15/2_uncertainty.png"


def test_forecast_date_window_holds_three_days():
    assert dp.forecast_date_window(TARGET) == [
        date(2026, 3, 16), date(2026, 3, 17), date(2026, 3, 18),
    ]


# ---------------------------------------------------------------------------
# Rendering without observations
# ---------------------------------------------------------------------------
def test_renders_three_frames_without_actual(output, storage_root):
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
            entry["horizon"], "median")).exists()
        assert (dp.frames_dir(TARGET) / dp.frame_filename(
            entry["horizon"], "uncertainty")).exists()

    assert not (dp.arrays_dir(TARGET) / "actual.npy").exists()
    assert (dp.arrays_dir(TARGET) / "median.npy").exists()
    assert (dp.arrays_dir(TARGET) / "uncertainty.npy").exists()


def test_one_entry_per_horizon_and_no_display_mode_variants(output, storage_root):
    """The manifest is three entries, not nine, and nothing is dusk/night."""
    manifest = dp.render_frames(output, TARGET, version=1)

    assert len(manifest["frames"]) == HORIZONS
    assert {entry["horizon"] for entry in manifest["frames"]} == {1, 2, 3}
    assert {entry["mode"] for entry in manifest["frames"]} == {"day"}

    names = sorted(path.name for path in dp.frames_dir(TARGET).glob("*.png"))
    assert names == [
        "1_median.png", "1_uncertainty.png",
        "2_median.png", "2_uncertainty.png",
        "3_median.png", "3_uncertainty.png",
    ]
    assert not list(dp.frames_dir(TARGET).glob("*_dusk_*"))
    assert not list(dp.frames_dir(TARGET).glob("*_night_*"))


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


def test_valid_mask_nan_s_out_every_field(output, storage_root, roi_shape, forecaster_artifacts):
    """Cells the forecaster marks invalid must be transparent, not painted.

    The mask is applied before reprojection, so it reaches median,
    uncertainty and actual alike — a half-width over a contaminated cell is
    as meaningless as a median over one.
    """
    valid = np.ones(roi_shape, dtype=bool)
    valid[10:20, 30:50] = False
    np.save(forecaster_artifacts / "valid_mask.npy", valid)
    invalid = ~valid

    actual = np.full(roi_shape, 0.4, np.float32)
    dp.render_frames(output, TARGET, version=1, actual=actual)

    for name in ("median", "uncertainty", "actual"):
        field = np.load(dp.arrays_dir(TARGET) / f"{name}.npy")
        assert np.isnan(field[:, invalid]).all(), f"{name}: invalid cells must be NaN"
        assert np.isfinite(field[:, ~invalid]).all(), f"{name}: valid cells must stay finite"


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
    dp._write_png(path, array, "median", [-1.0, -1.0, 1.0, 1.0])

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

    from app.utils.grid import place_sic_in_route_grid_nan
    from app.utils.projection import reproject_route_to_lcc

    # The frame is warped from the route canvas, so the NaN block has to
    # survive two hops — placement onto the bigger grid, then projection.
    lcc, _ = reproject_route_to_lcc(place_sic_in_route_grid_nan(median[0]))
    nan_mask = ~np.isfinite(lcc)
    assert nan_mask.any(), "the NaN block should survive reprojection"

    png = read_png(dp.frames_dir(TARGET) / dp.frame_filename(1, "median"))
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


def test_frame_extent_is_the_route_grid_not_the_sic_grid(output, storage_root):
    """The manifest advertises the canvas, so the PNG stops being a rectangle.

    An SIC-grid extent is exactly as large as the data, which is how the layer
    used to arrive on the map with a hard edge at 50°S. The canvas has to run
    *past* the data — north of it, south of it, and east of it — so the frame's
    edge is never the data's edge.

    East/west the canvas is the corridor, not the whole product: it spans
    5°E–85°E at the same 0.25° as the SIC grid, so the 10°W–5°E slice of the
    product falls outside it on purpose rather than the canvas being stretched
    to 361 columns. Only latitude has to contain the SIC region outright.
    """
    from app.utils.grid import roi_bounds, route_bounds
    from app.utils.projection import lcc_bounds, route_lcc_bounds

    manifest = dp.render_frames(output, TARGET, version=1)

    route = list(route_lcc_bounds())
    for entry in manifest["frames"]:
        assert entry["extent_lcc"] == route

    sic_extent = list(lcc_bounds())
    assert route != sic_extent, "the canvas must not be the SIC rectangle"

    r_west, r_south, r_east, r_north = route_bounds()
    s_west, s_south, s_east, s_north = roi_bounds()

    # Latitude: the whole SIC region, with room above and below it, so the
    # frame never ends where the data ends (50°S / 75°S).
    assert r_south < s_south
    assert r_north > s_north
    # East: the canvas reaches past the data's eastern edge too.
    assert r_east > s_east
    # West: corridor-aligned, so the westernmost SIC cells are outside the
    # canvas by design — that is what keeps the canvas at 321 columns.
    assert r_west > s_west
    assert r_west < s_east


def test_frame_has_a_transparent_margin_outside_the_sic_region(output, storage_root):
    """Ice must fade into the ocean instead of ending on the image's edge."""
    median = np.full((HORIZONS, *ROI_SHAPE), 0.5, np.float32)
    half_width = np.full((HORIZONS, *ROI_SHAPE), 0.05, np.float32)
    dp.render_frames(FakeOutput(median, half_width), TARGET, version=1)

    png = read_png(dp.frames_dir(TARGET) / dp.frame_filename(1, "median"))
    alpha = png[:, :, 3]

    assert alpha.max() > 0.5, "the SIC region itself must stay visible"
    assert alpha.min() == 0.0, "the canvas must extend past the data"
    # The four corners are far outside the SIC grid in every direction.
    assert alpha[0, 0] == 0.0
    assert alpha[0, -1] == 0.0
    assert alpha[-1, 0] == 0.0
    assert alpha[-1, -1] == 0.0


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
