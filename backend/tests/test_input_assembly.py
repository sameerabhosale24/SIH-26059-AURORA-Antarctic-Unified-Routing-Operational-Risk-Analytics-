"""Tests for the input window assembly — the module that decides whether a
forecast is earned or fabricated.

The three properties that matter operationally:

* a channel with no data on disk raises instead of yielding zeros;
* the SIC channel only ever reads observations, never forecasts;
* every substitution is counted and reported rather than silently absorbed.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.services import input_assembly
from app.services.field_storage import write_field
from app.utils.constants import (
    CHANNEL_NAMES,
    HORIZONS,
    INPUT_CHANNELS,
    LOOKBACK_DAYS,
    ROI_SHAPE,
)

TARGET = date(2026, 3, 15)


@pytest.fixture(autouse=True)
def _quiet_unconfigured_log():
    """Keep the one-shot 'adapter not configured' warning out of test output."""
    input_assembly._ADAPTER_LOGGED.clear()
    yield
    input_assembly._ADAPTER_LOGGED.clear()


def days() -> list[date]:
    return input_assembly.window_days(TARGET)


def populate_sic(roi_shape):
    for offset, day in enumerate(days()):
        write_field("sic", day, np.full(roi_shape, 0.5 + offset, np.float32))
    for day in days():
        write_field("sic", day - timedelta(days=365), np.full(roi_shape, 0.9, np.float32))


def populate_weather(roi_shape):
    for day in days():
        stack = np.stack(
            [np.full(roi_shape, 1.0, np.float32),
             np.full(roi_shape, -2.0, np.float32),
             np.full(roi_shape, 270.0, np.float32)]
        )
        write_field("weather", day, stack)


def populate_currents(roi_shape):
    for day in days():
        write_field("currents", day, np.full((5, *roi_shape), 0.1, np.float32))


def populate_all(roi_shape):
    populate_sic(roi_shape)
    populate_weather(roi_shape)
    populate_currents(roi_shape)


# ---------------------------------------------------------------------------
# Shape and ordering
# ---------------------------------------------------------------------------
def test_window_days_are_five_consecutive_ending_on_target():
    window = days()
    assert len(window) == LOOKBACK_DAYS
    assert window == sorted(window)
    assert window[-1] == TARGET
    assert window[0] == TARGET - timedelta(days=LOOKBACK_DAYS - 1)


def test_input_window_shape_matches_forecaster_contract():
    assert input_assembly.input_window_shape() == (5, 10, 101, 361)
    assert len(CHANNEL_NAMES) == INPUT_CHANNELS == 10
    assert input_assembly.horizons() == HORIZONS


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_assembles_complete_window(storage_root, roi_shape):
    populate_all(roi_shape)

    tensor, staleness = input_assembly.assemble_input_window(TARGET)

    assert tensor.shape == (5, 10, 101, 361)
    assert tensor.dtype == np.float32
    assert np.isfinite(tensor).all()

    # Spot-check that each block landed in the channel it claims.
    assert tensor[0, 0] == pytest.approx(0.5)   # SIC, oldest day
    assert tensor[4, 0] == pytest.approx(4.5)   # SIC, target day (0.5 + offset)
    assert tensor[2, 1].min() == pytest.approx(1.0)     # u10
    assert tensor[2, 2].min() == pytest.approx(-2.0)    # v10
    assert tensor[2, 3].min() == pytest.approx(270.0)   # t2m
    assert tensor[2, 4].min() == pytest.approx(0.1)     # uo
    assert tensor[4, 9].min() == pytest.approx(0.9)     # SIC_prev_year
    # First and last channels must be different fields, not a copy.
    assert not np.array_equal(tensor[0, 0], tensor[0, 9])

    assert staleness["sic_max_age_days"] == 0
    assert staleness["era5_max_age_days"] == 0
    assert staleness["cmems_max_age_days"] == 0
    assert staleness["cmems_analysis_used"] is True
    assert staleness["nwp_used"] is False


def test_absent_thickness_does_not_block_the_forecast(roi_shape):
    """Thickness is not a model input, so its absence must not fail assembly."""
    populate_all(roi_shape)

    _, staleness = input_assembly.assemble_input_window(TARGET)

    assert staleness["thickness_max_age_days"] == -1
    # ...but it must also not be able to inflate the gating staleness.
    assert staleness["max_staleness_days"] == 0


# ---------------------------------------------------------------------------
# Missing data must raise, never zero-fill
# ---------------------------------------------------------------------------
def test_missing_source_raises_rather_than_filling_with_zeros(roi_shape):
    populate_sic(roi_shape)
    populate_weather(roi_shape)
    # currents never written

    with pytest.raises(ValueError) as excinfo:
        input_assembly.assemble_input_window(TARGET)

    message = str(excinfo.value)
    assert "cannot assemble" in message
    assert "will not fabricate" in message
    assert "currents" in message


def test_empty_store_raises_for_the_first_channel(roi_shape):
    with pytest.raises(ValueError) as excinfo:
        input_assembly.assemble_input_window(TARGET)
    assert "channel SIC" in str(excinfo.value)


def test_missing_prev_year_observation_is_not_substituted(roi_shape):
    """SIC_prev_year needs exactly D-365; a near date must not pass."""
    for day in days():
        write_field("sic", day, np.full(roi_shape, 0.5, np.float32))
    populate_weather(roi_shape)
    populate_currents(roi_shape)

    # Off by one day: present, but not the required anniversary.
    write_field("sic", days()[0] - timedelta(days=364), np.full(roi_shape, 0.9, np.float32))

    with pytest.raises(ValueError) as excinfo:
        input_assembly.assemble_input_window(TARGET)

    message = str(excinfo.value)
    assert "SIC_prev_year" in message
    assert "365 days" in message


def test_wrong_grid_size_is_rejected(roi_shape):
    populate_sic(roi_shape)
    populate_weather(roi_shape)
    populate_currents(roi_shape)
    write_field("sic", days()[-1], np.full((50, 180), 0.5, np.float32))

    with pytest.raises(ValueError) as excinfo:
        input_assembly.assemble_input_window(TARGET)
    assert "different grid" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Persistence is bounded and reported
# ---------------------------------------------------------------------------
def test_persistence_is_reported_when_the_latest_day_is_absent(roi_shape):
    populate_sic(roi_shape)
    populate_weather(roi_shape)
    populate_currents(roi_shape)
    from app.services.field_storage import field_path

    # The target day's SIC never arrives; the store stops one day early.
    field_path("sic", days()[-1]).unlink()

    tensor, staleness = input_assembly.assemble_input_window(TARGET)

    assert staleness["sic_max_age_days"] == 1
    assert staleness["sic_persistence_days"] == 1
    # The fallback is a real observation, so the window still has no holes.
    assert np.isfinite(tensor).all()
    # And it must not be mistaken for fresh data.
    assert staleness["sic_max_age_days"] != 0


def test_fully_stale_store_still_assembles_but_reports_max_age(roi_shape):
    """A source whose files all stop early is stale, not missing."""
    for day in days()[:-1]:
        write_field("sic", day, np.full(roi_shape, 0.4, np.float32))
    for day in days():
        write_field("sic", day - timedelta(days=365), np.full(roi_shape, 0.4, np.float32))
    populate_weather(roi_shape)
    populate_currents(roi_shape)

    _, staleness = input_assembly.assemble_input_window(TARGET)

    assert staleness["max_staleness_days"] >= 1
    assert staleness["sic_persistence_days"] >= 1


def test_staleness_gate_excludes_thickness(roi_shape):
    """A stale thickness must not be able to suppress a valid forecast."""
    populate_sic(roi_shape)
    populate_weather(roi_shape)
    populate_currents(roi_shape)
    old = TARGET - timedelta(days=200)
    write_field("ice_thickness", old, np.full((1, *roi_shape), 0.3, np.float32))

    _, staleness = input_assembly.assemble_input_window(TARGET)

    assert staleness["thickness_max_age_days"] >= 0
    assert staleness["max_staleness_days"] == 0


# ---------------------------------------------------------------------------
# Structural guarantee: forecasts are never an input
# ---------------------------------------------------------------------------
def test_assembly_never_imports_forecast_products():
    """Forecast feedback is prevented structurally: this module may only
    import the observation store, never the renderer or the forecaster.

    Checking imports rather than prose keeps the assertion immune to the
    docstring, which deliberately discusses forecasts at length.
    """
    import ast
    import pathlib

    source = pathlib.Path(input_assembly.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")

    forbidden = (".display_pipeline", ".sic_scheduler", "forecaster", "matplotlib")
    hits = [name for name in imported if any(f in name for f in forbidden)]
    assert hits == [], f"input assembly must not import forecast machinery, got {hits}"


def test_only_observation_sources_are_read(roi_shape, monkeypatch):
    """Nothing outside the observation store may be opened.

    ``ice_thickness`` is read too — for staleness accounting only, never
    into a channel — so it belongs to the allowed set.
    """
    opened = []

    import app.services.field_storage as fs

    real_read = fs.read_field

    def spy(source, day):
        opened.append(source)
        return real_read(source, day)

    monkeypatch.setattr(input_assembly, "read_field", spy)
    populate_all(roi_shape)
    opened.clear()

    input_assembly.assemble_input_window(TARGET)

    assert set(opened) <= {"sic", "weather", "currents", "ice_thickness"}
    # SIC serves both channel 0 and channel 9 — the observations are the only
    # thing feeding them.
    assert opened.count("sic") == 10  # 5 window days + 5 anniversaries
