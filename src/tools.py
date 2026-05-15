"""LiveKit function_tool definitions backed by RunContext[MeetingState]."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from livekit.agents import RunContext, function_tool
from loguru import logger

from .harness import Finding, Followup, MeetingState, ObjectiveStatus


@function_tool
async def record_finding(
    ctx: RunContext[MeetingState],
    topic: str,
    content: str,
) -> str:
    """Record a material learning from the conversation.

    Call when you learn something concrete from the stakeholder:
    a fact, constraint, preference, decision, number, or risk.
    Use a short topic label and one to three sentences for content.
    """
    ctx.userdata.findings.append(Finding(topic=topic, content=content))
    logger.info("finding recorded: {} | {}", topic, content)
    return "recorded"


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
    return "updated"


@function_tool
async def note_followup(
    ctx: RunContext[MeetingState],
    item: str,
) -> str:
    """Note a follow-up action item the stakeholder requested or that we promised."""
    ctx.userdata.followups.append(Followup(item=item))
    logger.info("followup noted: {}", item)
    return "noted"


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
    return f"ending: {reason}. Say a one-sentence goodbye now."
