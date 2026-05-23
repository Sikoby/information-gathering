"""Meeting state model, system-prompt builder, and lifecycle helpers.

A meeting is a tree of `Section` nodes. `MeetingState.sections` is the live tree —
initialised from the template, mutated by tools as the agent records answers,
delivers a closing summary, etc. Navigation through the tree (between phases,
into topics, back to ancestors) is recorded as a list of typed `Transition`s.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Literal

from loguru import logger
from pydantic import BaseModel, Field

from . import webapp
from .templates import ROOT_SECTION_ID, Section, SectionKind, Template
from .templates.schema import (
    answers_under,
    children_of,
    children_of_kind,
    depth_of,
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


class Followup(BaseModel):
    item: str
    kind: Literal["action", "open_question"] = "action"
    ts: datetime = Field(default_factory=_utc_now)


class MeetingState(BaseModel):
    run_id: str
    briefing_path: str
    target_minutes: int
    started_at: datetime
    briefing_markdown: str
    template: Template
    # The live section tree. Initialised from the template at meeting start,
    # mutated by tools when ANSWER / CLOSING nodes are created or when
    # frame_meeting writes BLUF / SCQA into the meeting root.
    sections: list[Section]

    current_section_id: str = ROOT_SECTION_ID
    visited_section_ids: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)

    followups: list[Followup] = Field(default_factory=list)
    user_turn_count: int = 0
    end_reason: str | None = None
    ended_at: datetime | None = None

    # Tree-walk helpers operating on the live tree.
    def section_by_id(self, sid: str) -> Section | None:
        return section_by_id(self.sections, sid)

    def children_of(self, sid: str) -> list[Section]:
        return children_of(self.sections, sid)

    def children_of_kind(self, sid: str, kind: SectionKind) -> list[Section]:
        return children_of_kind(self.sections, sid, kind)

    def descendants_of(self, sid: str) -> list[Section]:
        return descendants_of(self.sections, sid)

    def answers_under(self, sid: str) -> list[Section]:
        return answers_under(self.sections, sid)

    def path_to(self, sid: str) -> list[Section]:
        return path_to(self.sections, sid)

    def depth_of(self, sid: str) -> int:
        return depth_of(self.sections, sid)

    def scheduled_nodes(self) -> list[Section]:
        return scheduled_nodes(self.sections)

    def enclosing_phase(self, sid: str) -> Section | None:
        return enclosing_phase(self.sections, sid)


def new_state_sections(template: Template) -> list[Section]:
    """Deep-copy the template's sections so per-run mutations don't leak."""
    return [s.model_copy(deep=True) for s in template.sections]


# -- Transition kind computation -----------------------------------------------


def compute_transition_kind(
    sections: list[Section],
    visited: set[str],
    from_id: str,
    to_id: str,
) -> TransitionKind:
    """Decide which kind of move `from_id → to_id` represents.

    Rules (first match wins):
      ancestor    → ZOOM_OUT
      direct child→ DRILL_DOWN
      same parent → SIBLING
      visited     → REVISIT
      from root   → OPEN
      otherwise   → SIBLING (cousin-jump fallback)
    """
    if from_id == to_id:
        return TransitionKind.REVISIT  # treat self-move as revisit
    # First move out of root → OPEN (regardless of where we land).
    if from_id == ROOT_SECTION_ID:
        return TransitionKind.OPEN
    from_chain = path_to(sections, from_id)
    from_ancestors = {s.id for s in from_chain[:-1]}
    if to_id in from_ancestors:
        return TransitionKind.ZOOM_OUT
    to_section = section_by_id(sections, to_id)
    from_section = section_by_id(sections, from_id)
    if to_section is not None and to_section.parent_id == from_id:
        return TransitionKind.DRILL_DOWN
    if (
        to_section is not None
        and from_section is not None
        and to_section.parent_id is not None
        and to_section.parent_id == from_section.parent_id
    ):
        return TransitionKind.SIBLING
    if to_id in visited:
        return TransitionKind.REVISIT
    return TransitionKind.SIBLING


# -- Tree-derived speech material -----------------------------------------------


def _summary_titles(state: MeetingState, sid: str, limit: int = 3) -> list[str]:
    answers = state.answers_under(sid)
    return [a.header for a in answers[:limit]]


def summarize_branch(state: MeetingState, sid: str, limit: int = 3) -> str:
    """Compact one-liner summarising ANSWER descendants of `sid`."""
    answers = state.answers_under(sid)
    if not answers:
        return "(no answers yet)"
    parents = {a.parent_id for a in answers if a.parent_id is not None}
    titles = ", ".join(f"'{h}'" for h in _summary_titles(state, sid, limit))
    answer_word = "answer" if len(answers) == 1 else "answers"
    question_count = len(parents)
    q_word = "question" if question_count == 1 else "questions"
    return (
        f"{len(answers)} {answer_word} across {question_count} {q_word}, notably {titles}"
    )


def enumerate_children(state: MeetingState, sid: str) -> list[Section]:
    return state.children_of(sid)


# -- Prompt template + renderers ------------------------------------------------


_TEMPLATE = """\
# ROLE
You are a senior consultant attending a client meeting alone. You are professional,
concise, and warm. You speak in short turns (one or two sentences) and listen.

