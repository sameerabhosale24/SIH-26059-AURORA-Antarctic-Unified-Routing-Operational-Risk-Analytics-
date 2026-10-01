"""artifacts_loader.py — loads the frozen artifacts exactly once.

This module is the ONLY place in the package that touches the filesystem,
and it only ever reads the frozen artifact set (checkpoints, scaler stats,
conformal quantiles, confidence thresholds, valid mask). Everything else in
the package is a pure function of its arguments.

The default artifact directory is resolved from the SIC_ARTIFACTS_PATH
environment variable, falling back to ``<package>/artifacts``. The resolved
instance is cached in a module-level singleton so repeated predict() calls
never reload weights. If any file is missing, FileNotFoundError is raised
with the exact path — this package never invents, downloads, or stubs an
artifact.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import torch

from .confidence import ConfidenceClassifier
from .conformal import ConformalIntervals
from .constants import MODEL_PARAM_COUNT, ROI_SHAPE, SEED_COUNT
from .model import ConvLSTMForecaster
from .scaler import Scaler, require_file

logger = logging.getLogger(__name__)

# Package root = the directory that contains src/ and artifacts/.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

ARTIFACTS_ENV_VAR = "SIC_ARTIFACTS_PATH"
MODEL_VERSION = "final_10ch_3f_seed0-2"
PACKAGE_VERSION = "1.0.0"

SEED_DIR_TEMPLATE = "final_10ch_3f_seed{seed}"
CHECKPOINT_NAME = "best_model.pt"


def resolve_artifacts_dir(artifacts_dir: str | os.PathLike | None = None) -> Path:
    """Resolve the artifact directory: argument > env var > package default."""
    if artifacts_dir is not None:
        return Path(artifacts_dir).expanduser()
    env = os.environ.get(ARTIFACTS_ENV_VAR)
    if env:
        return Path(env).expanduser()
    return PACKAGE_ROOT / "artifacts"


class Artifacts:
    """The complete frozen artifact set for one forecaster version.

    Attributes
    ----------
    models : list[ConvLSTMForecaster]
        3 seed checkpoints, loaded and in eval() mode (predict() flips
        dropout on per call and restores eval() afterwards).
    scaler : Scaler
        Frozen train-period standardization statistics.
    conformal : ConformalIntervals
        Frozen 2025 stratified conformal quantiles.
    confidence : ConfidenceClassifier
        Frozen ice-cell p33/p66 confidence thresholds.
    valid_mask : np.ndarray
        bool [H, W]; False where the cell never had valid training data.
    metadata : dict
        Version info for ForecastOutput.metadata.
    """

    def __init__(self, artifacts_dir: str | os.PathLike | None = None):
        self.artifacts_dir = resolve_artifacts_dir(artifacts_dir)

        # ---- Fail fast, with the exact path, before loading anything ----
        checkpoint_paths = []
        for seed in range(SEED_COUNT):
            ckpt = self.artifacts_dir / SEED_DIR_TEMPLATE.format(seed=seed) / CHECKPOINT_NAME
            checkpoint_paths.append(require_file(ckpt))
        require_file(self.artifacts_dir / "sic_mean.npy")
        require_file(self.artifacts_dir / "sic_std.npy")
        require_file(self.artifacts_dir / "norm_stats.json")
        require_file(self.artifacts_dir / "metrics_2025.json")
        require_file(self.artifacts_dir / "confidence_thresholds.json")
        valid_mask_path = require_file(self.artifacts_dir / "valid_mask.npy")

        # ---- Frozen post-processing components ----
        self.scaler = Scaler(self.artifacts_dir)
        self.conformal = ConformalIntervals(self.artifacts_dir)
        self.confidence = ConfidenceClassifier(self.artifacts_dir)

        # ---- Valid mask ----
        self.valid_mask = np.load(valid_mask_path).astype(bool)
        if self.valid_mask.shape != ROI_SHAPE:
            raise ValueError(
                f"{valid_mask_path} has shape {self.valid_mask.shape}, "
                f"expected {ROI_SHAPE}"
            )

        # ---- Seed checkpoints ----
        self.models: list[ConvLSTMForecaster] = []
        for seed, ckpt in enumerate(checkpoint_paths):
            model = ConvLSTMForecaster()
            state = torch.load(ckpt, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            n_params = sum(p.numel() for p in model.parameters())
            if n_params != MODEL_PARAM_COUNT:
                raise RuntimeError(
                    f"{ckpt} produced a model with {n_params} parameters, "
                    f"expected {MODEL_PARAM_COUNT} — architecture drift is forbidden."
                )
            model.eval()
            self.models.append(model)

        self.metadata = {
            "model_version": MODEL_VERSION,
            "package_version": PACKAGE_VERSION,
            "seeds": list(range(SEED_COUNT)),
            "param_count": MODEL_PARAM_COUNT,
            "artifacts_path": str(self.artifacts_dir),
        }

        logger.info(
            "Loaded %d seed models, scaler, conformal quantiles, confidence "
            "thresholds from %s", SEED_COUNT, self.artifacts_dir,
        )


# ---------------------------------------------------------------------------
# Module-level singleton: repeated predict() calls never reload weights.
# ---------------------------------------------------------------------------
_ARTIFACTS: dict[str, Artifacts] = {}


def get_artifacts(artifacts_dir: str | os.PathLike | None = None) -> Artifacts:
    """Return the cached Artifacts for `artifacts_dir`, loading it once."""
    key = str(resolve_artifacts_dir(artifacts_dir))
    if key not in _ARTIFACTS:
        _ARTIFACTS[key] = Artifacts(key)
    return _ARTIFACTS[key]


def clear_artifacts_cache() -> None:
    """Drop the singleton cache (internal; used by tests)."""
    _ARTIFACTS.clear()


# Load the default artifact set once, at import time (rule 1: the only
# filesystem read in the runtime path is the frozen artifact load).
get_artifacts()
