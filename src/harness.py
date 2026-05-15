"""Meeting state model.

Phase 1 holds only the typed data model.
The system-prompt builder is added in Phase 2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Objective(BaseModel):
    id: str
    objective: str
    success_criteria: str


class ObjectiveStatus(BaseModel):
    status: Literal["open", "partial", "covered"] = "open"
    note: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Finding(BaseModel):
    topic: str
    content: str
    ts: datetime = Field(default_factory=_utc_now)


class Followup(BaseModel):
    item: str
    ts: datetime = Field(default_factory=_utc_now)


class MeetingState(BaseModel):
    run_id: str
    briefing_path: str
    target_minutes: int
    started_at: datetime
    briefing_markdown: str
    objectives: list[Objective]
    tracker: dict[str, ObjectiveStatus]
    findings: list[Finding] = Field(default_factory=list)
    followups: list[Followup] = Field(default_factory=list)
    user_turn_count: int = 0
    end_reason: str | None = None
    ended_at: datetime | None = None
