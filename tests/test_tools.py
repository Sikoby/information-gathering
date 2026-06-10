"""Tests for the six function_tools in src/tools.py.

We invoke each tool via its `__wrapped__` (the raw async function under the
function_tool decorator) with a tiny fake RunContext.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from src import tools as tools_mod
from src import meeting as meeting_mod
from src.extraction import insert_finding
from src.harness import MeetingState, TransitionKind, new_state_sections
from src.templates import TEMPLATES, ROOT_SECTION_ID, SectionKind
from src.templates.schema import CLOSING_SECTION_ID, OTHER_QUESTION_ID


@dataclass
class _FakeSession:
    drained: bool = False
    closed: bool = False

    async def drain(self) -> None:
        self.drained = True

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class _FakeCtx:
    userdata: MeetingState
    session: _FakeSession = field(default_factory=_FakeSession)


@pytest.fixture(autouse=True)
def _stub_publish(monkeypatch):
    async def noop(_state: MeetingState) -> None:
        return None

    monkeypatch.setattr(meeting_mod, "publish", noop)


@pytest.fixture
def state() -> MeetingState:
    template = TEMPLATES["requirements"]
    return MeetingState(
        run_id="test",
        briefing_path="briefing.md",
        target_minutes=30,
        started_at=datetime.now(timezone.utc),
        briefing_markdown="dummy",
        template=template,
        sections=new_state_sections(template),
        current_section_id=ROOT_SECTION_ID,
    )


def _call(tool: Any, ctx: _FakeCtx, **kwargs):
    return asyncio.run(tool.__wrapped__(ctx, **kwargs))


def test_record_finding_enqueues_raw_note_without_mutating_tree(state):
    state._note_queue = asyncio.Queue()
    ctx = _FakeCtx(userdata=state)
    state.current_section_id = "pain_points/q1"
    out = _call(tools_mod.record_finding, ctx, note="Daily report builds take 4h.")
    assert out == "noted"
    assert state._note_queue.qsize() == 1
    raw = state._note_queue.get_nowait()
    assert raw.note == "Daily report builds take 4h."
    assert raw.section_id == "pain_points/q1"
    # The voice path does NOT touch the tree — the extractor does that later.
    assert not [s for s in state.sections if s.kind == SectionKind.ANSWER]


def test_record_finding_acks_even_without_queue(state):
    # Defensive: no queue wired (shouldn't happen in a real run) → ack, never raise.
    ctx = _FakeCtx(userdata=state)
    out = _call(tools_mod.record_finding, ctx, note="anything")
    assert out == "noted"


# ---- extraction.insert_finding (placement logic, exercised by the background worker) ----


def test_insert_finding_creates_answer_under_named_question(state):
    sec = insert_finding(
        state, "pain_points/q1", "Slow report", "Daily report builds take 4h."
    )
    assert sec.parent_id == "pain_points/q1"
    assert sec.kind == SectionKind.ANSWER
    assert sec.header == "Slow report"
    assert sec.body == "Daily report builds take 4h."
    assert sec.ts is not None
    answers = [
        s for s in state.sections
        if s.parent_id == "pain_points/q1" and s.kind == SectionKind.ANSWER
    ]
    assert len(answers) == 1


def test_insert_finding_falls_back_to_other_q_on_unknown(state):
    insert_finding(state, "not_a_real_id", "Stray finding", "Where did this go?")
    answers = [
        s for s in state.sections
        if s.parent_id == OTHER_QUESTION_ID and s.kind == SectionKind.ANSWER
    ]
    assert len(answers) == 1


def test_insert_finding_falls_back_to_other_q_on_non_question(state):
    # pain_points is a TOPIC, not a QUESTION
    insert_finding(state, "pain_points", "Misrouted", "Topic-targeted finding.")
    answers = [
        s for s in state.sections
        if s.parent_id == OTHER_QUESTION_ID and s.kind == SectionKind.ANSWER
    ]
    assert len(answers) == 1


def test_navigate_records_typed_transition(state):
    ctx = _FakeCtx(userdata=state)
    _call(tools_mod.navigate, ctx, to_section_id="rapport")
    assert state.current_section_id == "rapport"
    assert len(state.transitions) == 1
    t = state.transitions[0]
    assert t.from_section_id == ROOT_SECTION_ID
    assert t.to_section_id == "rapport"
    assert t.kind == TransitionKind.OPEN

    _call(tools_mod.navigate, ctx, to_section_id="stakeholders")
    assert state.current_section_id == "stakeholders"
    t2 = state.transitions[-1]
    assert t2.kind == TransitionKind.DRILL_DOWN


def test_navigate_revisit_requires_bridge(state):
    ctx = _FakeCtx(userdata=state)
    # Visit and leave so that returning is a REVISIT.
    _call(tools_mod.navigate, ctx, to_section_id="define")
    _call(tools_mod.navigate, ctx, to_section_id="pain_points")  # drill_down
    _call(tools_mod.navigate, ctx, to_section_id="constraints/q1")  # not sibling
    out_no_bridge = _call(
        tools_mod.navigate, ctx, to_section_id="pain_points"
    )  # would be REVISIT
    assert "bridge" in out_no_bridge.lower() or "REVISIT" in out_no_bridge

    out_with_bridge = _call(
        tools_mod.navigate,
        ctx,
        to_section_id="pain_points",
        bridge="we hadn't covered severity yet",
    )
    assert state.current_section_id == "pain_points"
    assert state.transitions[-1].kind == TransitionKind.REVISIT
    assert state.transitions[-1].bridge == "we hadn't covered severity yet"
    assert "come back" in out_with_bridge.lower() or "revisit" in out_with_bridge.lower()


def test_deliver_pyramid_summary_creates_one_closing(state):
    ctx = _FakeCtx(userdata=state)
    _call(
        tools_mod.deliver_pyramid_summary,
        ctx,
        top_conclusion="Phased migration is right.",
        supporting_findings=["Costs rising", "Reports stale"],
        next_actions=["Send proposal Tuesday"],
    )
    closings = [s for s in state.sections if s.id == CLOSING_SECTION_ID]
    assert len(closings) == 1
    c = closings[0]
    assert c.kind == SectionKind.TOPIC
    assert c.parent_id == ROOT_SECTION_ID
    assert c.target_fraction is None
    assert "Phased migration" in c.header
    assert "Costs rising" in (c.body or "")
    assert "Send proposal Tuesday" in (c.body or "")

    # Re-calling replaces (does not duplicate).
    _call(
        tools_mod.deliver_pyramid_summary,
        ctx,
        top_conclusion="Revised conclusion.",
        supporting_findings=[],
        next_actions=[],
    )
    closings = [s for s in state.sections if s.id == CLOSING_SECTION_ID]
    assert len(closings) == 1
    assert closings[0].header == "Revised conclusion."
