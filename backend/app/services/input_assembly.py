"""Assemble the 5-day x 10-channel input window for the forecaster.

This is the module where a plausible-looking forecast is either earned or
lost. Three rules are enforced here and nowhere else may relax them:

1. **The SIC channel is always anchored to a real NSIDC observation.**
   Day D uses the observation for D, or — if D has not been published yet —
   the most recent prior observation. A forecast is never an input, so
   forecast feedback is structurally impossible: forecasts live in
   ``data/sic_arrays`` and ``data/sic_frames``, observations in
   ``data/fields/sic``, and this module only ever reads the latter.

2. **Persistence is bounded and reported.** Every substitution is counted,
   surfaced in the staleness dict, and can be inspected by the operator.
   Nothing silently becomes "fresh".

3. **Missing data raises.** A channel with nothing on disk is a
   ``ValueError``, not zeros. Zero is a legitimate SIC value (open water)
   and a legitimate current (no flow); using it for "unknown" would make
   the model confidently wrong instead of honestly absent.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np

from app.adapters import ADAPTERS
from app.services.field_storage import latest_available_date, read_field
from app.utils.constants import HORIZONS, INPUT_CHANNELS, LOOKBACK_DAYS, ROI_SHAPE

logger = logging.getLogger("aurora.input_assembly")

# Storage roots, one per channel group.
SIC_SOURCE = "sic"
WEATHER_SOURCE = "weather"
CURRENTS_SOURCE = "currents"
THICKNESS_SOURCE = "ice_thickness"

# Channel slice indices inside the input tensor.
CH_SIC = 0
CH_U10, CH_V10, CH_T2M = 1, 2, 3
CH_UO, CH_VO, CH_THETAO, CH_SO, CH_ZOS = 4, 5, 6, 7, 8
CH_SIC_PREV_YEAR = 9

WEATHER_CHANNELS = (CH_U10, CH_V10, CH_T2M)
CURRENTS_CHANNELS = (CH_UO, CH_VO, CH_THETAO, CH_SO, CH_ZOS)

#: No operational NWP feed exists in PART 1, so ERA5/ERA5T is always the
#: most recent surface field available. Kept as a named flag so PART 2 can
#: wire a real NWP source in one place.
NWP_CONFIGURED = False

#: Skip days when logging adapter availability (one line per source, not per day).
_ADAPTER_LOGGED: set[str] = set()


def input_window_shape() -> tuple[int, int, int, int]:
    return (LOOKBACK_DAYS, INPUT_CHANNELS, *ROI_SHAPE)


def window_days(target_date: date) -> list[date]:
    """The five days ``[N-4, N-3, N-2, N-1, N]``, oldest first."""
    return [target_date - timedelta(days=offset) for offset in range(LOOKBACK_DAYS - 1, -1, -1)]


def _log_unconfigured() -> None:
    """Log ``adapter {name} not configured`` once per adapter per process."""
    for name in ("nsidc", "era5", "cmems", "cs2smos"):
        if name in _ADAPTER_LOGGED:
            continue
        adapter = ADAPTERS.get(name)
        if adapter is not None and not adapter.is_configured():
            logger.warning("adapter %s not configured", name)
        _ADAPTER_LOGGED.add(name)


def _resolve(
    source: str, days: list[date]
) -> tuple[list[np.ndarray], list[int], list[bool]] | None:
    """Resolve each day to a stored field, its age, and whether it matched.

    Returns ``None`` when the source has nothing on disk for the whole
    window — the caller turns that into a ``ValueError`` rather than
    silently dropping a channel.
    """
    arrays: list[np.ndarray] = []
    ages: list[int] = []
    exact: list[bool] = []
    for day in days:
        array = read_field(source, day)
        matched = array is not None
        used = day
        if array is None:
            used = latest_available_date(source, day)
            if used is None:
                logger.warning("no %s data on or before %s", source, day.isoformat())
                return None
            array = read_field(source, used)
            if array is None:  # pragma: no cover — file vanished mid-scan
                logger.warning("%s/%s vanished while resolving", source, used.isoformat())
                return None
        arrays.append(array)
        ages.append(max((day - used).days, 0))
        exact.append(matched)
    return arrays, ages, exact


def _require(resolved, source: str, channel_label: str):
    if resolved is None:
        raise ValueError(
            f"No data available for channel {channel_label}, cannot assemble "
            f"(source '{source}' has no files on or before the requested window). "
            "Configure the adapter or populate the store; AURORA will not "
            "fabricate a field."
        )
    return resolved


def _validate(array: np.ndarray, label: str, expected: tuple[int, ...]) -> np.ndarray:
    if array.shape != expected:
        raise ValueError(
            f"{label} has shape {array.shape}, expected {expected}; "
            "the store contains a field written for a different grid"
        )
    if not np.isfinite(np.asarray(array, dtype=np.float32)).any():
        raise ValueError(
            f"{label} is entirely NaN — there is no usable observation in it"
        )
    return np.ascontiguousarray(array, dtype=np.float32)


def assemble_input_window(target_date: date) -> tuple[np.ndarray, dict]:
    """Build the ``[5, 10, 101, 361]`` input window and its staleness record.

    Raises ``ValueError`` when a required channel has no data at all. The
    SIC scheduler catches that, skips the run, and raises a
    ``forecast_stale`` alarm — an absent forecast is survivable, a
    fabricated one is not.
    """
    _log_unconfigured()
    days = window_days(target_date)
    tensor = np.full(input_window_shape(), np.nan, dtype=np.float32)

    # ---------------------------------------------------------------- SIC
    sic = _require(_resolve(SIC_SOURCE, days), SIC_SOURCE, "SIC")
    sic_arrays, sic_ages, sic_exact = sic
    for index, (day, array) in enumerate(zip(days, sic_arrays)):
        tensor[index, CH_SIC] = _validate(array, f"SIC[{day}]", ROI_SHAPE)
    sic_max_age = max(sic_ages)
    sic_persistence_days = max(
        (age for age, matched in zip(sic_ages, sic_exact) if not matched), default=0
    )

    # -------------------------------------------------------- SIC_prev_year
    # Exactly 365 days back, no persistence fallback: a stale "previous
    # year" field would quietly become a second current-year channel and
    # the model would learn nothing from it.
    prev_year_arrays = []
    for day in days:
        wanted = day - timedelta(days=365)
        array = read_field(SIC_SOURCE, wanted)
        if array is None:
            raise ValueError(
                f"No data available for channel SIC_prev_year, cannot assemble "
                f"(no observation for {wanted.isoformat()}, which is exactly "
                "365 days before an input day). AURORA will not substitute a "
                "different date or a forecast for this channel."
            )
        prev_year_arrays.append(_validate(array, f"SIC_prev_year[{wanted}]", ROI_SHAPE))
    for index, array in enumerate(prev_year_arrays):
        tensor[index, CH_SIC_PREV_YEAR] = array

    # ------------------------------------------------------------- ERA5
    weather = _require(_resolve(WEATHER_SOURCE, days), WEATHER_SOURCE, "u10/v10/t2m")
    weather_arrays, weather_ages, weather_exact = weather
    for index, (day, array) in enumerate(zip(days, weather_arrays)):
        stack = _validate(array, f"weather[{day}]", (3, *ROI_SHAPE))
        tensor[index, WEATHER_CHANNELS[0]] = stack[0]
        tensor[index, WEATHER_CHANNELS[1]] = stack[1]
        tensor[index, WEATHER_CHANNELS[2]] = stack[2]
    era5_max_age = max(weather_ages)
    era5_persistence_days = max(
        (age for age, matched in zip(weather_ages, weather_exact) if not matched), default=0
    )

    # ------------------------------------------------------------- CMEMS
    currents = _require(_resolve(CURRENTS_SOURCE, days), CURRENTS_SOURCE, "uo/vo/thetao/so/zos")
    currents_arrays, currents_ages, currents_exact = currents
    for index, (day, array) in enumerate(zip(days, currents_arrays)):
        stack = _validate(array, f"currents[{day}]", (5, *ROI_SHAPE))
        for offset, channel in enumerate(CURRENTS_CHANNELS):
            tensor[index, channel] = stack[offset]
    cmems_max_age = max(currents_ages)
    cmems_analysis_used = all(currents_exact)

    # ---------------------------------------------------------- thickness
    # Not one of the ten forecaster channels — it feeds the route optimizer.
    # Tracked for staleness, but absent data must not block the forecast.
    thickness = _resolve(THICKNESS_SOURCE, days)
    if thickness is None:
        logger.warning(
            "adapter cs2smos not configured or no thickness on disk; "
            "thickness staleness will be reported as absent"
        )
        thickness_max_age = -1
    else:
        _, thickness_ages, _ = thickness
        thickness_max_age = max(thickness_ages)

    staleness = {
        "sic_max_age_days": int(sic_max_age),
        "era5_max_age_days": int(era5_max_age),
        "cmems_max_age_days": int(cmems_max_age),
        "thickness_max_age_days": int(thickness_max_age),
        "sic_persistence_days": int(sic_persistence_days),
        "era5_persistence_days": int(era5_persistence_days),
        "cmems_analysis_used": bool(cmems_analysis_used),
        "nwp_used": bool(NWP_CONFIGURED),
        # Gate on the channels that actually reach the model. Thickness is
        # excluded deliberately: it is not an input, so a stale thickness
        # must not be able to suppress an otherwise valid forecast.
        "max_staleness_days": int(max(sic_max_age, era5_max_age, cmems_max_age)),
    }

    bad = ~np.isfinite(tensor)
    if bad.any():
        where = np.argwhere(bad)
        day_index, channel, row, col = (int(v) for v in where[0])
        raise ValueError(
            f"No data available for channel {channel} at day index {day_index} "
            f"(cell {row}, {col}), cannot assemble — the window is incomplete "
            "and AURORA will not fill it with zeros."
        )

    tensor = tensor.astype(np.float32, copy=False)
    logger.info(
        "assembled input window for %s: shape=%s max_staleness_days=%s "
        "sic_persistence=%s era5_persistence=%s cmems_analysis_used=%s",
        target_date.isoformat(), tensor.shape,
        staleness["max_staleness_days"],
        staleness["sic_persistence_days"],
        staleness["era5_persistence_days"],
        staleness["cmems_analysis_used"],
    )
    return tensor, staleness


def horizons() -> int:
    return HORIZONS
