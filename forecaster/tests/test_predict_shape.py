"""End-to-end shape / dtype / finiteness contract of ForecastOutput."""

import numpy as np

from forecaster import predict


def test_predict_shape_and_contract():
    x = np.zeros((5, 10, 101, 361), dtype=np.float32)
    out = predict(x)

    assert out.median.shape == (3, 101, 361)
    assert out.combined_std.shape == (3, 101, 361)
    assert out.q05.shape == (3, 101, 361)
    assert out.q95.shape == (3, 101, 361)
    assert out.interval_half_width.shape == (3, 101, 361)
    assert out.confidence_class.shape == (3, 101, 361)

    assert out.median.dtype == np.float32
    assert out.combined_std.dtype == np.float32
    assert out.q05.dtype == np.float32
    assert out.q95.dtype == np.float32
    assert out.interval_half_width.dtype == np.float32
    assert out.confidence_class.dtype == np.uint8

    for name in (
        "median",
        "combined_std",
        "q05",
        "q95",
        "interval_half_width",
        "confidence_class",
    ):
        field = getattr(out, name)
        assert np.isfinite(field).all(), f"non-finite values in {name}"

    assert out.median.min() >= 0.0
    assert out.median.max() <= 1.0
    assert out.q05.min() >= 0.0 and out.q05.max() <= 1.0
    assert out.q95.min() >= 0.0 and out.q95.max() <= 1.0
    assert (out.q05 <= out.q95).all()

    # Conformal half-widths must come from the two frozen strata only.
    for value in np.unique(out.interval_half_width):
        assert np.isclose(value, 0.12617) or np.isclose(value, 0.00206), value

    # Confidence classes are one of HIGH/MEDIUM/LOW/INVALID.
    assert set(np.unique(out.confidence_class).tolist()) <= {0, 1, 2, 255}

    assert out.metadata["seed_count"] == 3
    assert out.metadata["mc_passes"] == 20
    assert isinstance(out.metadata["artifacts_path"], str)
    assert isinstance(out.metadata["predict_timestamp"], str)
    assert "T" in out.metadata["predict_timestamp"]


def test_return_uncertainty_false_zero_fills_uncertainty():
    x = np.zeros((5, 10, 101, 361), dtype=np.float32)
    out = predict(x, return_uncertainty=False)

    assert out.median.shape == (3, 101, 361)
    assert out.median.dtype == np.float32
    assert np.isfinite(out.median).all()
    assert out.median.min() >= 0.0 and out.median.max() <= 1.0
    # uncertainty fields are zero-filled (documented contract)
    assert not out.combined_std.any()
    assert not out.interval_half_width.any()
    assert not out.confidence_class.any()
    np.testing.assert_array_equal(out.q05, out.median)
    np.testing.assert_array_equal(out.q95, out.median)
    assert out.metadata["mc_passes"] == 1
