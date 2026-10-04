"""Operational alarms and their acknowledgement.

``type`` is a closed set — ``ukc | collision | ice | iceberg | off_course |
forecast_stale`` — because the console's alarm panel keys its labels off it
and an unknown type would render as a blank row. New rules must map onto
one of these rather than invent a seventh.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlarmOut(BaseModel):
    id: int
    ts: str | None = None
    vessel_id: str = ""
    severity: str = "warning"
    type: str
    message: str = ""
    lat: float | None = None
    lon: float | None = None
    payload: dict = Field(default_factory=dict)
    acked_at: str | None = None
    acked_by: str | None = None


class AckRequest(BaseModel):
    """``POST /api/alarms/{id}/ack``.

    The operator's identity is recorded with the acknowledgement so the
    audit trail says who saw it, not just when.
    """

    acked_by: str = ""
