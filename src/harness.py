"""Meeting state model, system-prompt builder, and lifecycle helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from loguru import logger
from pydantic import BaseModel, Field

from . import webapp
from .templates import Template

if TYPE_CHECKING:
    from livekit.agents import Agent


class Objective(BaseModel):
    id: str
    objective: str
    success_criteria: str


class ObjectiveStatus(BaseModel):
    status: Literal["open", "partial", "covered"] = "open"
    note: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotebookEntry(BaseModel):
    title: str
    content: str
    objective_ids: list[str] = Field(default_factory=list)
    ts: datetime = Field(default_factory=_utc_now)


class Followup(BaseModel):
    item: str
    kind: Literal["action", "open_question"] = "action"
    ts: datetime = Field(default_factory=_utc_now)


class PhaseTransition(BaseModel):
    phase_id: str
    note: str = ""
    ts: datetime = Field(default_factory=_utc_now)


class MeetingState(BaseModel):
    run_id: str
    target_minutes: int
    started_at: datetime
    briefing_markdown: str
    objectives: list[Objective]
    tracker: dict[str, ObjectiveStatus]
    template: Template
    notebook: dict[str, list[NotebookEntry]] = Field(default_factory=dict)
    current_phase: str
    phase_history: list[PhaseTransition] = Field(default_factory=list)
    followups: list[Followup] = Field(default_factory=list)
    user_turn_count: int = 0
    end_reason: str | None = None
    ended_at: datetime | None = None


_TEMPLATE = """\
# ROLE
You are a senior consultant attending a client meeting alone. You are professional,
concise, and warm. You speak in short turns (one or two sentences) and listen.
Always speak English, regardless of the language the briefing below is written in.

# MEETING BRIEFING  (verbatim, swappable)
<<<
{briefing_markdown}
>>>

# OPERATING RULES
1. Read the briefing fully before your first turn.
2. After every stakeholder turn, silently ask yourself which briefing objectives are covered, partial, or open, what phase you are in, and what is the next-highest-value question.
3. Adapt. Do not run a fixed script. Probe when answers are vague.
4. When you learn something material, call record_finding(section, title, content, objective_ids?). `section` must be one of the NOTEBOOK section ids below; prefer declared sections over "other".
5. When you have met the goal of the current phase, or the time profile says it is time, call enter_phase(phase_id, note) to advance. Real conversations loop; going back to an earlier phase is allowed.
6. When briefing success conditions are met OR the time budget is hit OR the stakeholder signals end of meeting, call end_meeting(reason).
7. If the stakeholder digresses, follow briefly, then steer back.
8. Never invent facts. Never read the briefing aloud.

# PHASE
{phase_state}

# OBJECTIVE TRACKER
{tracker_state}

# NOTEBOOK
{notebook_state}

# FOLLOWUPS
{followups_state}

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


def render_phase(state: MeetingState) -> str:
    template = state.template
    current = template.get_phase(state.current_phase)
    if current is None:
        return f"Current phase id '{state.current_phase}' is not in template; recover by calling enter_phase with a valid id."

    lines: list[str] = [
        f"Current: {current.id} ({current.label}) — {current.goal}",
    ]
    if current.sections_in_focus:
        lines.append(f"Sections to fill this phase: {', '.join(current.sections_in_focus)}")
    else:
        lines.append("Sections to fill this phase: (none specifically — focus on phase goal)")

    cumulative = 0.0
    idx = None
    for i, p in enumerate(template.phases):
        if p.id == current.id:
            idx = i
            break
        cumulative += p.target_fraction

    if idx is not None and idx + 1 < len(template.phases):
        next_phase = template.phases[idx + 1]
        next_start_minute = (cumulative + current.target_fraction) * state.target_minutes
        lines.append(
            f"Next phase: {next_phase.id} ({next_phase.label}) — typically begins ~min "
            f"{next_start_minute:.0f} of {state.target_minutes}"
        )
    else:
        lines.append("Next phase: (this is the final phase)")

    valid_ids = ", ".join(template.phase_ids())
    lines.append(f"Available phase ids: {valid_ids}")
    return "\n".join(lines)


def _truncate(text: str, limit: int = 160) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def render_notebook(state: MeetingState) -> str:
    template = state.template
    parts: list[str] = []
    for section in template.sections:
        entries = state.notebook.get(section.id, [])
        header = f"## {section.label} [{section.id}] ({len(entries)})"
        parts.append(header)
        if not entries:
            parts.append("(empty)")
            continue
        for e in entries:
            line = f"- {e.title}: {_truncate(e.content)}"
            if e.objective_ids:
                line += f"  // objectives: {', '.join(e.objective_ids)}"
            parts.append(line)
    return "\n".join(parts)


def render_followups(state: MeetingState) -> str:
    buckets: dict[str, list[str]] = {"action": [], "open_question": []}
    for f in state.followups:
        buckets[f.kind].append(f"- {f.item}")
    parts: list[str] = []
    parts.append(f"## ACTIONS ({len(buckets['action'])})")
    parts.append("\n".join(buckets["action"]) if buckets["action"] else "(none)")
    parts.append(f"## OPEN QUESTIONS ({len(buckets['open_question'])})")
    parts.append("\n".join(buckets["open_question"]) if buckets["open_question"] else "(none)")
    return "\n".join(parts)


def build_instructions(state: MeetingState, elapsed_minutes: float) -> str:
    return _TEMPLATE.format(
        briefing_markdown=state.briefing_markdown,
        phase_state=render_phase(state),
        tracker_state=render_tracker(state.tracker, state.objectives),
        notebook_state=render_notebook(state),
        followups_state=render_followups(state),
        elapsed_minutes=elapsed_minutes,
        target_minutes=state.target_minutes,
    )


def elapsed_minutes(state: MeetingState) -> float:
    return (datetime.now(timezone.utc) - state.started_at).total_seconds() / 60.0


async def schedule_time_warning(agent: "Agent", state: MeetingState) -> None:
    """Sleep until five minutes before the target end, then nudge the model to wrap up."""
    warn_seconds = max(0.0, (state.target_minutes - 5) * 60.0)
    await asyncio.sleep(warn_seconds)
    if state.end_reason is not None:
        return
    elapsed = elapsed_minutes(state)
    body = build_instructions(state, elapsed)
    has_wrap_phase = any(p.id == "wrap" for p in state.template.phases)
    if has_wrap_phase and state.current_phase != "wrap":
        warning = (
            "\n\n# TIME WARNING\nFive minutes remaining. If you haven't already, "
            "call enter_phase('wrap', note) and begin wrapping up now."
        )
    else:
        warning = "\n\n# TIME WARNING\nFive minutes remaining. Begin wrapping up now."
    await agent.update_instructions(body + warning)
    await webapp.publish(state)
    logger.info("time warning fired at {:.1f} min elapsed", elapsed)
