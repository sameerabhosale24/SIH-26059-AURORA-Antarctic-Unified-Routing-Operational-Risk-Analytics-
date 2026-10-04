"""Frozen geometry of the AURORA region of interest.

Every field in the system — SIC, winds, currents, thickness, bathymetry — is
regridded onto this one 0.25 degree grid before it is used. The shape is
frozen by the forecaster's weights: `[101, 361]` with 10 channels and a
5-day lookback.

The MAX bounds are EXCLUSIVE, exactly like `numpy.arange(min, max, res)`:

    lat = -75.125 + arange(101) * 0.25   -> -75.125 .. -50.125
    lon = -10.125 + arange(361) * 0.25   -> -10.125 ..  79.875

so `(ROI_LAT_MAX - ROI_LAT_MIN) / ROI_RES == 101` and
`(ROI_LON_MAX - ROI_LON_MIN) / ROI_RES == 361`. Cell centres therefore sit
half a cell off a conventional whole-quarter grid, which is why the
lat/lon sources must be sampled rather than sliced.
"""

ROI_LAT_MIN = -75.125
ROI_LAT_MAX = -49.875
ROI_LON_MIN = -10.125
ROI_LON_MAX = 80.125

ROI_SHAPE = (101, 361)
ROI_RES = 0.25

# Equal-area-ish conic for the Southern Ocean; used for every PNG frame the
# map consumes.
LCC_PROJ = (
    "+proj=lcc +lat_1=-45 +lat_2=-65 +lat_0=-55 +lon_0=35 +x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)

# Source CRS of the grid itself.
ROI_CRS = "EPSG:4326"

# ---------------------------------------------------------------------------
# Route grid — the canvas the SIC display frames are painted on.
#
# The SIC grid above is a *model* grid: `[101, 361]` over 10°W–80°E and
# 75°S–50°S, frozen by the forecaster's weights and therefore untouchable.
# A PNG whose extent is that grid ends exactly where the data ends, which is
# how the SIC layer used to land on the map as a rectangle with a hard edge
# at 50°S.
#
# The route grid is a *display* grid instead: `[185, 321]` at 0.25°, the same
# resolution as the SIC grid so the two can be matched cell-to-cell without
# resampling. It spans the Cape Town → Antarctica corridor the map frames
# (5°E–85°E, 78°S–32°S) and, in latitude, the whole SIC region plus the water
# north of it.
#
# It is deliberately *narrower in longitude than the SIC grid* (321 cells vs
# 361): the SIC product runs 10°W–80°E, the corridor runs 10°E–85°E, and the
# canvas only has to hold what the map shows. The westernmost SIC cells
# (10°W–5°E) therefore have no home on the canvas and are left out rather
# than squeezed — see `place_sic_in_route_grid_nan`, which places by nearest
# cell centre and marks everything more than one cell away as no-data.
#
# MAX bounds are EXCLUSIVE, exactly like the ROI bounds above:
#
#     lat = -78.0 + arange(185) * 0.25  -> -78.00 .. -32.00
#     lon =   5.0 + arange(321) * 0.25  ->   5.00 ..  85.00
ROUTE_ROI_LAT_MIN = -78.0
ROUTE_ROI_LAT_MAX = -31.75
ROUTE_ROI_LON_MIN = 5.0
ROUTE_ROI_LON_MAX = 85.25

ROUTE_SHAPE = (185, 321)
ROUTE_RES = 0.25

# Named channels of the forecaster input window, in frozen order.
CHANNEL_NAMES = [
    "SIC",             # 0
    "u10",             # 1
    "v10",             # 2
    "t2m",             # 3
    "uo",              # 4
    "vo",              # 5
    "thetao",          # 6
    "so",              # 7
    "zos",             # 8
    "SIC_prev_year",   # 9
]

LOOKBACK_DAYS = 5
HORIZONS = 3
INPUT_CHANNELS = len(CHANNEL_NAMES)

# Source field directories under STORAGE_ROOT/fields/.
SOURCE_DIRS = {
    "sic": "sic",
    "currents": "currents",
    "weather": "weather",
    "ice_thickness": "ice_thickness",
    "bathymetry": "",  # bathymetry is a single file, not a date series
}
