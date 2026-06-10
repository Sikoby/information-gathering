"""Meeting state model, system-prompt builder, and lifecycle helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Literal

from loguru import logger
from pydantic import BaseModel, Field, PrivateAttr

from . import meeting
from .templates import (
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    Template,
    children_of,
    children_of_kind,
    descendants_of,
    enclosing_phase,
    path_to,
    scheduled_nodes,
    section_by_id,
)

if TYPE_CHECKING:
    from livekit.agents import Agent


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Followup(BaseModel):
    item: str
    kind: Literal["action", "open_question"] = "action"
    ts: datetime = Field(default_factory=_utc_now)


class TransitionKind(str, Enum):
    SIBLING = "sibling"
    DRILL_DOWN = "drill_down"
    ZOOM_OUT = "zoom_out"
    REVISIT = "revisit"
    OPEN = "open"


class Transition(BaseModel):
    from_section_id: str | None
    to_section_id: str
    kind: TransitionKind
    crossed_phase_boundary: bool
    recap: str | None = None
    bridge: str | None = None
    preview: str | None = None
    ts: datetime = Field(default_factory=_utc_now)


class MeetingState(BaseModel):
    run_id: str
    briefing_path: str
    target_minutes: int
    started_at: datetime
    briefing_markdown: str
    template: Template
    sections: list[Section]
    current_section_id: str = ROOT_SECTION_ID
    visited_section_ids: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    followups: list[Followup] = Field(default_factory=list)
    user_turn_count: int = 0
    end_reason: str | None = None
    ended_at: datetime | None = None

    # Runtime-only handles, excluded from model_dump / Redis snapshots.
    _note_queue: "asyncio.Queue | None" = PrivateAttr(default=None)
    _agent: "Agent | None" = PrivateAttr(default=None)
    # Id of the last conversation item present when the current section was
    # entered — the boundary for the rolling one-section history window.
    _section_start_item_id: str | None = PrivateAttr(default=None)


def new_state_sections(template: Template) -> list[Section]:
    """Deep-copy the template's sections so the state can mutate independently."""
    return [s.model_copy(deep=True) for s in template.sections]


# ---- Transition kind computation + branch helpers ----


def _ancestors(sections: list[Section], sid: str) -> list[str]:
    """Ancestor ids, root-first, EXCLUDING the node itself. Empty if unknown."""
    chain = path_to(sections, sid)
    return [s.id for s in chain[:-1]] if chain else []


def compute_transition_kind(
    sections: list[Section],
    visited: list[str],
    from_id: str | None,
    to_id: str,
) -> TransitionKind:
    """Categorize a move from `from_id` to `to_id` per the rules in the plan."""
    if from_id is not None and from_id == to_id:
        return TransitionKind.REVISIT
    if from_id is None or from_id == ROOT_SECTION_ID:
        return TransitionKind.OPEN
    if to_id in _ancestors(sections, from_id):
        return TransitionKind.ZOOM_OUT
    to_node = section_by_id(sections, to_id)
    if to_node is not None and to_node.parent_id == from_id:
        return TransitionKind.DRILL_DOWN
    from_node = section_by_id(sections, from_id)
    if (
        from_node is not None
        and to_node is not None
        and from_node.parent_id is not None
        and to_node.parent_id == from_node.parent_id
    ):
        return TransitionKind.SIBLING
    if to_id in visited:
        return TransitionKind.REVISIT
    return TransitionKind.SIBLING


def summarize_branch(state: "MeetingState", sid: str, limit: int = 3) -> str:
    """One-liner like '3 answers across 2 questions, notably "X", "Y"'."""
    answers = [
        s for s in descendants_of(state.sections, sid) if s.kind == SectionKind.ANSWER
    ]
    if not answers:
        return "no answers captured yet"
    questions_with_answers = {a.parent_id for a in answers}
    n_answers = len(answers)
    n_questions = len(questions_with_answers)
    notable = ", ".join(f"'{a.header}'" for a in answers[:limit])
    q_word = "question" if n_questions == 1 else "questions"
    a_word = "answer" if n_answers == 1 else "answers"
    return f"{n_answers} {a_word} across {n_questions} {q_word}, notably {notable}"


def enumerate_children(state: "MeetingState", sid: str) -> list[Section]:
    """Direct non-ANSWER children. Used for drill-down enumeration."""
    return [c for c in children_of(state.sections, sid) if c.kind != SectionKind.ANSWER]


# ---- Prompt template + block rendering ----

