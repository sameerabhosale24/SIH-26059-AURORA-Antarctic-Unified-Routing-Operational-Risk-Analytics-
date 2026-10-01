"""Statelessness: identical input -> identical output, input never mutated."""

import numpy as np

from forecaster import predict


def test_predict_is_deterministic_and_stateless():
    rng = np.random.default_rng(0)
    # Raw physical units: SIC channels in [0, 1], plausible forcing elsewhere.
    x = rng.random((5, 10, 101, 361), dtype=np.float32)
    x[:, 0] *= 1.0   # SIC
    x[:, 9] *= 1.0   # SIC_prev_year
    x_before = x.copy()

    out_1 = predict(x)
    out_2 = predict(x)

    # Same input twice -> bitwise identical output (torch.manual_seed(0)).
    np.testing.assert_array_equal(out_1.median, out_2.median)
    np.testing.assert_array_equal(out_1.combined_std, out_2.combined_std)
    np.testing.assert_array_equal(out_1.q05, out_2.q05)
    np.testing.assert_array_equal(out_1.q95, out_2.q95)
    np.testing.assert_array_equal(
        out_1.interval_half_width, out_2.interval_half_width
    )
    np.testing.assert_array_equal(out_1.confidence_class, out_2.confidence_class)

    # The input tensor is never modified in place (rule 12).
    np.testing.assert_array_equal(x, x_before)
    assert x.dtype == np.float32

    # The forecast is never fed back in: a *different* input yields a
    # different forecast, i.e. no stored state is shared between calls.
    x2 = x.copy()
    x2[:, 0] = np.flip(x2[:, 0], axis=0)
    out_3 = predict(x2)
    assert not np.array_equal(out_1.median, out_3.median)
    np.testing.assert_array_equal(x2[:, 0], np.flip(x[:, 0], axis=0))
