"""LiveKit function_tool definitions backed by RunContext[MeetingState].

All node-creating tools mutate `state.sections` (the live tree). All navigation
tools update `state.current_section_id` and append to `state.transitions`.
"""

from __future__ import annotations

import asyncio
import re
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
from .templates import OTHER_SECTION_ID, ROOT_SECTION_ID, Section, SectionKind


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "a"


# -- record_finding -----------------------------------------------------------


@function_tool
async def record_finding(
    ctx: RunContext[MeetingState],
    section_id: str,
    header: str,
    body: str,
) -> str:
    """Record a material finding as a child ANSWER node.

    `section_id` MUST be the id of a TOPIC or QUESTION node shown in the
    NOTEBOOK / NAVIGATION OPTIONS blocks of your instructions. Prefer the
    most specific question. Unknown ids fall back to 'other'.

    `header` is a short headline (a few words). `body` is one to three
    sentences of substance.
    """
    state = ctx.userdata
    parent = state.section_by_id(section_id)
    if parent is None or parent.kind not in (SectionKind.TOPIC, SectionKind.QUESTION):
        logger.warning(
            "record_finding: '{}' not a TOPIC/QUESTION; routing to '{}'",
            section_id,
            OTHER_SECTION_ID,
        )
        section_id = OTHER_SECTION_ID
        parent = state.section_by_id(OTHER_SECTION_ID)
        if parent is None:
            return f"internal error: '{OTHER_SECTION_ID}' missing from template"

    existing_answers = state.children_of_kind(parent.id, SectionKind.ANSWER)

    # Single-answer parents replace their prior child.
    if not parent.repeated and existing_answers:
        for stale in existing_answers:
            state.sections.remove(stale)
        existing_answers = []

    new_id = _allocate_answer_id(state, parent.id)
    new_answer = Section(
        id=new_id,
        parent_id=parent.id,
        kind=SectionKind.ANSWER,
        header=header.strip() or "(untitled)",
        body=body.strip(),
        ts=_now(),
    )
    state.sections.append(new_answer)
    logger.info("finding recorded: [{}] {}", new_id, header)

    # Hint: which sibling questions still have zero answers?
    if parent.parent_id is not None:
        unanswered_siblings = [
            sib
            for sib in state.children_of_kind(parent.parent_id, SectionKind.QUESTION)
            if sib.id != parent.id
            and not state.children_of_kind(sib.id, SectionKind.ANSWER)
        ]
    else:
        unanswered_siblings = []
    hint = ""
    if unanswered_siblings:
        names = ", ".join(f"'{q.id}'" for q in unanswered_siblings[:3])
        hint = f" Sibling questions still unanswered: {names}."

    count = len(state.children_of_kind(parent.id, SectionKind.ANSWER))
    await webapp.publish(state)
    return f"Recorded under '{parent.header}'. {count} answer(s) there now.{hint}"


def _allocate_answer_id(state: MeetingState, parent_id: str) -> str:
    n = 1
    while True:
        candidate = f"{parent_id}/a{n}"
        if state.section_by_id(candidate) is None:
            return candidate
        n += 1


# -- navigate -----------------------------------------------------------------


_KIND_PLURAL = {
    SectionKind.QUESTION: "questions",
    SectionKind.TOPIC: "topics",
    SectionKind.ANSWER: "answers",
    SectionKind.PHASE: "phases",
    SectionKind.MEETING: "meetings",
    SectionKind.CLOSING: "closings",
}