_TEMPLATE = """\
# ROLE
You are a senior consultant attending a client meeting alone. You are professional,
concise, and warm. You speak in short turns (one or two sentences) and listen.
Always speak English, regardless of the language the briefing below is written in.

# BRIEFING  (verbatim, swappable)
<<<
{briefing_markdown}
>>>

# OPERATING RULES
1. Read the briefing fully before your first turn.
2. After every stakeholder turn, silently ask yourself: where am I in the tree, what
   question is in front of me, what is unanswered nearby, and what would top-down
   communication say next.
3. Adapt. Do not run a fixed script. Probe when answers are vague.
4. When you learn something material, call record_finding(note) with a single short
   natural-language sentence — just say what you learned. You do NOT pick a question id
   and you do NOT split header/body; a background pass files it under the right question
   and trims it to a terse note. It returns instantly, so keep talking — never wait for it.
5. When you change topics, call navigate(to_section_id). Then, out loud, BRIDGE the move:
   first (a) summarise the ground you just covered, then (b) outline what's coming next.
   The tool returns tree-derived material (a branch recap, child count + first child, the
   destination) — use it to make the bridge concrete. Shape the bridge by the move kind:
     - DRILL_DOWN: name the topic, say how many sub-questions it holds, outline the first
       ("There are 3 questions under X — let's start with the first…").
     - ZOOM_OUT: summarise the branch you're leaving, then where that leaves us and what's
       next ("Stepping back from X: we covered … — next we'll look at …").
     - SIBLING: recap the sibling you just finished, then introduce the next one.
     - REVISIT: say why you're coming back and recap what was captured before, then the step.
   Never silently change topic — always bridge by recapping the ground covered and
   previewing what's next, in your own words, using the material the tool returns.
6. When briefing success conditions are met OR the time budget is hit OR the
   stakeholder signals end of meeting, call end_meeting(reason).
7. If the stakeholder digresses, follow briefly, then steer back.
8. Never invent facts. Never read the briefing aloud. Never read or paraphrase
   `speaker notes:` aloud — those are private delivery cues from the template
   author for you only; use them to shape your tone, pacing, and approach.
9. Communicate top-down. Lead every block with the bottom line, then 2–4 supports,
   then detail.
10. You start already in the first phase — the introduction. Open by introducing
    yourself as an AI voice agent running this meeting, ask the participant whether
    they're happy to proceed (read their reply and continue — don't wait for a
    formal yes), preview the agenda, then begin the introduction. Do NOT navigate
    to open; you're already in the first phase.
11. Toward the end of the time budget, call deliver_pyramid_summary and speak it
    pyramid-style.

# MEETING
{meeting_state}

# TREE POSITION
{tree_position}

# NAVIGATION OPTIONS
{navigation_options}

# NOTEBOOK
{notebook_state}

# FOLLOWUPS
{followups_state}

# TIME BUDGET
Elapsed: {elapsed_minutes:.1f} min of target {target_minutes} min
"""


def _truncate(text: str, limit: int = 160) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def render_meeting(state: MeetingState) -> str:
    agenda = " → ".join(s.header for s in scheduled_nodes(state.sections))
    parts = [f"Meeting: {state.template.name}"]
    if state.template.description:
        parts.append(state.template.description)
    if agenda:
        parts.append(f"Agenda: {agenda}")
    return "\n\n".join(parts)


_KIND_GLYPH = {
    SectionKind.MEETING: "M",
    SectionKind.TOPIC: "T",
    SectionKind.QUESTION: "Q",
    SectionKind.ANSWER: "A",
}


def _question_summary(state: MeetingState, q: Section) -> str:
    n_answers = len(
        [c for c in children_of(state.sections, q.id) if c.kind == SectionKind.ANSWER]
    )
    status = f"{n_answers} answer(s)" if n_answers else "unanswered"
    return f'{q.id}: "{q.header}" — {status}'


def render_tree_position(state: MeetingState, elapsed_minutes: float) -> str:
    cur_id = state.current_section_id
    cur = section_by_id(state.sections, cur_id)
    if cur is None:
        return f"current_section_id={cur_id!r} not in tree"
    chain = path_to(state.sections, cur_id)
    breadcrumb = " › ".join(
        (f'{_KIND_GLYPH[s.kind]}:{s.id}' if s.id == ROOT_SECTION_ID else f'"{s.header}"')
        for s in chain
    )
    depth = len(chain) - 1
    lines = [f"Position: {breadcrumb}", f"Depth: {depth}"]

    phase = enclosing_phase(state.sections, cur_id)
    if phase is not None and phase.target_fraction is not None:
        phase_budget = phase.target_fraction * state.target_minutes
        lines.append(
            f"Enclosing phase: {phase.id} ({phase.header}) — "
            f"phase budget ≈ {phase_budget:.1f} min, "
            f"elapsed across meeting {elapsed_minutes:.1f} of {state.target_minutes}"
        )
    else:
        lines.append("Enclosing phase: (none — at root or unscheduled branch)")

    questions = children_of_kind(state.sections, cur_id, SectionKind.QUESTION)
    if questions:
        lines.append(f"Child questions ({len(questions)}):")
        for q in questions:
            lines.append(f"  - {_question_summary(state, q)}")
    n_answers_below = len(
        [s for s in descendants_of(state.sections, cur_id) if s.kind == SectionKind.ANSWER]
    )
    lines.append(f"Answers in this branch: {n_answers_below}")
    return "\n".join(lines)


def _navigation_annotation(
    state: MeetingState, target_id: str
) -> str:
    kind = compute_transition_kind(
        state.sections, state.visited_section_ids, state.current_section_id, target_id
    )
    cur_phase = enclosing_phase(state.sections, state.current_section_id)
    to_phase = enclosing_phase(state.sections, target_id)
    crossed = (cur_phase.id if cur_phase else None) != (to_phase.id if to_phase else None)
    target = section_by_id(state.sections, target_id)
    target_kind = target.kind.value if target else "?"
    marker = " ↕phase" if crossed else ""
    return f"[{kind.value}{marker}, {target_kind}]"


