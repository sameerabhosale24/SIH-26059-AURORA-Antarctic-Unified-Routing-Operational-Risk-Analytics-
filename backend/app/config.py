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
    AURORA_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.AURORA_CORS_ORIGINS.split(",") if origin.strip()]

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
