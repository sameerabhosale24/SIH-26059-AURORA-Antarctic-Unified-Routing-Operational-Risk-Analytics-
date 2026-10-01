"""Response models for the data_version ledger and GET /api/health."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DataVersionOut(BaseModel):
    key: str
    version: int
    updated_at: Optional[str] = None
    source_ts: Optional[str] = None
    staleness: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class SourceHealth(BaseModel):
    configured: bool = False
    last_fetch: Optional[str] = None


class SchedulerHealth(BaseModel):
    running: bool = False
    next_sic_run: Optional[str] = None
    last_sic_run: Optional[dict[str, Any]] = None


class HealthOut(BaseModel):
    status: str
    db: bool
    redis: bool
    forecaster: bool = False
    sources: dict[str, SourceHealth] = Field(default_factory=dict)
    scheduler: SchedulerHealth = Field(default_factory=SchedulerHealth)


class StalenessMeta(BaseModel):
    sic_max_age_days: int = 0
    era5_max_age_days: int = 0
    cmems_max_age_days: int = 0
    thickness_max_age_days: int = 0
    sic_persistence_days: int = 0
    era5_persistence_days: int = 0
    cmems_analysis_used: bool = False
    nwp_used: bool = False
    max_staleness_days: int = 0
