"""Frozen conformal quantiles and the stratified half-width rule."""

from pathlib import Path

import numpy as np
import pytest

from forecaster.artifacts_loader import resolve_artifacts_dir
from forecaster.conformal import ConformalIntervals, Q90_MIZ, Q90_OPEN, METRICS_FILE
from forecaster.constants import ROI_SHAPE

ARTIFACTS = Path(resolve_artifacts_dir())


def test_published_constants():
    assert Q90_MIZ == 0.12617
    assert Q90_OPEN == 0.00206


def test_loads_frozen_quantiles_from_real_metrics():
    conformal = ConformalIntervals(ARTIFACTS)
    assert conformal.q90_miz == Q90_MIZ
    assert conformal.q90_open == Q90_OPEN
    assert conformal.source_path == str(ARTIFACTS / METRICS_FILE)

    # and the file itself carries the frozen values
    import json

    with open(ARTIFACTS / METRICS_FILE, encoding="utf-8") as fh:
        metrics = json.load(fh)
    assert f"{metrics['conformal']['q90_miz']:.5f}" == "0.12617"
    assert f"{metrics['conformal']['q90_open']:.5f}" == "0.00206"


def test_stratified_half_width_from_median():
    """At inference (true_sic=None) the model median selects the stratum."""
    conformal = ConformalIntervals(ARTIFACTS)
    H, W = ROI_SHAPE

    median = np.zeros((3, H, W), dtype=np.float32)
    median[0, :10, :] = 0.50   # ice -> q90_miz
    median[0, 10:20, :] = 0.05  # open -> q90_open
    median[1, :, :] = 0.15      # exactly at threshold -> open (rule is >)
    median[2, 50, 50] = 0.99

    half_width = conformal.compute(median, true_sic=None)

    assert half_width.shape == (3, H, W)
    assert half_width.dtype == np.float32
    assert np.all(half_width[0, :10, :] == np.float32(Q90_MIZ))
    assert np.all(half_width[0, 10:20, :] == np.float32(Q90_OPEN))
    assert np.all(half_width[1, :, :] == np.float32(Q90_OPEN))
    assert half_width[2, 50, 50] == np.float32(Q90_MIZ)


def test_stratified_half_width_from_true_sic():
    conformal = ConformalIntervals(ARTIFACTS)
    H, W = ROI_SHAPE

    median = np.full((3, H, W), 0.80, dtype=np.float32)   # median says ice
    true_sic = np.full((3, H, W), 0.02, dtype=np.float32)  # truth says open

    half_width = conformal.compute(median, true_sic=true_sic)
    # true_sic wins as the stratum selector when it is provided
    assert np.all(half_width == np.float32(Q90_OPEN))

    true_sic[..., :5, :] = 0.70
    half_width = conformal.compute(median, true_sic=true_sic)
    assert np.all(half_width[:, :5, :] == np.float32(Q90_MIZ))


def test_missing_metrics_file_raises(tmp_path: Path):
    missing = tmp_path / METRICS_FILE
    with pytest.raises(FileNotFoundError) as excinfo:
        ConformalIntervals(tmp_path)
    assert str(missing) in str(excinfo.value)


def test_wrong_median_shape_raises():
    conformal = ConformalIntervals(ARTIFACTS)
    with pytest.raises(ValueError):
        conformal.compute(np.zeros((3, 100, 360), dtype=np.float32))
