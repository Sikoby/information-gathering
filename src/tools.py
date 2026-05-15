"""LiveKit function_tool definitions backed by RunContext[MeetingState]."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from livekit.agents import RunContext, function_tool
from loguru import logger

from . import webapp
from .harness import Followup, MeetingState, NotebookEntry, ObjectiveStatus, PhaseTransition


@function_tool
async def record_finding(
    ctx: RunContext[MeetingState],
    section: str,
    title: str,
    content: str,
    objective_ids: list[str] | None = None,
) -> str:
    """Record a material learning into the structured notebook.

    `section` MUST be one of the section ids shown in the NOTEBOOK block of your
    instructions (or "other" as a last resort). `title` is a short noun phrase
    (a few words). `content` is one to three sentences of substance.
    `objective_ids` is the list of OBJECTIVE TRACKER ids this finding helps cover
    (empty if none directly).
    """
    state = ctx.userdata
    valid_section_ids = state.template.section_ids()
    if section not in valid_section_ids:
        logger.warning(
            "record_finding: unknown section '{}' (valid: {}); routing to 'other'",
            section,
            valid_section_ids,
        )
        section = "other"

    state.notebook.setdefault(section, [])
    state.notebook[section].append(
        NotebookEntry(
            title=title,
            content=content,
            objective_ids=list(objective_ids or []),
        )
    )
    logger.info("finding recorded: [{}] {} | {}", section, title, content)
    await webapp.publish(state)
    return f"recorded in {section}"


@function_tool
async def update_objective_status(
    ctx: RunContext[MeetingState],
    objective_id: str,
    status: Literal["open", "partial", "covered"],
    note: str,
) -> str:
    """Update the tracker for a briefing objective.

    Use the objective IDs shown in the OBJECTIVE TRACKER block of
    your instructions. Status is one of open, partial, covered.
    Note is a brief reason (one sentence).
    """
    if objective_id not in ctx.userdata.tracker:
        return f"unknown objective_id: {objective_id}"
    ctx.userdata.tracker[objective_id] = ObjectiveStatus(status=status, note=note)
    logger.info("objective {} -> {} ({})", objective_id, status, note)
    await webapp.publish(ctx.userdata)
    return "updated"


@function_tool
async def note_followup(
    ctx: RunContext[MeetingState],
    item: str,
    kind: Literal["action", "open_question"] = "action",
) -> str:
    """Note a follow-up.

    `kind="action"` for concrete commitments either side made (we'll send docs,
    they'll introduce us to X). `kind="open_question"` for questions you still
    need answered after this meeting (do they have budget? what is the SLA?).
    """
    ctx.userdata.followups.append(Followup(item=item, kind=kind))
    logger.info("followup noted [{}]: {}", kind, item)
    await webapp.publish(ctx.userdata)
    return f"noted ({kind})"


@function_tool
async def enter_phase(
    ctx: RunContext[MeetingState],
    phase_id: str,
    note: str,
) -> str:
    """Advance to a new conversation phase.

    `phase_id` MUST be one of the phase ids listed in the PHASE block of your
    instructions. `note` is a one-sentence reason (e.g. "covered top pains,
    moving to prioritisation"). Going back to an earlier phase is permitted if
    the conversation loops; it will be logged.
    """
    state = ctx.userdata
    if state.template.get_phase(phase_id) is None:
        return f"unknown phase_id: {phase_id} (valid: {', '.join(state.template.phase_ids())})"
    previous = state.current_phase
    state.current_phase = phase_id
    state.phase_history.append(PhaseTransition(phase_id=phase_id, note=note))
    if previous != phase_id:
        logger.info("phase {} -> {} ({})", previous, phase_id, note)
    else:
        logger.info("phase re-entered {} ({})", phase_id, note)
    await webapp.publish(state)
    return f"entered: {phase_id}"


@function_tool
async def end_meeting(
    ctx: RunContext[MeetingState],
    reason: Literal["objectives_met", "time_up", "user_ended", "blocked"],
) -> str:
    """End the meeting cleanly.

    Call this when briefing success conditions are met, the time budget is hit,
    the stakeholder signals end of meeting, or you are blocked. After the tool
    returns, say a one-sentence goodbye; the session will then close.
    """
    ctx.userdata.end_reason = reason
    ctx.userdata.ended_at = datetime.now(timezone.utc)

    session = ctx.session

    async def _close_after_goodbye() -> None:
        try:
            await asyncio.sleep(6.0)
            await session.drain()
        finally:
            await session.aclose()

    asyncio.create_task(_close_after_goodbye())
    logger.info("end_meeting called: {}", reason)
    await webapp.publish(ctx.userdata)
    return f"ending: {reason}. Say a one-sentence goodbye now."
