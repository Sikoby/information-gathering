"""LiveKit function_tool definitions backed by RunContext[MeetingState]."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ChatContext
from loguru import logger

from . import meeting
from .extraction import RawNote
from .harness import (
    Followup,
    MeetingState,
    Transition,
    TransitionKind,
    build_instructions,
    compute_transition_kind,
    elapsed_minutes,
    enumerate_children,
    summarize_branch,
)
from .templates import (
    CLOSING_SECTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    enclosing_phase,
    scheduled_nodes,
    section_by_id,
)


def _agenda(state: MeetingState) -> str:
    return " → ".join(s.header for s in scheduled_nodes(state.sections))


# ---- record_finding ----


@function_tool
async def record_finding(ctx: RunContext[MeetingState], note: str) -> str:
    """Capture something you just learned, in one short natural-language sentence.

    Just say what you learned in plain words — you do NOT pick a question id and you
    do NOT split header from body. A background pass files the note under the right
    question and trims it to a terse entry. Returns immediately, so keep talking;
    never wait for the finding to appear.
    """
    state = ctx.userdata
    queue = state._note_queue
    if queue is None:
        # Extractor not wired (should not happen in a normal run). Don't block the
        # voice loop or lose the note silently — log it and ack.
        logger.error("record_finding: no note queue on state; note dropped: {!r}", note)
        return "noted"
    queue.put_nowait(
        RawNote(
            note=note,
            section_id=state.current_section_id,
            user_turn=state.user_turn_count,
        )
    )
    logger.info("note queued under {}: {}", state.current_section_id, note)
    return "noted"


# ---- navigate ----


@function_tool
async def navigate(
    ctx: RunContext[MeetingState],
    to_section_id: str,
    recap: str | None = None,
    bridge: str | None = None,
    preview: str | None = None,
) -> str:
    """Change which section the conversation is in.

    Pass the id of any TOPIC or QUESTION in the tree. The tool computes the move
    kind (open/drill_down/zoom_out/sibling/revisit) and returns bridge material —
    a recap of the ground just covered plus a pointer to what's next. Use it to
    bridge the move out loud (summarise what's done, then outline what's next);
    it's raw material to speak in your own words, not a script to read verbatim.

    `recap` is a one-line summary you'd offer when leaving a branch (used on
    SIBLING and ZOOM_OUT). `bridge` is a one-line reason you're returning to
    something (required on REVISIT). `preview` is an optional teaser for what's
    next.
    """
    state = ctx.userdata
    target = section_by_id(state.sections, to_section_id)
    if target is None:
        return f"unknown section_id: {to_section_id!r}"
    if target.kind == SectionKind.ANSWER:
        return (
            f"refusing to navigate into ANSWER {to_section_id!r}; "
            "answers are leaves — pick the question or topic above it"
        )

    from_id = state.current_section_id
    kind = compute_transition_kind(
        state.sections, state.visited_section_ids, from_id, target.id
    )

    if kind == TransitionKind.REVISIT and not bridge:
        return (
            f"REVISIT to {target.id!r} requires a `bridge` argument explaining "
            "why you're coming back; pass one and retry"
        )

    from_phase = enclosing_phase(state.sections, from_id) if from_id else None
    to_phase = enclosing_phase(state.sections, target.id)
    crossed = (
        (from_phase.id if from_phase else None)
        != (to_phase.id if to_phase else None)
    )

    state.current_section_id = target.id
    if target.id not in state.visited_section_ids:
        state.visited_section_ids.append(target.id)
    state.transitions.append(
        Transition(
            from_section_id=from_id,
            to_section_id=target.id,
            kind=kind,
            crossed_phase_boundary=crossed,
            recap=recap,
            bridge=bridge,
            preview=preview,
        )
    )
    logger.info(
        "navigate {} -> {} ({}{})",
        from_id,
        target.id,
        kind.value,
        ", ↕phase" if crossed else "",
    )

    # Compose kind-specific speech material.
    speech = _speech_for_transition(
        state, kind, from_id, target, crossed, recap, bridge
    )

    await meeting.publish(state)
    await _refresh_on_transition(ctx, state)

    return (
        "Bridge out loud — recap what's done, then outline what's next:\n"
        f"{speech}\n"
        f"[move: {kind.value}]"
    )


async def _refresh_on_transition(
    ctx: RunContext[MeetingState], state: MeetingState
) -> None:
    """D1 + D2: a transition is the one moment the live context needs to change.

    D1 — rebuild instructions now (TREE POSITION / NAVIGATION OPTIONS only move here).
    D2 — window conversation history to the section that just ended: keep everything
    from where it began, drop older sections (their findings already live in the
    NOTEBOOK snapshot). The just-ended section's turns stay, so a note spoken right
    before this move is never orphaned by the prune. Refresh before prune so the
    rebuilt snapshot is authoritative for the content we're dropping.
    """
    agent = state._agent
    if agent is None:
        return

    await agent.update_instructions(build_instructions(state, elapsed_minutes(state)))

    hist = ctx.session.history
    items = hist.items
    if not items:
        return
    marker = state._section_start_item_id
    if marker is not None:
        idx = hist.index_by_id(marker)
        if idx is not None and idx > 0:
            await agent.update_chat_ctx(ChatContext(items=items[idx:]))
            logger.info(
                "history windowed: dropped {} item(s) before the last section", idx
            )
    state._section_start_item_id = items[-1].id


def _speech_for_transition(
    state: MeetingState,
    kind: TransitionKind,
    from_id: str | None,
    to: "Section",
    crossed_phase: bool,
    recap: str | None,
    bridge: str | None,
) -> str:
    if kind == TransitionKind.OPEN:
        agenda = _agenda(state)
        return (
            f"Today we'll cover {agenda}. Let's start with {to.header}."
            if agenda
            else f"Let's start with {to.header}."
        )

    from_node = section_by_id(state.sections, from_id) if from_id else None

    if kind == TransitionKind.SIBLING:
        recap_str = recap or summarize_branch(state, from_id or to.id)
        prefix = ""
        if crossed_phase and from_node is not None:
            prev_phase = enclosing_phase(state.sections, from_node.id)
            if prev_phase is not None:
                prefix = f"Closing out phase '{prev_phase.header}'. "
        return f"{prefix}{recap_str}. Next: {to.header}."

    if kind == TransitionKind.DRILL_DOWN:
        children = enumerate_children(state, to.id)
        if not children:
            return f"Let's open {to.header}."
        n = len(children)
        plural = "question" if n == 1 else "questions"
        if children[0].kind == SectionKind.QUESTION:
            return (
                f"I have {n} {plural} on {to.header} — first: "
                f"{children[0].header}"
            )
        return f"Let's break {to.header} into {n} parts — first: {children[0].header}"

    if kind == TransitionKind.ZOOM_OUT:
        branch_summary = recap or summarize_branch(state, from_id or to.id)
        from_label = from_node.header if from_node is not None else (from_id or "previous")
        return (
            f"Stepping back from {from_label}: {branch_summary}. "
            f"Where that leaves us is {to.header}."
        )

    if kind == TransitionKind.REVISIT:
        prior_capture = summarize_branch(state, to.id)
        return (
            f"Let me come back to {to.header} because {bridge}. "
            f"We had captured {prior_capture}."
        )

    return f"Now on {to.header}."


# ---- deliver_pyramid_summary ----


@function_tool
async def deliver_pyramid_summary(
    ctx: RunContext[MeetingState],
    top_conclusion: str,
    supporting_findings: list[str],
    next_actions: list[str],
) -> str:
    """Land the meeting top-down: top conclusion first, then supports, then actions.

    `top_conclusion` is the single sentence the stakeholder should remember.
    `supporting_findings` is 2–4 lines that back it up (most important first).
    `next_actions` is the concrete things either side will do after this meeting.

    Creates (or replaces) the closing TOPIC under root with id `_root/closing`.
    """
    state = ctx.userdata
    body_lines: list[str] = ["Supports:"]
    if supporting_findings:
        body_lines.extend(f"- {s}" for s in supporting_findings)
    else:
        body_lines.append("- (none)")
    body_lines.append("")
    body_lines.append("Next actions:")
    if next_actions:
        body_lines.extend(f"- {a}" for a in next_actions)
    else:
        body_lines.append("- (none)")
    body = "\n".join(body_lines)

    # Replace any existing closing.
    state.sections = [s for s in state.sections if s.id != CLOSING_SECTION_ID]
    state.sections.append(
        Section(
            id=CLOSING_SECTION_ID,
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header=top_conclusion,
            body=body,
            ts=datetime.now(timezone.utc),
        )
    )
    logger.info("pyramid summary delivered: {}", top_conclusion)
    await meeting.publish(state)
    return (
        f"Closing prepared: '{top_conclusion}'. "
        "Now speak it pyramid-style: top conclusion first, then 2–4 supports, then actions."
    )


# ---- note_followup (unchanged behavior, kept) ----


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
    await meeting.publish(ctx.userdata)
    return f"noted ({kind})"


# ---- end_meeting (unchanged) ----


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
    await meeting.publish(ctx.userdata)
    return f"ending: {reason}. Say a one-sentence goodbye now."
