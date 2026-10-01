"""Array hygiene shared by every adapter.

Three rules enforced here so no adapter has to remember them:

* the ROI shape is exact — wrong shape raises, it is never padded;
* missing data is NaN — never zeros;
* stacking is explicit — a channel axis is added deliberately, not by accident.
"""

from __future__ import annotations

import numpy as np

from app.utils.constants import ROI_SHAPE


def as_float32(array: np.ndarray, name: str = "field") -> np.ndarray:
    """Coerce to float32, leaving NaN untouched."""
    return np.ascontiguousarray(array, dtype=np.float32)


def validate_roi(array: np.ndarray, name: str = "field") -> np.ndarray:
    """Assert the array is exactly ``[101, 361]`` and return it as float32."""
    if array.shape != ROI_SHAPE:
        raise ValueError(
            f"{name} regridded to shape {array.shape}, expected {ROI_SHAPE}. "
            "Refusing to pad or crop — a misaligned field is worse than none."
        )
    return as_float32(array, name)


def stack_channels(arrays: list[np.ndarray], name: str = "field") -> np.ndarray:
    """Stack ``[101, 361]`` frames into ``[C, 101, 361]``."""
    if not arrays:
        raise ValueError(f"{name}: nothing to stack")
    checked = [validate_roi(a, f"{name}[{i}]") for i, a in enumerate(arrays)]
    return np.stack(checked, axis=0).astype(np.float32)


def coarsen_min(array: np.ndarray, factor: int, name: str = "field") -> np.ndarray:
    """Block-reduce with ``min()``.

    Used for bathymetry: taking the shallowest sounding in a cell is the
    conservative choice for under-keel clearance, and the safe one.
    """
    if factor < 1:
        raise ValueError("factor must be >= 1")
    rows, cols = array.shape
    if rows % factor or cols % factor:
        raise ValueError(
            f"{name} shape {array.shape} is not divisible by the coarsening "
            f"factor {factor}; crop the source to a multiple first."
        )
    reduced = array.reshape(rows // factor, factor, cols // factor, factor)
    return np.min(reduced, axis=(1, 3)).astype(np.float32)


def nan_summary(array: np.ndarray) -> dict:
    """Fraction of finite cells — used in logs so a fully-NaN field is obvious."""
    finite = np.isfinite(array)
    return {
        "size": int(array.size),
        "finite": int(finite.sum()),
        "nan": int((~finite).sum()),
        "finite_fraction": float(finite.mean()) if array.size else 0.0,
    }
