"""LiveKit function_tool definitions backed by RunContext[MeetingState]."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from livekit.agents import RunContext, function_tool
from loguru import logger

from . import webapp
from .harness import (
    Followup,
    MeetingState,
    Transition,
    TransitionKind,
    compute_transition_kind,
    enumerate_children,
    summarize_branch,
)
from .templates import (
    CLOSING_SECTION_ID,
    OTHER_QUESTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    children_of,
    enclosing_phase,
    scheduled_nodes,
    section_by_id,
)


def _agenda(state: MeetingState) -> str:
    return " → ".join(s.header for s in scheduled_nodes(state.sections))


# ---- record_finding ----


@function_tool
async def record_finding(
    ctx: RunContext[MeetingState],
    section_id: str,
    header: str,
    body: str,
) -> str:
    """Record a material learning under a QUESTION in the notebook tree.

    `section_id` MUST be the id of a QUESTION node (these are the lines starting
    with `Q (...)` in the NOTEBOOK block of your instructions). If unknown or
    not a question, the finding is routed to the fallback question
    ('other/q'). `header` is a short noun phrase (a few words). `body` is one
    to three sentences of substance.
    """
    state = ctx.userdata
    parent = section_by_id(state.sections, section_id)
    if parent is None or parent.kind != SectionKind.QUESTION:
        logger.warning(
            "record_finding: section_id {!r} is not a QUESTION; routing to {!r}",
            section_id,
            OTHER_QUESTION_ID,
        )
        section_id = OTHER_QUESTION_ID
        parent = section_by_id(state.sections, section_id)
    assert parent is not None  # auto-appended by the Template validator

    # Pick the next free integer suffix for the answer id.
    existing_answers = [
        s for s in children_of(state.sections, parent.id) if s.kind == SectionKind.ANSWER
    ]
    n = len(existing_answers) + 1
    while any(s.id == f"{parent.id}/a{n}" for s in existing_answers):
        n += 1
    answer_id = f"{parent.id}/a{n}"

    state.sections.append(
        Section(
            id=answer_id,
            parent_id=parent.id,
            kind=SectionKind.ANSWER,
            header=header,
            body=body,
            ts=datetime.now(timezone.utc),
        )
    )
    logger.info(
        "finding recorded under {}: {} | {}", parent.id, header, body
    )

    n_after = len(existing_answers) + 1
    # Sibling QUESTIONs still at zero answers (helpful nudge).
    if parent.parent_id is not None:
        sibling_qs_unanswered: list[str] = []
        for sibling in children_of(state.sections, parent.parent_id):
            if sibling.id == parent.id or sibling.kind != SectionKind.QUESTION:
                continue
            if not any(
                c.kind == SectionKind.ANSWER for c in children_of(state.sections, sibling.id)
            ):
                sibling_qs_unanswered.append(sibling.id)
    else:
        sibling_qs_unanswered = []

    hint = ""
    if sibling_qs_unanswered:
        hint = (
            f" Sibling questions still at zero answers: "
            f"{', '.join(sibling_qs_unanswered)}."
        )
    await webapp.publish(state)
    return (
        f"Recorded under '{parent.header}'. {n_after} answer(s) there now.{hint}"
    )


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
    kind (open/drill_down/zoom_out/sibling/revisit) and returns the words you
    should speak to make the move feel intentional and top-down.

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

    await webapp.publish(state)
    return f"[{kind.value}] {speech}"


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


# ---- frame_meeting ----


@function_tool
async def frame_meeting(
    ctx: RunContext[MeetingState],
    bluf: str,
    situation: str,
    complication: str,
) -> str:
    """Frame the meeting top-down before starting (Minto BLUF + SCQA).

    `bluf` is the one-sentence bottom line — what you want this meeting to land.
    `situation` is the shared background (one or two sentences). `complication`
    is what changed or what's at stake that makes the meeting needed
    (one sentence). Idempotent — calling again replaces the framing.
    """
    state = ctx.userdata
    root = section_by_id(state.sections, ROOT_SECTION_ID)
    if root is None:
        return "no root section — cannot frame"
    root.header = bluf
    root.body = f"Situation: {situation}\n\nComplication: {complication}"
    logger.info("meeting framed: {}", bluf)
    agenda = _agenda(state) or "(no scheduled phases)"
    await webapp.publish(state)
    return (
        f"Meeting framed. BLUF set. Agenda is: {agenda}. "
        "Now speak the BLUF, situation, complication, and agenda aloud in 2–3 sentences, "
        "then call navigate() to the first phase."
    )


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
    await webapp.publish(state)
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
    await webapp.publish(ctx.userdata)
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
    await webapp.publish(ctx.userdata)
    return f"ending: {reason}. Say a one-sentence goodbye now."