@function_tool
async def navigate(
    ctx: RunContext[MeetingState],
    to_section_id: str,
    recap: str | None = None,
    bridge: str | None = None,
    preview: str | None = None,
) -> str:
    """Move to a section node in the tree.

    `to_section_id` is the id of any node shown in the NAVIGATION OPTIONS
    block of your instructions. The tool computes the move kind (sibling /
    drill_down / zoom_out / revisit / open) and returns concrete words for
    you to speak — phrase them yourself, never repeat verbatim.

    Optional `recap` / `bridge` / `preview` are short prose hints you supply
    when the move benefits from them (e.g. a REVISIT needs a `bridge` reason).
    """
    state = ctx.userdata
    target = state.section_by_id(to_section_id)
    if target is None:
        valid = [s.id for s in state.sections][:30]
        return (
            f"unknown to_section_id '{to_section_id}'. "
            f"Some valid ids: {', '.join(valid)}"
        )

    from_id = state.current_section_id
    visited = set(state.visited_section_ids)
    kind = compute_transition_kind(state.sections, visited, from_id, to_section_id)

    cur_phase = state.enclosing_phase(from_id)
    to_phase = state.enclosing_phase(to_section_id)
    crossed = (cur_phase.id if cur_phase else None) != (to_phase.id if to_phase else None)

    if kind == TransitionKind.REVISIT and not bridge:
        return (
            "REVISIT moves need a one-sentence `bridge` explaining why you're "
            "coming back. Re-call navigate with bridge=... ."
        )

    # Apply the move.
    state.current_section_id = to_section_id
    if to_section_id not in state.visited_section_ids:
        state.visited_section_ids.append(to_section_id)
    state.transitions.append(
        Transition(
            from_section_id=from_id,
            to_section_id=to_section_id,
            kind=kind,
            crossed_phase_boundary=crossed,
            recap=recap,
            bridge=bridge,
            preview=preview,
        )
    )
    logger.info(
        "navigate {} -> {} kind={} crossed_phase={}",
        from_id,
        to_section_id,
        kind.value,
        crossed,
    )
    await webapp.publish(state)
    return _navigate_speech_hint(state, from_id, target, kind, crossed, recap, bridge, preview)


def _navigate_speech_hint(
    state: MeetingState,
    from_id: str,
    target: Section,
    kind: TransitionKind,
    crossed: bool,
    recap: str | None,
    bridge: str | None,
    preview: str | None,
) -> str:
    if kind == TransitionKind.OPEN:
        phases = state.scheduled_nodes()
        agenda = " → ".join(p.header for p in phases) if phases else "(no phases)"
        return (
            f"OPEN. Agenda: {agenda}. "
            f"Speak: 'Today we'll cover {agenda}. Let's start with {target.header}.'"
        )

    from_section = state.section_by_id(from_id)
    from_label = from_section.header if from_section else from_id

    if kind == TransitionKind.SIBLING:
        prefix = ""
        if crossed:
            prev_phase = state.enclosing_phase(from_id)
            if prev_phase is not None:
                prefix = f"Closing out phase '{prev_phase.header}'. "
        summary = summarize_branch(state, from_id)
        recap_clause = recap or summary
        return (
            f"{prefix}SIBLING ('{from_label}' → '{target.header}'). "
            f"Recap: {recap_clause}. "
            f"Speak: short recap, then 'Next: {target.header}.'"
        )

    if kind == TransitionKind.DRILL_DOWN:
        children = enumerate_children(state, target.id)
        if children:
            kind_plural = _KIND_PLURAL.get(children[0].kind, "items")
            numbered = "\n".join(
                f"  ({i + 1}) [{c.kind.value}] {c.header}"
                for i, c in enumerate(children)
            )
            return (
                f"DRILL_DOWN into '{target.header}'. {len(children)} {kind_plural}:\n"
                f"{numbered}\n"
                f"Speak: 'Let's zoom in on {target.header}. I have {len(children)} "
                f"{kind_plural} here — first: {children[0].header}'"
            )
        # Leaf drill-down — just announce the node.
        return (
            f"DRILL_DOWN to '{target.header}'. No children yet. "
            f"Speak: 'Let's focus on {target.header}.'"
            + (f" {target.body}" if target.body else "")
        )

    if kind == TransitionKind.ZOOM_OUT:
        # The "leaving branch" is the node we were on if it was a topic/phase,
        # otherwise the nearest topic/phase ancestor we are leaving behind.
        from_chain = state.path_to(from_id)
        leaving = from_chain[-1] if from_chain else None
        for s in reversed(from_chain[:-1]):
            if s.id == target.id:
                break
            if s.kind in (SectionKind.TOPIC, SectionKind.PHASE) and from_id != s.id:
                leaving = s
                break
        leaving_label = leaving.header if leaving else from_label
        summary = summarize_branch(state, leaving.id if leaving else from_id)
        recap_clause = recap or summary
        return (
            f"ZOOM_OUT from '{leaving_label}' → '{target.header}'. "
            f"Summary of '{leaving_label}': {summary}. "
            f"Speak: 'Stepping back from {leaving_label}: {recap_clause}. "
            f"Where that leaves us is {target.header}.'"
        )

    if kind == TransitionKind.REVISIT:
        summary = summarize_branch(state, target.id)
        return (
            f"REVISIT '{target.header}'. Already captured: {summary}. "
            f"Speak: 'Let me come back to {target.header} because {bridge}. "
            f"We had captured {summary}.'"
        )

    return f"Moved to '{target.header}'."


