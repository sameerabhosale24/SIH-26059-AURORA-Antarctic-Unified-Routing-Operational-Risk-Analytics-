"""Frozen-artifact loading: every missing file must raise with its path."""

import shutil
from pathlib import Path

import pytest

from forecaster.artifacts_loader import Artifacts, resolve_artifacts_dir
from forecaster.constants import MODEL_PARAM_COUNT, ROI_SHAPE, SEED_COUNT

REAL_ARTIFACTS = Path(resolve_artifacts_dir())


@pytest.fixture()
def artifacts_copy(tmp_path: Path) -> Path:
    """A complete copy of the real artifact set in a temp directory."""
    dst = tmp_path / "artifacts"
    shutil.copytree(REAL_ARTIFACTS, dst)
    return dst


def test_load_complete_artifacts(artifacts_copy: Path):
    artifacts = Artifacts(artifacts_copy)

    assert len(artifacts.models) == SEED_COUNT
    for model in artifacts.models:
        n_params = sum(p.numel() for p in model.parameters())
        assert n_params == MODEL_PARAM_COUNT
        assert not model.training  # eval() mode

    assert artifacts.valid_mask.shape == ROI_SHAPE
    assert artifacts.valid_mask.dtype == bool
    assert artifacts.scaler.sic_std > 0
    assert artifacts.conformal.q90_miz == 0.12617
    assert artifacts.conformal.q90_open == 0.00206
    assert artifacts.confidence.p33 < artifacts.confidence.p66
    assert artifacts.metadata["seeds"] == [0, 1, 2]
    assert artifacts.metadata["param_count"] == MODEL_PARAM_COUNT


def test_missing_checkpoint_raises_with_path(artifacts_copy: Path):
    missing = artifacts_copy / "final_10ch_3f_seed1" / "best_model.pt"
    missing.unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        Artifacts(artifacts_copy)

    assert str(missing) in str(excinfo.value)


def test_missing_conformal_metrics_raises_with_path(artifacts_copy: Path):
    missing = artifacts_copy / "metrics_2025.json"
    missing.unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        Artifacts(artifacts_copy)

    assert str(missing) in str(excinfo.value)


def test_missing_confidence_thresholds_raises_with_path(artifacts_copy: Path):
    missing = artifacts_copy / "confidence_thresholds.json"
    missing.unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        Artifacts(artifacts_copy)

    assert str(missing) in str(excinfo.value)


def test_missing_scaler_stat_raises_with_path(artifacts_copy: Path):
    missing = artifacts_copy / "sic_mean.npy"
    missing.unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        Artifacts(artifacts_copy)

    assert str(missing) in str(excinfo.value)


def test_real_artifacts_are_present():
    """The shipped package must never stub an artifact — all must exist."""
    for name in (
        "sic_mean.npy",
        "sic_std.npy",
        "norm_stats.json",
        "metrics_2025.json",
        "confidence_thresholds.json",
        "valid_mask.npy",
    ):
        assert (REAL_ARTIFACTS / name).is_file(), f"missing artifact {name}"
    for seed in range(SEED_COUNT):
        ckpt = REAL_ARTIFACTS / f"final_10ch_3f_seed{seed}" / "best_model.pt"
        assert ckpt.is_file(), f"missing checkpoint {ckpt}"
