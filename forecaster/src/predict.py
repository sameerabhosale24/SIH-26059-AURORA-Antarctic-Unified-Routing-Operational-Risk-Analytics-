"""predict.py — the single public entry point of the forecaster kernel.

    from forecaster import predict, ForecastOutput
    output = predict(input_window)          # [5, 10, 101, 361] -> ForecastOutput

This module is a pure function of its argument. It never reads data from
the filesystem (the frozen artifacts are loaded once, at import time, by
artifacts_loader), never looks at the calendar date, never writes anything,
and keeps no state between calls — the forecast of one call is never fed
back in as input to the next (rule 11).

Determinism: torch.manual_seed(0) is set at the start of every call, so the
MC-Dropout passes are reproducible for a given input and artifact set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import torch

from .artifacts_loader import get_artifacts
from .constants import (
    INPUT_SHAPE,
    MC_PASSES,
    SEED_COUNT,
)

logger = logging.getLogger(__name__)

# 90% two-sided Gaussian quantile used for the RAW (non-conformal) interval.
GAUSS_Z90 = 1.645


@dataclass
class ForecastOutput:
    """3-day SIC forecast with uncertainty, in ROI lat/lon grid order.

    All fields share the shape [3, 101, 361] (horizon, lat, lon).
    """

    median: np.ndarray               # [3, 101, 361], float32, SIC 0-1
    combined_std: np.ndarray         # [3, 101, 361], float32
    q05: np.ndarray                  # [3, 101, 361], float32
    q95: np.ndarray                  # [3, 101, 361], float32
    interval_half_width: np.ndarray  # [3, 101, 361], float32 (conformal)
    confidence_class: np.ndarray     # [3, 101, 361], uint8
    metadata: dict


def _require_finite(name: str, array: np.ndarray) -> None:
    """Rule 13: never return NaN or inf — raise with the cell coordinates."""
    bad = ~np.isfinite(array)
    n_bad = int(bad.sum())
    if n_bad:
        coords = np.argwhere(bad)[0]
        coords = tuple(int(c) for c in coords)
        raise RuntimeError(
            f"non-finite value in ForecastOutput.{name}: {n_bad} cell(s), "
            f"first at index {coords} (h, y, x). Aborting instead of "
            f"returning NaN/inf."
        )


def _mc_passes(model: torch.nn.Module, x: torch.Tensor, n_passes: int) -> np.ndarray:
    """Run `n_passes` dropout-enabled forwards for one seed.

    Returns [n_passes, 3, H, W] float32.
    """
    model.train()  # enables Dropout2d for MC-Dropout; no BatchNorm exists
    try:
        passes = []
        for _ in range(n_passes):
            pred = model(x)  # [1, 3, H, W]
            passes.append(pred[0].detach().cpu().numpy())
    finally:
        model.eval()  # leave the cached artifact in eval mode
    return np.stack(passes, axis=0).astype(np.float32)


def _ensemble_passes(
    models: list[torch.nn.Module],
    x: torch.Tensor,
    n_passes: int,
) -> np.ndarray:
    """Run all seeds x passes. Returns [SEED_COUNT, n_passes, 3, H, W]."""
    with torch.no_grad():
        per_seed = [_mc_passes(model, x, n_passes) for model in models]
    return np.stack(per_seed, axis=0)


def _run_models(
    models: list[torch.nn.Module],
    x: torch.Tensor,
    n_passes: int,
    device: torch.device,
) -> tuple[np.ndarray, torch.device]:
    """Forward all seeds, retrying on CPU if CUDA runs out of memory."""
    try:
        for model in models:
            model.to(device)
        x = x.to(device)
        return _ensemble_passes(models, x, n_passes), device
    except RuntimeError as exc:
        if device.type != "cuda" or "out of memory" not in str(exc).lower():
            raise
        logger.warning(
            "CUDA OOM during MC-Dropout passes (%s); retrying the whole "
            "ensemble on CPU.", exc,
        )
        try:
            torch.cuda.empty_cache()
        except Exception:  # pragma: no cover - cache flush is best effort
            pass
        cpu = torch.device("cpu")
        for model in models:
            model.to(cpu)
        x = x.to(cpu)
        # Raise (never swallow) if the CPU retry also fails.
        return _ensemble_passes(models, x, n_passes), cpu


def predict(
    input_window: np.ndarray,
    return_uncertainty: bool = True,
) -> ForecastOutput:
    """Forecast 3 days of Antarctic SIC from a 5-day input window.

    Parameters
    ----------
    input_window : np.ndarray
        Shape [5, 10, 101, 361]. Channels in RAW physical units, in the
        frozen order (see constants.CHANNEL_NAMES): SIC (0-1), u10, v10,
        t2m (K), uo, vo, thetao (K), so, zos, SIC_prev_year (0-1).
        Any dtype is accepted and cast to float32; the array is copied, so
        the caller's data is never modified in place.
    return_uncertainty : bool, default True
        When False, one forward pass per seed is run instead of the full
        MC-Dropout ensemble and combined_std / q05 / q95 /
        interval_half_width / confidence_class are zero-filled. Use only if
        you do not intend to consume the uncertainty fields.

    Returns
    -------
    ForecastOutput
        median [3, 101, 361] float32 in [0, 1] (mean of the 3 per-seed
        MC-Dropout means), combined_std [3, 101, 361] float32,
        q05/q95 [3, 101, 361] float32 raw Gaussian bounds clipped to [0, 1],
        interval_half_width [3, 101, 361] float32 (frozen stratified
        conformal — the authoritative interval), confidence_class
        [3, 101, 361] uint8, and a metadata dict.

    Notes
    -----
    * Deterministic: torch.manual_seed(0) at the top of every call makes the
      MC-Dropout passes reproducible for the same input and artifacts.
    * Stateless: no state is stored between calls; each call is independent
      and forecast output is never fed back in as input (rule 11).
    * The conformal quantiles are frozen; this function never widens them
      for staleness (rule 9) — the backend applies that penalty.
    """
    # Reproducible MC-Dropout (documented above).
    torch.manual_seed(0)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # 1. Validate input: cast to float32 on a private copy (rules 12/13).
    array = np.array(input_window, dtype=np.float32, copy=True)
    if array.shape != INPUT_SHAPE:
        raise ValueError(
            f"input_window must have shape {INPUT_SHAPE} "
            f"({len(INPUT_SHAPE)} days x 10 channels x H x W), got {array.shape}"
        )

    # 2. Standardize with the frozen stats (NaN -> 0 after standardizing).
    artifacts = get_artifacts()
    x_np = artifacts.scaler.standardize(array)

    # 3. Torch tensor on CUDA when available, else CPU.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    x = torch.from_numpy(x_np).unsqueeze(0)  # [1, 5, 10, H, W] (B=1)

    # 4. MC-Dropout over 3 seeds (1 pass when uncertainty is not wanted).
    n_passes = MC_PASSES if return_uncertainty else 1
    mc, device = _run_models(artifacts.models, x, n_passes, device)
    logger.debug("predict: %d seeds x %d passes on %s", SEED_COUNT, n_passes, device)

    # 5. Ensemble statistics.
    seed_means = mc.mean(axis=1)                     # [3, 3, H, W]
    seed_stds = mc.std(axis=1)                       # [3, 3, H, W]
    ens_mean = seed_means.mean(axis=0)               # [3, H, W]
    ens_std = seed_means.std(axis=0)                 # [3, H, W]
    mc_std_avg = seed_stds.mean(axis=0)              # [3, H, W]
    combined_std = np.sqrt(ens_std**2 + mc_std_avg**2).astype(np.float32)

    # Median = ensemble mean of the per-seed means (not the median of passes).
    pre_clamp = ens_mean.astype(np.float32)
    median = np.clip(pre_clamp, 0.0, 1.0).astype(np.float32)
    clamped = int(np.count_nonzero(pre_clamp != median))
    if clamped:
        logger.info(
            "predict: clamping moved %d/%d median cells into [0, 1] "
            "(should be zero or near-zero)", clamped, median.size,
        )

    if not return_uncertainty:
        # Uncertainty deliberately not computed: zero-fill every uncertainty
        # field (each field gets its own array — no aliasing between fields).
        q05 = median.copy()
        q95 = median.copy()
        half_width = np.zeros_like(median)
        combined_std = np.zeros_like(median)
        confidence = np.zeros(median.shape, dtype=np.uint8)
    else:
        # 6. Raw Gaussian quantiles (NOT the conformal interval).
        q05 = np.clip(median - GAUSS_Z90 * combined_std, 0.0, 1.0).astype(np.float32)
        q95 = np.clip(median + GAUSS_Z90 * combined_std, 0.0, 1.0).astype(np.float32)
        # 7. Frozen stratified conformal interval (authoritative).
        half_width = artifacts.conformal.compute(median, true_sic=None)
        # 8. Confidence classes (frozen p33/p66 thresholds).
        confidence = artifacts.confidence.classify(
            combined_std, median, artifacts.valid_mask
        )

    # 9. Metadata (timestamp is recorded, never used in any computation).
    metadata = {
        "model_version": artifacts.metadata["model_version"],
        "seed_count": SEED_COUNT,
        "mc_passes": n_passes,
        "artifacts_path": artifacts.metadata["artifacts_path"],
        "predict_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 13. Never return NaN/inf — verify every field before returning.
    for name, field in (
        ("median", median),
        ("combined_std", combined_std),
        ("q05", q05),
        ("q95", q95),
        ("interval_half_width", half_width),
        ("confidence_class", confidence),
    ):
        _require_finite(name, field)

    return ForecastOutput(
        median=median,
        combined_std=combined_std,
        q05=q05,
        q95=q95,
        interval_half_width=half_width,
        confidence_class=confidence,
        metadata=metadata,
    )
