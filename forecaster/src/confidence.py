"""confidence.py — ice-cell confidence classes from frozen p33/p66 bins.

Thresholds are the empirical 33rd/66th percentiles of combined_std over
ice cells (predicted SIC > 0.15 and valid), frozen in
artifacts/confidence_thresholds.json — the single source of truth. This
module refuses to run when that file is missing; hardcoded fallback
thresholds are forbidden (they drift and silently change the labels).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .constants import HORIZONS, MIZ_THRESHOLD, ROI_SHAPE
from .scaler import require_file

CONFIDENCE_FILE = "confidence_thresholds.json"

# Class encoding — identical to the backend/frontend contract.
CLASS_HIGH = 0
CLASS_MEDIUM = 1
CLASS_LOW = 2
CLASS_INVALID = 255


class ConfidenceClassifier:
    """Bins combined_std into HIGH/MEDIUM/LOW confidence classes."""

    def __init__(self, artifacts_dir: Path):
        path = require_file(Path(artifacts_dir) / CONFIDENCE_FILE)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        try:
            self.p33 = float(data["p33"])
            self.p66 = float(data["p66"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KeyError(
                f"{path} is missing numeric 'p33'/'p66' entries. Refusing to "
                f"fall back to hardcoded thresholds."
            ) from exc

        if not (np.isfinite(self.p33) and np.isfinite(self.p66)) or not self.p33 < self.p66:
            raise ValueError(
                f"{path} has invalid thresholds p33={self.p33!r} p66={self.p66!r} "
                f"(expected finite values with p33 < p66)."
            )
        self.source_path = str(path)

    def classify(
        self,
        combined_std: np.ndarray,
        median: np.ndarray,
        valid_mask: np.ndarray,
    ) -> np.ndarray:
        """Classify every cell, shape [3, H, W] -> uint8 [3, H, W].

        Parameters
        ----------
        combined_std : np.ndarray
            Ensemble + MC-Dropout spread, shape [3, H, W].
        median : np.ndarray
            Model median SIC, shape [3, H, W].
        valid_mask : np.ndarray
            Boolean [H, W] mask: True where the cell has ever had valid
            training data (land / pole hole / coastal NaN band -> False).

        Returns
        -------
        np.ndarray
            uint8 array, shape [3, H, W]::

                255 = invalid cell (valid_mask False)
                  0 = HIGH   (combined_std < p33)
                  1 = MEDIUM (p33 <= combined_std < p66)
                  2 = LOW    (combined_std >= p66)

        Notes
        -----
        Precedence: an invalid cell is ALWAYS 255, even if it looks like ice.

        Among valid cells, only ICE cells (median > 0.15) are binned by the
        thresholds. Valid open-ocean cells (median <= 0.15) default to HIGH
        (0): their combined_std is tiny (the model is confidently ~0 there),
        so binning them would just relabel "has no ice" as LOW confidence.
        This matches how the thresholds were defined (p33/p66 over ice cells
        only).
        """
        combined_std = np.asarray(combined_std, dtype=np.float32)
        median = np.asarray(median, dtype=np.float32)
        valid_mask = np.asarray(valid_mask, dtype=bool)

        expected = (HORIZONS, ROI_SHAPE[0], ROI_SHAPE[1])
        if combined_std.shape != expected:
            raise ValueError(f"combined_std must have shape {expected}, got {combined_std.shape}")
        if median.shape != expected:
            raise ValueError(f"median must have shape {expected}, got {median.shape}")
        if valid_mask.shape != ROI_SHAPE:
            raise ValueError(f"valid_mask must have shape {ROI_SHAPE}, got {valid_mask.shape}")

        valid_3d = np.broadcast_to(valid_mask[np.newaxis, :, :], expected)
        ice_3d = median > MIZ_THRESHOLD

        out = np.full(expected, CLASS_INVALID, dtype=np.uint8)

        # Valid open water defaults to HIGH (documented above).
        out[valid_3d & ~ice_3d] = CLASS_HIGH

        # Ice cells are binned by combined_std.
        ice_valid = valid_3d & ice_3d
        out[ice_valid & (combined_std < self.p33)] = CLASS_HIGH
        out[ice_valid & (combined_std >= self.p33) & (combined_std < self.p66)] = CLASS_MEDIUM
        out[ice_valid & (combined_std >= self.p66)] = CLASS_LOW

        return out
