"""Meeting state model and system-prompt builder."""

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


_TEMPLATE = """\
# ROLE
You are a senior consultant attending a client meeting alone. You are professional,
concise, and warm. You speak in short turns (one or two sentences) and listen.

# MEETING BRIEFING  (verbatim, swappable)
<<<
{briefing_markdown}
>>>

# OPERATING RULES
1. Read the briefing fully before your first turn.
2. After every stakeholder turn, silently ask yourself which briefing objectives are covered, partial, or open, and what is the next-highest-value question.
3. Adapt. Do not run a fixed script. Probe when answers are vague.
4. When you learn something material, call record_finding(topic, content).
5. When briefing success conditions are met OR the time budget is hit OR the stakeholder signals end of meeting, call end_meeting(reason).
6. If the stakeholder digresses, follow briefly, then steer back.
7. Never invent facts. Never read the briefing aloud.

# OBJECTIVE TRACKER
{tracker_state}

# TIME BUDGET
Elapsed: {elapsed_minutes:.1f} min of target {target_minutes} min
"""


def render_tracker(tracker: dict[str, ObjectiveStatus], objectives: list[Objective]) -> str:
    by_id = {o.id: o for o in objectives}
    bucket: dict[str, list[str]] = {"covered": [], "partial": [], "open": []}
    for oid, st in tracker.items():
        obj = by_id.get(oid)
        if obj is None:
            continue
        line = f"- {oid}: {obj.objective}"
        if st.note:
            line += f"  // {st.note}"
        bucket[st.status].append(line)

    sections: list[str] = []
    for status in ("covered", "partial", "open"):
        items = bucket[status]
        sections.append(f"## {status.upper()}")
        sections.append("\n".join(items) if items else "(none)")
    return "\n".join(sections)


def build_instructions(state: MeetingState, elapsed_minutes: float) -> str:
    return _TEMPLATE.format(
        briefing_markdown=state.briefing_markdown,
        tracker_state=render_tracker(state.tracker, state.objectives),
        elapsed_minutes=elapsed_minutes,
        target_minutes=state.target_minutes,
    )