# -- frame_meeting + deliver_pyramid_summary ----------------------------------


@function_tool
async def frame_meeting(
    ctx: RunContext[MeetingState],
    bluf: str,
    situation: str,
    complication: str,
) -> str:
    """Open the meeting by recording its top-of-the-pyramid framing.

    Writes the BLUF (bottom-line-up-front) to the meeting root's header and
    the situation + complication to its body. Call this once at the start,
    then speak the BLUF + situation + complication + agenda aloud in 2–3
    sentences.
    """
    state = ctx.userdata
    root = state.section_by_id(ROOT_SECTION_ID)
    if root is None:
        return "internal error: meeting root missing"
    root.header = bluf.strip()
    parts = []
    s = situation.strip()
    if s:
        parts.append(f"Situation: {s}")
    c = complication.strip()
    if c:
        parts.append(f"Complication: {c}")
    root.body = "\n\n".join(parts) if parts else None
    logger.info("frame_meeting: bluf set")
    await webapp.publish(state)
    phases = state.scheduled_nodes()
    agenda = " → ".join(p.header for p in phases) if phases else ""
    return (
        f"Meeting framed. Speak: BLUF + situation + complication + agenda. "
        f"Agenda is: {agenda}."
    )


@function_tool
async def deliver_pyramid_summary(
    ctx: RunContext[MeetingState],
    top_conclusion: str,
    supporting_findings: list[str],
    next_actions: list[str],
) -> str:
    """Close the meeting with a top-down pyramid summary.

    Creates a single CLOSING node under the meeting root. Then speak it
    pyramid-style: conclusion first, then the 2–4 supports, then next actions.
    """
    state = ctx.userdata
    root = state.section_by_id(ROOT_SECTION_ID)
    if root is None:
        return "internal error: meeting root missing"

    # Remove any prior closing (keep at-most-one).
    for stale in state.children_of_kind(ROOT_SECTION_ID, SectionKind.CLOSING):
        state.sections.remove(stale)

    body_parts: list[str] = []
    if supporting_findings:
        body_parts.append("Supports:\n" + "\n".join(f"- {s}" for s in supporting_findings))
    if next_actions:
        body_parts.append("Next actions:\n" + "\n".join(f"- {a}" for a in next_actions))
    closing = Section(
        id=f"{ROOT_SECTION_ID}/closing",
        parent_id=ROOT_SECTION_ID,
        kind=SectionKind.CLOSING,
        header=top_conclusion.strip(),
        body="\n\n".join(body_parts) if body_parts else "(no body)",
        repeated=False,
    )
    state.sections.append(closing)
    logger.info("closing summary recorded")
    await webapp.publish(state)
    return (
        "Closing recorded. Speak it pyramid-style: conclusion first, "
        "then the supports, then next actions."
    )


# -- note_followup + end_meeting (unchanged behaviour) ------------------------


@function_tool
async def note_followup(
    ctx: RunContext[MeetingState],
    item: str,
    kind: Literal["action", "open_question"] = "action",
) -> str:
    """Note a follow-up.

    `kind="action"` for concrete commitments either side made.
    `kind="open_question"` for questions you still need answered later.
    """
    ctx.userdata.followups.append(Followup(item=item, kind=kind))
    logger.info("followup noted [{}]: {}", kind, item)
    await webapp.publish(ctx.userdata)
    return f"noted ({kind})"


@function_tool
async def end_meeting(
    ctx: RunContext[MeetingState],
    reason: Literal["objectives_met", "time_up", "user_ended", "blocked"],
) -> str:
    """End the meeting cleanly.

    Call this when briefing success conditions are met, the time budget is hit,
    the stakeholder signals end of meeting, or you are blocked.
    """
    ctx.userdata.end_reason = reason
    ctx.userdata.ended_at = _now()

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
