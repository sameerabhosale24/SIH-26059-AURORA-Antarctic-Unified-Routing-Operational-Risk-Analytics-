"""Closest Point of Approach for AIS targets.

The two ships are treated as moving at constant velocity over the short
horizon CPA is defined for (tens of minutes), which is exactly the regime
where the straight-line assumption holds and the numbers a bridge team acts
on are stable.

Positions come in as latitude/longitude, velocities as speed over ground in
knots and course over ground in degrees. Internally everything is local
east/north nautical miles, which makes the maths a two-line projection onto
the relative velocity vector.
"""

from __future__ import annotations

import numpy as np

from app.utils.geo import KT_TO_MS, haversine_scalar_nm, local_en_offset_nm

#: A target reporting no movement still has a CPA: it is the range now.
_STALLED_SPEED_KT = 0.05


def _velocity_en(sog_kt, cog_deg) -> tuple[np.ndarray, np.ndarray]:
    """``(east, north)`` velocity in nautical miles per hour."""
    sog = np.asarray(sog_kt, dtype=np.float64)
    theta = np.asarray(cog_deg, dtype=np.float64) * (np.pi / 180.0)
    return sog * np.sin(theta), sog * np.cos(theta)


def cpa_tcpa(
    own_lat: float,
    own_lon: float,
    own_sog_kt: float,
    own_cog_deg: float,
    target_lat: float,
    target_lon: float,
    target_sog_kt: float,
    target_cog_deg: float,
    horizon_h: float = 60.0 / 60.0,
) -> tuple[float, float]:
    """Closest approach in nautical miles and the hours until it.

    Returns ``(cpa_nm, tcpa_h)``. ``tcpa_h`` is clamped to
    ``[0, horizon_h]``: an encounter already behind us reports a TCPA of
    zero with the current range as the CPA, which is what an alarm rule
    wants — the danger is now, not in the past.

    Missing or non-finite inputs return ``(+inf, 0.0)`` rather than
    raising: the alarm layer treats "cannot compute" as "no alarm", and a
    single malformed AIS sentence must not take the evaluator down.
    """
    values = (own_lat, own_lon, own_sog_kt, own_cog_deg,
              target_lat, target_lon, target_sog_kt, target_cog_deg)
    try:
        if not all(np.isfinite(float(v)) for v in values):
            return float("inf"), 0.0
    except (TypeError, ValueError):
        return float("inf"), 0.0

    east, north = local_en_offset_nm(own_lat, own_lon, target_lat, target_lon)
    rel_east = float(east)
    rel_north = float(north)

    own_ve, own_vn = _velocity_en(own_sog_kt, own_cog_deg)
    tgt_ve, tgt_vn = _velocity_en(target_sog_kt, target_cog_deg)
    dv_e = float(tgt_ve - own_ve)
    dv_n = float(tgt_vn - own_vn)

    speed2 = dv_e * dv_e + dv_n * dv_n
    if speed2 < _STALLED_SPEED_KT**2:
        # No relative motion: the range never changes.
        return float(np.hypot(rel_east, rel_north)), 0.0

    tcpa = -(rel_east * dv_e + rel_north * dv_n) / speed2
    tcpa = float(np.clip(tcpa, 0.0, max(horizon_h, 0.0)))

    cpa = float(np.hypot(rel_east + dv_e * tcpa, rel_north + dv_n * tcpa))
    return cpa, tcpa


def range_nm(own_lat: float, own_lon: float, target_lat: float, target_lon: float) -> float:
    """Current great-circle range, for rules that ask "how far now"."""
    try:
        return haversine_scalar_nm(own_lat, own_lon, target_lat, target_lon)
    except (TypeError, ValueError):
        return float("inf")


def target_speed_ms(sog_kt) -> float:
    """Convenience for rules comparing an AIS speed against a metric limit."""
    try:
        return float(sog_kt) * KT_TO_MS
    except (TypeError, ValueError):
        return float("nan")
