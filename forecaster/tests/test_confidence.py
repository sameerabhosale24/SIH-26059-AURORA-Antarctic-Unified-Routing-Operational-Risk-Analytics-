"""Frozen p33/p66 confidence classes."""

from pathlib import Path

import numpy as np
import pytest

from forecaster.artifacts_loader import resolve_artifacts_dir
from forecaster.confidence import (
    CLASS_HIGH,
    CLASS_INVALID,
    CLASS_LOW,
    CLASS_MEDIUM,
    CONFIDENCE_FILE,
    ConfidenceClassifier,
)
from forecaster.constants import ROI_SHAPE

ARTIFACTS = Path(resolve_artifacts_dir())


@pytest.fixture(scope="module")
def classifier() -> ConfidenceClassifier:
    return ConfidenceClassifier(ARTIFACTS)


def test_loads_real_thresholds(classifier: ConfidenceClassifier):
    assert classifier.source_path == str(ARTIFACTS / CONFIDENCE_FILE)
    assert np.isfinite(classifier.p33)
    assert np.isfinite(classifier.p66)
    assert classifier.p33 < classifier.p66


def test_class_boundaries(classifier: ConfidenceClassifier):
    H, W = ROI_SHAPE
    p33, p66 = classifier.p33, classifier.p66

    combined_std = np.zeros((3, H, W), dtype=np.float32)
    combined_std[0] = p33 / 2.0            # < p33        -> HIGH
    combined_std[1] = (p33 + p66) / 2.0    # p33..p66     -> MEDIUM
    combined_std[2] = p66 * 2.0            # >= p66       -> LOW

    median = np.full((3, H, W), 0.50, dtype=np.float32)  # ice everywhere
    valid_mask = np.ones(ROI_SHAPE, dtype=bool)

    out = classifier.classify(combined_std, median, valid_mask)

    assert out.dtype == np.uint8
    assert out.shape == (3, H, W)
    assert np.all(out[0] == CLASS_HIGH)
    assert np.all(out[1] == CLASS_MEDIUM)
    assert np.all(out[2] == CLASS_LOW)


def test_exact_p33_p66_boundaries(classifier: ConfidenceClassifier):
    H, W = ROI_SHAPE
    combined_std = np.full((3, H, W), classifier.p33, dtype=np.float32)
    combined_std[1] = classifier.p66
    median = np.full((3, H, W), 0.5, dtype=np.float32)
    valid_mask = np.ones(ROI_SHAPE, dtype=bool)

    out = classifier.classify(combined_std, median, valid_mask)
    assert np.all(out[0] == CLASS_MEDIUM)  # < p33 fails at equality
    assert np.all(out[1] == CLASS_LOW)      # >= p66 holds at equality


def test_invalid_mask_is_255(classifier: ConfidenceClassifier):
    H, W = ROI_SHAPE
    combined_std = np.full((3, H, W), classifier.p66 * 2.0, dtype=np.float32)
    median = np.full((3, H, W), 0.5, dtype=np.float32)

    valid_mask = np.ones(ROI_SHAPE, dtype=bool)
    valid_mask[7, 9] = False  # never-valid cell (land / coastal NaN band)

    out = classifier.classify(combined_std, median, valid_mask)
    assert out[0, 7, 9] == CLASS_INVALID
    assert out[1, 7, 9] == CLASS_INVALID
    assert out[2, 7, 9] == CLASS_INVALID
    assert out[0, 0, 0] == CLASS_LOW


def test_open_ocean_defaults_to_high(classifier: ConfidenceClassifier):
    """Valid cells with median <= 0.15 are HIGH regardless of std (documented)."""
    H, W = ROI_SHAPE
    combined_std = np.full((3, H, W), classifier.p66 * 10.0, dtype=np.float32)
    median = np.zeros((3, H, W), dtype=np.float32)
    valid_mask = np.ones(ROI_SHAPE, dtype=bool)
    valid_mask[0, 0] = False  # invalid cells still win -> 255

    out = classifier.classify(combined_std, median, valid_mask)
    assert np.all(out[:, 1:, :] == CLASS_HIGH)  # valid open water -> HIGH
    assert out[0, 0, 0] == CLASS_INVALID         # invalid cell wins -> 255


def test_missing_threshold_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as excinfo:
        ConfidenceClassifier(tmp_path)
    assert str(tmp_path / CONFIDENCE_FILE) in str(excinfo.value)


def test_wrong_shapes_raise(classifier: ConfidenceClassifier):
    H, W = ROI_SHAPE
    median = np.full((3, H, W), 0.5, dtype=np.float32)
    valid_mask = np.ones(ROI_SHAPE, dtype=bool)
    with pytest.raises(ValueError):
        classifier.classify(np.zeros((3, H - 1, W), dtype=np.float32), median, valid_mask)
    with pytest.raises(ValueError):
        classifier.classify(
            np.zeros((3, H, W), dtype=np.float32),
            median,
            np.ones((H - 1, W), dtype=bool),
        )
