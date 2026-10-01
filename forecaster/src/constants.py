"""constants.py — frozen physical and model constants for the AURORA kernel.

Every module in this package imports from here instead of hardcoding.
None of these values may change without retraining and recalibrating.
"""

ROI_LAT_MIN = -75.125
ROI_LAT_MAX = -49.875
ROI_LON_MIN = -10.125
ROI_LON_MAX = 80.125
ROI_SHAPE = (101, 361)
LOOKBACK_DAYS = 5
HORIZONS = 3
INPUT_CHANNELS = 10
CHANNEL_NAMES = [
    "SIC", "u10", "v10", "t2m",
    "uo", "vo", "thetao", "so", "zos",
    "SIC_prev_year",
]
MIZ_THRESHOLD = 0.15
MC_PASSES = 20
SEED_COUNT = 3
MODEL_PARAM_COUNT = 270147

# Expected shape of the input window passed to predict().
INPUT_SHAPE = (LOOKBACK_DAYS, INPUT_CHANNELS, ROI_SHAPE[0], ROI_SHAPE[1])

# Expected shape of every field of ForecastOutput().
OUTPUT_SHAPE = (HORIZONS, ROI_SHAPE[0], ROI_SHAPE[1])