# BRIEFING  (verbatim, swappable)
<<<
{briefing_markdown}
>>>

# OPERATING RULES
1. Read the briefing fully before your first turn.
2. After every stakeholder turn, silently ask yourself: where am I in the tree, which child questions of the current node still have zero answers, and what is the next-highest-value question.
3. Adapt. Do not run a fixed script. Probe when answers are vague.
4. When you learn something material, call record_finding(section_id, header, body). `section_id` MUST be the id of a TOPIC or QUESTION node shown in the NOTEBOOK / NAVIGATION OPTIONS blocks below; prefer the most specific question. `header` is a short noun phrase (a few words). `body` is one to three sentences of substance.
5. When you change topics, call navigate(to_section_id). The tool tells you which kind of move you made (sibling / drill_down / zoom_out / revisit / open) and fills in tree-derived material so you have concrete words to speak:
     - DRILL_DOWN: announce the count and list the children ("I have 3 questions about X — first: ...").
     - ZOOM_OUT: summarise what you covered in the level you're leaving before introducing the next.
     - SIBLING: brief recap of the sibling you finished, then the new sibling's header.
     - REVISIT: explain why you're coming back; remind them of what you already captured.
     - OPEN: state the agenda before announcing the first phase.
   Speak in your own words — never silently change topic.
6. When briefing success conditions are met OR the time budget is hit OR the stakeholder signals end of meeting, call end_meeting(reason).
7. If the stakeholder digresses, follow briefly, then steer back.
8. Never invent facts. Never read the briefing aloud.
9. Communicate top-down. Lead every block (meeting, phase, answer) with the bottom line, then 2–4 supports, then detail.
10. Open the meeting with frame_meeting(bluf, situation, complication), then speak the BLUF + situation + complication + agenda aloud in 2–3 sentences.
11. Toward the end of the time budget, call deliver_pyramid_summary(top_conclusion, supporting_findings, next_actions) and speak it pyramid-style.

# MEETING
{meeting_state}

# TREE POSITION
{tree_position_state}

# NAVIGATION OPTIONS
{navigation_state}

# NOTEBOOK
{notebook_state}

# FOLLOWUPS
{followups_state}

