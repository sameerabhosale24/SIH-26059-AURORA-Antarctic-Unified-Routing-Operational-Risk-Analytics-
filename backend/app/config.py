"""
Runtime configuration.

Read from the process environment first, then `.env`. `DATABASE_URL` and
`AURORA_JWT_SECRET` are required on purpose: a backend that cannot reach the
database or cannot sign a token must refuse to start instead of failing on the
operator's first request.

Every data-source credential is optional. An adapter with no credentials is
"not configured": it logs, returns nothing, and never fabricates a field.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    AURORA_JWT_SECRET: str
    AURORA_JWT_EXPIRY_DAYS: int = 7
    AURORA_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:4173,http://127.0.0.1:4173,http://localhost:3000"

    # ------------------------------------------------------------------
    # ROI — the single 0.25 degree grid every field is regridded onto.
    # The bounds are EXCLUSIVE on the max side: the grid is
    # `min + arange(n) * ROI_RES`, which is exactly (101, 361).
    # ------------------------------------------------------------------
    ROI_LON_MIN: float = -10.125
    ROI_LAT_MIN: float = -75.125
    ROI_LON_MAX: float = 80.125
    ROI_LAT_MAX: float = -49.875

    # Projection used for the on-screen SIC frames.
    LCC_PROJ: str = (
        "+proj=lcc +lat_1=-45 +lat_2=-65 +lat_0=-55 +lon_0=35 +x_0=0 +y_0=0 "
        "+datum=WGS84 +units=m +no_defs"
    )

    # Storage root for regridded fields, SIC frames and raw arrays.
    STORAGE_ROOT: Path = Path("./data")

    # ------------------------------------------------------------------
    # Data source credentials — all optional by design.
    # ------------------------------------------------------------------
    NSIDC_USERNAME: str | None = None
    NSIDC_PASSWORD: str | None = None
    CDSAPI_URL: str | None = None
    CDSAPI_KEY: str | None = None
    CMEMS_USERNAME: str | None = None
    CMEMS_PASSWORD: str | None = None
    AISSTREAM_API_KEY: str | None = None
    BYU_SCP_URL: str | None = None
    GPS_HOST: str | None = None
    GPS_PORT: int | None = None

    # ------------------------------------------------------------------
    # Forecaster (vendored inside AURORA at AURORA/forecaster/)
    # ------------------------------------------------------------------
    SIC_ARTIFACTS_PATH: Path = Path("../forecaster/artifacts")
    FORECASTER_MAX_STALENESS_DAYS: int = 7
    FORECASTER_DEGRADED_DAYS: int = 10
    STALENESS_PENALTY_PER_DAY: float = 0.05

    # Scheduling
    DAILY_JOB_HOUR: int = 3

    # ------------------------------------------------------------------
    # Route optimizer (PART 2)
    # ------------------------------------------------------------------
    #: Under-keel clearance required below the keel, in metres.
    ROUTE_UKC_MARGIN_M: float = 2.0
    ROUTE_WEIGHT_ICE: float = 1.0
    ROUTE_WEIGHT_THICKNESS: float = 1.5
    ROUTE_WEIGHT_ICEBERG: float = 2.0
    ROUTE_WEIGHT_WEATHER: float = 0.5
    ROUTE_WEIGHT_FUEL: float = 1.0
    ROUTE_WEIGHT_CURRENT: float = 0.3
    #: Comma-separated hours of day (UTC) for the 6-hourly route job.
    ROUTE_JOB_HOURS: str = "0,6,12,18"
    #: Safety bound on the A* expansion loop.
    ROUTE_MAX_EXPANSIONS: int = 500_000
    #: An alternative route must differ from every kept route by more than
    #: this Jaccard overlap to be worth showing.
    ROUTE_ALT_MAX_OVERLAP: float = 0.8
    #: Defaults for Cape Town -> the Antarctic stations.
    DEFAULT_DEPARTURE_LAT: float = -33.9
    DEFAULT_DEPARTURE_LON: float = 18.4
    DEFAULT_DESTINATIONS: str = "-70.767,11.733;-69.397,76.247"

    #: Alarm thresholds that are not already vessel fields.
    ALARM_CPA_NM: float = 1.0
    ALARM_OFF_COURSE_NM: float = 2.0
    ALARM_ICEBERG_NM: float = 20.0
    ALARM_STALENESS_HOURS: int = 36

    # ------------------------------------------------------------------
    # Real-time relays (PART 2)
    # ------------------------------------------------------------------
    #: The vessel row the GPS and AIS relays publish against. AURORA tracks
    #: exactly one own ship; the fleet is blueprints, not live telemetry.
    OWN_SHIP_VESSEL_ID: int = 1
    #: An AIS sighting older than this is no longer a live target: it is kept
    #: for history but excluded from CPA, from GET /api/ais/latest and from
    #: the collision rule.
    AIS_FRESHNESS_MINUTES: int = 30
    #: Seconds between weather samples at the vessel position.
    WEATHER_POLL_SECONDS: int = 300
    #: Seconds between alarm-engine passes.
    ALARM_POLL_SECONDS: int = 60
    #: How long a relay waits before reconnecting to a dead socket.
    RELAY_RECONNECT_SECONDS: int = 10
    #: A rule must not re-fire within this many hours of its previous ack,
    #: otherwise acknowledging a persistent condition only mutes it for one
    #: pass.
    ALARM_REARM_HOURS: int = 1

    # ------------------------------------------------------------------
    # Storage and retention (PART 2)
    # ------------------------------------------------------------------
    SIC_FRAMES_RETENTION_DAYS: int = 30
    CLEANUP_JOB_HOUR: int = 4
    WARN_SIC_FRAMES_MB: int = 500
    WARN_FIELDS_MB: int = 2000

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.AURORA_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def route_job_hours(self) -> list[int]:
        hours = sorted({int(h) for h in self.ROUTE_JOB_HOURS.split(",") if h.strip()})
        for hour in hours:
            if not 0 <= hour <= 23:
                raise ValueError(f"ROUTE_JOB_HOURS contains {hour}, outside 0-23")
        return hours or [0, 6, 12, 18]

    @property
    def default_destinations(self) -> list[tuple[float, float]]:
        """``[(lat, lon), ...]`` parsed from ``DEFAULT_DESTINATIONS``."""
        points: list[tuple[float, float]] = []
        for chunk in self.DEFAULT_DESTINATIONS.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            lat_text, _, lon_text = chunk.partition(",")
            points.append((float(lat_text), float(lon_text)))
        return points

    # Convenience getters used by adapters' is_configured() checks. They
    # return None instead of an empty string so `bool("")` never reads as a
    # configured credential.
    def _opt(self, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
