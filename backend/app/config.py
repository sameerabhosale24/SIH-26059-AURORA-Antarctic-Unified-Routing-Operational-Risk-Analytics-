"""
Runtime configuration.

Read from the process environment first, then `.env`. `DATABASE_URL` and
`AURORA_JWT_SECRET` are required on purpose: a backend that cannot reach the
database or cannot sign a token must refuse to start instead of failing on
the operator's first request.
"""

from functools import lru_cache

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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.AURORA_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