def render_navigation_options(state: MeetingState) -> str:
    cur = section_by_id(state.sections, state.current_section_id)
    if cur is None:
        return "(current section unknown — cannot enumerate options)"

    lines: list[str] = []

    children = enumerate_children(state, cur.id)
    if children:
        lines.append("Children (drill_down):")
        for c in children:
            lines.append(f"  - {c.id} {_navigation_annotation(state, c.id)}: {c.header}")

    if cur.parent_id is not None:
        siblings = [
            s
            for s in children_of(state.sections, cur.parent_id)
            if s.id != cur.id and s.kind != SectionKind.ANSWER
        ]
        if siblings:
            lines.append("Siblings:")
            for s in siblings:
                lines.append(
                    f"  - {s.id} {_navigation_annotation(state, s.id)}: {s.header}"
                )

    if cur.parent_id is not None and cur.parent_id != ROOT_SECTION_ID:
        parent = section_by_id(state.sections, cur.parent_id)
        if parent is not None:
            lines.append("Ancestor (zoom_out):")
            lines.append(
                f"  - {parent.id} {_navigation_annotation(state, parent.id)}: {parent.header}"
            )

    revisits = [
        sid
        for sid in reversed(state.visited_section_ids)
        if sid != cur.id
    ]
    # de-dup while preserving order
    seen: set[str] = set()
    revisits = [sid for sid in revisits if not (sid in seen or seen.add(sid))][:3]
    if revisits:
        lines.append("Recent visited (revisit):")
        for sid in revisits:
            node = section_by_id(state.sections, sid)
            if node is None:
                continue
            lines.append(
                f"  - {sid} {_navigation_annotation(state, sid)}: {node.header}"
            )

    if not lines:
        return "(no navigation targets — current section is isolated)"
    return "\n".join(lines)


def render_notebook(state: MeetingState) -> str:
    """Recursive walk: scheduled TOPICs as ##, nested TOPICs as ###+, questions and answers."""
    root = section_by_id(state.sections, ROOT_SECTION_ID)
    if root is None:
        return "(no root)"
    lines: list[str] = []

    def walk(node: Section, depth: int) -> None:
        if node.kind == SectionKind.TOPIC:
            prefix = "#" * (depth + 1)
            badge = ""
            if node.target_fraction is not None:
                badge = f" [{node.target_fraction:.0%}]"
            lines.append(f"{prefix} {node.header} ({node.id}){badge}")
            if node.body:
                lines.append(_truncate(node.body, 220))
            if node.private_notes:
                lines.append(f"(speaker notes: {_truncate(node.private_notes, 220)})")
        elif node.kind == SectionKind.QUESTION:
            answers = [
                c for c in children_of(state.sections, node.id) if c.kind == SectionKind.ANSWER
            ]
            status = f"{len(answers)} answer(s)" if answers else "unanswered"
            lines.append(f'Q ({node.id}): "{node.header}" — {status}')
            if node.private_notes:
                lines.append(f"  (speaker notes: {_truncate(node.private_notes, 220)})")
            for a in answers:
                lines.append(f"  - **{a.header}** — {_truncate(a.body or '', 220)}")
            return  # questions own only answers; don't recurse further
        for child in children_of(state.sections, node.id):
            if child.kind == SectionKind.ANSWER:
                continue  # rendered inline by the QUESTION block above
            walk(child, depth + 1)

    # Top-level walk: scheduled phases first, then non-scheduled top-level TOPICs.
    for s in scheduled_nodes(state.sections):
        walk(s, depth=1)
    non_scheduled = [
        s
        for s in children_of(state.sections, ROOT_SECTION_ID)
        if s.kind == SectionKind.TOPIC and s.target_fraction is None
    ]
    for s in non_scheduled:
        walk(s, depth=1)
    return "\n".join(lines) if lines else "(notebook empty)"


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
        meeting_state=render_meeting(state),
        tree_position=render_tree_position(state, elapsed_minutes),
        navigation_options=render_navigation_options(state),
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
    cur_phase = enclosing_phase(state.sections, state.current_section_id)
    wrap_phase = next(
        (s for s in scheduled_nodes(state.sections) if "wrap" in s.id),
        None,
    )
    if wrap_phase is not None and (cur_phase is None or cur_phase.id != wrap_phase.id):
        warning = (
            f"\n\n# TIME WARNING\nFive minutes remaining. If you haven't already, "
            f"call navigate('{wrap_phase.id}') and then deliver_pyramid_summary. "
            "Begin wrapping up now."
        )
    else:
        warning = (
            "\n\n# TIME WARNING\nFive minutes remaining. Call deliver_pyramid_summary "
            "and begin wrapping up now."
        )
    await agent.update_instructions(body + warning)
    await meeting.publish(state)
    logger.info("time warning fired at {:.1f} min elapsed", elapsed)
