"""Input validation: shape is strict, dtype is cast."""

import numpy as np
import pytest

from forecaster import predict

FULL_SHAPE = (5, 10, 101, 361)


def test_wrong_lookback_raises():
    with pytest.raises(ValueError) as excinfo:
        predict(np.zeros((4, 10, 101, 361), dtype=np.float32))
    assert str(FULL_SHAPE) in str(excinfo.value)


def test_wrong_channel_count_raises():
    with pytest.raises(ValueError) as excinfo:
        predict(np.zeros((5, 9, 101, 361), dtype=np.float32))
    assert str(FULL_SHAPE) in str(excinfo.value)


def test_wrong_spatial_shape_raises():
    with pytest.raises(ValueError) as excinfo:
        predict(np.zeros((5, 10, 100, 360), dtype=np.float32))
    assert str(FULL_SHAPE) in str(excinfo.value)


def test_int32_input_is_cast_to_float32():
    x = np.zeros(FULL_SHAPE, dtype=np.int32)
    out = predict(x)
    assert out.median.shape == (3, 101, 361)
    assert out.median.dtype == np.float32
    assert np.isfinite(out.median).all()
    # the caller's array is untouched (rule 12)
    assert x.dtype == np.int32
    assert not x.any()
