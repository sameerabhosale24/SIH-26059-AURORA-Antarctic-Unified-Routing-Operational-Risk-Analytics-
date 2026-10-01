"""scaler.py — frozen train-period standardization statistics.

Loads the artifacts once at construction and applies exactly the same
standardization the model was trained with (see training/dataset.py):

    channel 0 (SIC)          : (x - sic_mean) / sic_std
    channels 1-8 (forcing)   : per-channel mean/std from norm_stats.json
    channel 9 (SIC_prev_year): same scalars as channel 0

NaN handling matches training: NaN cells are replaced with 0 AFTER
standardization (the "no-data -> channel mean" convention).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from .constants import INPUT_CHANNELS

logger = logging.getLogger(__name__)

SCALER_FILES = ("sic_mean.npy", "sic_std.npy", "norm_stats.json")


def require_file(path: Path) -> Path:
    """Raise FileNotFoundError with the exact path if an artifact is absent."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Required artifact not found: {path}. The forecaster never "
            f"generates or downloads its own artifacts; place the frozen file "
            f"at this exact path (see README, 'Artifacts')."
        )
    return path


class Scaler:
    """Frozen standardization statistics for the 10 input channels."""

    def __init__(self, artifacts_dir: Path):
        artifacts_dir = Path(artifacts_dir)
        for name in SCALER_FILES:
            require_file(artifacts_dir / name)

        self.artifacts_dir = artifacts_dir
        self.sic_mean = float(np.load(artifacts_dir / "sic_mean.npy"))
        self.sic_std = float(np.load(artifacts_dir / "sic_std.npy"))
        if not np.isfinite(self.sic_mean) or not np.isfinite(self.sic_std) or self.sic_std == 0:
            raise ValueError(
                f"Invalid SIC scalars in {artifacts_dir / 'sic_mean.npy'} / "
                f"sic_std.npy: mean={self.sic_mean!r} std={self.sic_std!r}"
            )

        with open(artifacts_dir / "norm_stats.json", encoding="utf-8") as fh:
            stats = json.load(fh)

        try:
            self.channel_mean = np.asarray(stats["mean"], dtype=np.float64)
            self.channel_std = np.asarray(stats["std"], dtype=np.float64)
        except KeyError as exc:
            raise KeyError(
                f"norm_stats.json at {artifacts_dir / 'norm_stats.json'} is "
                f"missing the 'mean'/'std' keys required for channels 1-8"
            ) from exc

        # norm_stats.json carries 9 entries (u10 .. sic_prev_year); channels
        # 1-8 consume entries 0..7 and channel 9 uses the SIC scalars, so at
        # least INPUT_CHANNELS - 2 entries are required.
        n_forcing = INPUT_CHANNELS - 2
        if (
            self.channel_mean.shape != self.channel_std.shape
            or self.channel_mean.ndim != 1
            or self.channel_mean.shape[0] < n_forcing
        ):
            raise ValueError(
                f"norm_stats.json must carry at least {n_forcing} per-channel "
                f"stats, got mean={self.channel_mean.shape} "
                f"std={self.channel_std.shape}"
            )
        if np.any(self.channel_std == 0) or not np.all(np.isfinite(self.channel_std)):
            raise ValueError(
                f"norm_stats.json at {artifacts_dir / 'norm_stats.json'} has a "
                f"non-finite or zero std entry; refusing to standardize."
            )

        logger.info(
            "Scaler loaded from %s (sic_mean=%.6f, sic_std=%.6f, %d forcing stats)",
            artifacts_dir, self.sic_mean, self.sic_std, n_forcing,
        )

    def standardize(self, tensor: np.ndarray) -> np.ndarray:
        """Standardize a raw input window.

        Parameters
        ----------
        tensor : np.ndarray
            Raw input window, shape [T, 10, H, W] (or [10, H, W] channel
            axis at position 1). Channels are in RAW physical units.

        Returns
        -------
        np.ndarray
            float32 array of the same shape, standardized with the frozen
            train-period statistics, with NaN (and any non-finite) cells
            replaced by 0 AFTER standardization.

        Notes
        -----
        The input is always copied first — this method never modifies its
        argument in place (runtime rule 12).
        """
        arr = np.array(tensor, dtype=np.float32, copy=True)  # rule 12: copy first
        if arr.ndim != 4:
            raise ValueError(
                f"Scaler.standardize expects a 4-D [T, C, H, W] window, got shape {arr.shape}"
            )
        if arr.shape[1] != INPUT_CHANNELS:
            raise ValueError(
                f"Scaler.standardize expects {INPUT_CHANNELS} channels at axis 1, "
                f"got {arr.shape[1]}"
            )

        out = np.empty_like(arr)
        # channel 0: SIC
        out[:, 0] = (arr[:, 0] - self.sic_mean) / self.sic_std
        # channels 1-8: per-channel forcing stats (norm_stats.json entries 0..7)
        for offset, channel in enumerate(range(1, INPUT_CHANNELS - 1)):
            out[:, channel] = (arr[:, channel] - self.channel_mean[offset]) / self.channel_std[offset]
        # channel 9: SIC_prev_year — same scalars as channel 0
        out[:, INPUT_CHANNELS - 1] = (arr[:, INPUT_CHANNELS - 1] - self.sic_mean) / self.sic_std

        # Rule: NaN in the input is replaced with 0 AFTER standardization
        # (identical to training/dataset.py), never before.
        nan_mask = np.isnan(arr)
        nan_count = int(nan_mask.sum())
        if nan_count:
            out[nan_mask] = 0.0
            logger.info("Scaler.standardize: replaced %d NaN cells with 0 after standardization", nan_count)

        non_finite = ~np.isfinite(out)
        other_count = int(non_finite.sum())
        if other_count:
            # Defensive: +/-inf in the input would poison the convolution and
            # violate "never return NaN" downstream. Zero them like NaN.
            out[non_finite] = 0.0
            logger.warning(
                "Scaler.standardize: replaced %d non-finite (inf) cells with 0 "
                "(%d of them were NaN)", other_count, nan_count,
            )

        return out

    def destandardize_sic(self, tensor: np.ndarray) -> np.ndarray:
        """Map a standardized SIC field back to raw SIC 0..1.

        Present for future compatibility only. The model's sigmoid head
        already emits RAW SIC in [0, 1] (the target was never standardized
        during training), so there is nothing to undo: this is a no-op that
        returns an unchanged float32 copy of its argument.
        """
        return np.array(tensor, dtype=np.float32, copy=True)