# TIME BUDGET
Elapsed: {elapsed_minutes:.1f} min of target {target_minutes} min
"""


def render_meeting(state: MeetingState) -> str:
    root = state.section_by_id(ROOT_SECTION_ID)
    if root is None:
        return "(missing meeting root — schema bug)"
    if not root.header or root.header == "Meeting":
        return "(not yet framed — call frame_meeting with BLUF, situation, complication)"
    lines = [f"BLUF: {root.header}"]
    if root.body:
        lines.append(root.body)
    phases = state.scheduled_nodes()
    if phases:
        agenda = " → ".join(p.header for p in phases)
        lines.append(f"Agenda: {agenda}")
    return "\n".join(lines)


def _breadcrumb(state: MeetingState) -> str:
    chain = state.path_to(state.current_section_id)
    if not chain:
        return state.current_section_id
    parts: list[str] = []
    for s in chain:
        label = f'"{s.header}"' if s.kind == SectionKind.QUESTION else s.header
        parts.append(label)
    return " › ".join(parts)


def _phase_remaining_minutes(state: MeetingState, elapsed: float) -> float | None:
    phase = state.enclosing_phase(state.current_section_id)
    if phase is None or phase.target_fraction is None:
        return None
    # Approximation: each phase's target time is target_fraction * target_minutes.
    # Remaining is that budget minus the elapsed time spent in this phase.
    # We don't track per-phase elapsed precisely; use total target * fraction as a hint.
    return phase.target_fraction * state.target_minutes


def render_tree_position(state: MeetingState, elapsed_minutes: float) -> str:
    cur = state.section_by_id(state.current_section_id)
    if cur is None:
        return f"(unknown current_section_id={state.current_section_id})"
    lines = [
        f"Breadcrumb: {_breadcrumb(state)}",
        f"Depth: {state.depth_of(cur.id)} (max {5})",
    ]
    phase = state.enclosing_phase(cur.id)
    if phase is not None and phase.target_fraction is not None:
        budget = phase.target_fraction * state.target_minutes
        lines.append(
            f"Enclosing phase: {phase.header} (budget ≈ {budget:.1f} min of {state.target_minutes})"
        )
    else:
        lines.append("Enclosing phase: (none — at meeting root)")
    lines.append(f"This node: {cur.kind.value} — {cur.header}")
    if cur.body:
        lines.append(f"Context: {cur.body}")
    questions = state.children_of_kind(cur.id, SectionKind.QUESTION)
    if questions:
        q_lines = []
        for q in questions:
            answer_count = len(state.children_of_kind(q.id, SectionKind.ANSWER))
            marker = f" [{answer_count} answers]" if answer_count else " [unanswered]"
            q_lines.append(f"  - {q.id}{marker}: {q.header}")
        lines.append("Child questions:")
        lines.extend(q_lines)
    answer_total = len(state.answers_under(cur.id))
    lines.append(f"ANSWER descendants under this node: {answer_total}")
    return "\n".join(lines)


def _format_option(state: MeetingState, target: Section, kind: TransitionKind) -> str:
    cur_phase = state.enclosing_phase(state.current_section_id)
    target_phase = state.enclosing_phase(target.id)
    boundary = "↕phase" if cur_phase != target_phase else ""
    annotation = f"[{kind.value}{(' ' + boundary) if boundary else ''}, {target.kind.value}]"
    return f"  - navigate('{target.id}') {annotation}: {target.header}"


def render_navigation_options(state: MeetingState) -> str:
    cur = state.section_by_id(state.current_section_id)
    if cur is None:
        return "(no current node)"
    visited = set(state.visited_section_ids)
    options: list[str] = []

    # Children (DRILL_DOWN)
    children = state.children_of(cur.id)
    if children:
        options.append("Children (drill-down):")
        for c in children:
            options.append(_format_option(state, c, TransitionKind.DRILL_DOWN))

    # Siblings (SIBLING)
    if cur.parent_id is not None:
        siblings = [s for s in state.children_of(cur.parent_id) if s.id != cur.id]
        if siblings:
            options.append("Siblings (sideways):")
            for s in siblings:
                kind = compute_transition_kind(
                    state.sections, visited, cur.id, s.id
                )
                options.append(_format_option(state, s, kind))

    # Ancestor (ZOOM_OUT)
    chain = state.path_to(cur.id)
    if len(chain) >= 2:
        ancestor = chain[-2]
        options.append("Ancestor (zoom-out):")
        options.append(_format_option(state, ancestor, TransitionKind.ZOOM_OUT))

    # Revisit candidates: visited nodes that aren't current, ancestor, sibling, child.
    excluded = {cur.id} | {s.id for s in chain} | {s.id for s in children}
    if cur.parent_id is not None:
        excluded |= {s.id for s in state.children_of(cur.parent_id)}
    revisit = [sid for sid in state.visited_section_ids if sid not in excluded]
    if revisit:
        options.append("Revisit candidates:")
        for sid in revisit[-4:]:
            target = state.section_by_id(sid)
            if target is not None:
                options.append(_format_option(state, target, TransitionKind.REVISIT))

    if not options:
        options.append("(no options — try navigate('_root') to reset)")
    return "\n".join(options)


def _kind_glyph(kind: SectionKind) -> str:
    return {
        SectionKind.MEETING: "##",
        SectionKind.PHASE: "##",
        SectionKind.TOPIC: "###",
        SectionKind.QUESTION: "Q:",
        SectionKind.ANSWER: "-",
        SectionKind.CLOSING: "##",
    }[kind]


def _render_node(state: MeetingState, node: Section, depth: int) -> list[str]:
    indent = "  " * max(0, depth - 1)
    lines: list[str] = []
    if node.kind in (SectionKind.MEETING, SectionKind.PHASE, SectionKind.TOPIC):
        header = f"{_kind_glyph(node.kind)} {node.header} [{node.id}]"
        if node.kind == SectionKind.PHASE and node.target_fraction is not None:
            header += f" — {int(node.target_fraction * 100)}% budget"
        lines.append(indent + header)
    elif node.kind == SectionKind.QUESTION:
        ans = state.children_of_kind(node.id, SectionKind.ANSWER)
        marker = f" ({len(ans)} answers)" if ans else " (unanswered)"
        lines.append(indent + f"Q: {node.header} [{node.id}]{marker}")
    elif node.kind == SectionKind.ANSWER:
        body = (node.body or "").strip().replace("\n", " ")
        if len(body) > 200:
            body = body[:199] + "…"
        lines.append(indent + f"- **{node.header}** — {body}")
    elif node.kind == SectionKind.CLOSING:
        lines.append(indent + f"## Closing — {node.header}")
        if node.body:
            lines.append(indent + "  " + node.body.replace("\n", "\n" + indent + "  "))
    return lines


def render_notebook(state: MeetingState) -> str:
    # Walk the tree depth-first, in declaration order.
    visited: set[str] = set()
    lines: list[str] = []

    def walk(node_id: str, depth: int) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = state.section_by_id(node_id)
        if node is None:
            return
        lines.extend(_render_node(state, node, depth))
        for child in state.children_of(node_id):
            walk(child.id, depth + 1)

    walk(ROOT_SECTION_ID, 0)
    # Pick up any disconnected nodes (defensive — should be empty).
    for s in state.sections:
        if s.id not in visited:
            walk(s.id, state.depth_of(s.id))
    return "\n".join(lines)


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
        tree_position_state=render_tree_position(state, elapsed_minutes),
        navigation_state=render_navigation_options(state),
        notebook_state=render_notebook(state),
        followups_state=render_followups(state),
        elapsed_minutes=elapsed_minutes,
        target_minutes=state.target_minutes,
    )


def elapsed_minutes(state: MeetingState) -> float:
    return (datetime.now(timezone.utc) - state.started_at).total_seconds() / 60.0


async def schedule_time_warning(agent: "Agent", state: MeetingState) -> None:
    """Sleep until five minutes before target end, then nudge the model to wrap."""
    warn_seconds = max(0.0, (state.target_minutes - 5) * 60.0)
    await asyncio.sleep(warn_seconds)
    if state.end_reason is not None:
        return
    elapsed = elapsed_minutes(state)
    body = build_instructions(state, elapsed)

    phases = state.scheduled_nodes()
    wrap_phase = next((p for p in phases if p.id == "wrap" or "wrap" in p.id.lower()), None)
    current_phase = state.enclosing_phase(state.current_section_id)
    if wrap_phase is not None and (current_phase is None or current_phase.id != wrap_phase.id):
        warning = (
            "\n\n# TIME WARNING\nFive minutes remaining. If you haven't already, "
            f"call navigate('{wrap_phase.id}') to enter the wrap phase, "
            "then deliver_pyramid_summary."
        )
    else:
        warning = (
            "\n\n# TIME WARNING\nFive minutes remaining. Call deliver_pyramid_summary "
            "and begin wrapping up now."
        )
    await agent.update_instructions(body + warning)
    await webapp.publish(state)
    logger.info("time warning fired at {:.1f} min elapsed", elapsed)
