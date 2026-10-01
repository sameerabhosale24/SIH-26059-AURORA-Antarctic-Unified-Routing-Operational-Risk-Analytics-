"""conformal.py — frozen stratified conformal 90% interval half-widths.

The quantiles were calibrated once on 2025 (176 calibration samples,
90th percentile of |residual|) and are FROZEN. The conformal coverage
guarantee only holds with these exact numbers, so this module refuses to
run when metrics_2025.json is missing — there is deliberately no fallback
to raw combined_std.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .constants import HORIZONS, MIZ_THRESHOLD, ROI_SHAPE
from .scaler import require_file

# Published (rounded) frozen quantiles — the single source of truth.
Q90_MIZ = 0.12617
Q90_OPEN = 0.00206

METRICS_FILE = "metrics_2025.json"


class ConformalIntervals:
    """Stratified conformal interval widths from frozen 2025 quantiles."""

    def __init__(self, artifacts_dir: Path):
        path = require_file(Path(artifacts_dir) / METRICS_FILE)
        with open(path, encoding="utf-8") as fh:
            metrics = json.load(fh)

        try:
            conf = metrics["conformal"]
            q90_miz = float(conf["q90_miz"])
            q90_open = float(conf["q90_open"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KeyError(
                f"{path} does not contain a numeric conformal.q90_miz / "
                f"conformal.q90_open entry. Refusing to fall back to raw "
                f"combined_std: the conformal guarantee only holds with the "
                f"frozen quantiles."
            ) from exc

        # Freeze guard: the file must carry exactly the published quantiles
        # (file stores full precision, e.g. 0.12616950273513794 -> 0.12617).
        if f"{q90_miz:.5f}" != f"{Q90_MIZ:.5f}" or f"{q90_open:.5f}" != f"{Q90_OPEN:.5f}":
            raise ValueError(
                f"{path} carries conformal quantiles (q90_miz={q90_miz!r}, "
                f"q90_open={q90_open!r}) that differ from the frozen published "
                f"values (Q90_MIZ={Q90_MIZ}, Q90_OPEN={Q90_OPEN}). Recalibrating "
                f"on new data would invalidate the coverage guarantee."
            )

        self.q90_miz = Q90_MIZ
        self.q90_open = Q90_OPEN
        self.source_path = str(path)

    def compute(
        self,
        median: np.ndarray,
        true_sic: np.ndarray | None = None,
    ) -> np.ndarray:
        """Stratified conformal half-width per cell, shape [3, H, W].

        Parameters
        ----------
        median : np.ndarray
            Model median SIC, shape [3, H, W], range [0, 1].
        true_sic : np.ndarray or None
            Ground-truth SIC, shape [3, H, W]. Only available when
            evaluating against observations; at operational inference time
            it is None.

        Returns
        -------
        np.ndarray
            float32 half-width, shape [3, H, W]. The interval is
            [median - half_width, median + half_width] clipped to [0, 1].

        Notes
        -----
        Stratified rule (frozen from 2025 calibration)::

            if stratum_SIC > 0.15:  half_width = Q90_MIZ   (0.12617)
            else:                   half_width = Q90_OPEN   (0.00206)

        **Operational approximation:** the calibration stratified on TRUE SIC,
        but at inference time ground truth is unknown, so when ``true_sic``
        is None the MODEL MEDIAN is used as the stratum selector. This is the
        documented approximation used in production; it never widens or
        narrows the quantiles themselves, only chooses between the two frozen
        strata.
        """
        median = np.asarray(median, dtype=np.float32)
        expected = (HORIZONS, ROI_SHAPE[0], ROI_SHAPE[1])
        if median.shape != expected:
            raise ValueError(f"median must have shape {expected}, got {median.shape}")

        if true_sic is None:
            stratum = median  # operational approximation (see docstring)
        else:
            stratum = np.asarray(true_sic, dtype=np.float32)
            if stratum.shape != expected:
                raise ValueError(f"true_sic must have shape {expected}, got {stratum.shape}")

        half_width = np.where(
            stratum > MIZ_THRESHOLD, self.q90_miz, self.q90_open
        ).astype(np.float32)
        return half_width
