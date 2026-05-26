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
from src import webapp as webapp_mod
from src.harness import MeetingState, TransitionKind, new_state_sections
from src.templates import TEMPLATES, ROOT_SECTION_ID, SectionKind, section_by_id
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

    monkeypatch.setattr(webapp_mod, "publish", noop)


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


def test_frame_meeting_writes_header_and_body(state):
    ctx = _FakeCtx(userdata=state)
    out = _call(
        tools_mod.frame_meeting,
        ctx,
        bluf="We need a phased data-warehouse migration.",
        situation="Reports are slow.",
        complication="Costs are climbing.",
    )
    root = section_by_id(state.sections, ROOT_SECTION_ID)
    assert root is not None
    assert root.header == "We need a phased data-warehouse migration."
    assert "Situation: Reports are slow." in (root.body or "")
    assert "Complication: Costs are climbing." in (root.body or "")
    assert "Agenda" in out


def test_record_finding_creates_answer_under_named_question(state):
    ctx = _FakeCtx(userdata=state)
    out = _call(
        tools_mod.record_finding,
        ctx,
        section_id="pain_points/q1",
        header="Slow report",
        body="Daily report builds take 4h.",
    )
    answers = [
        s for s in state.sections
        if s.parent_id == "pain_points/q1" and s.kind == SectionKind.ANSWER
    ]
    assert len(answers) == 1
    assert answers[0].header == "Slow report"
    assert answers[0].body == "Daily report builds take 4h."
    assert answers[0].ts is not None
    assert "pain_points" not in out or "answer" in out.lower()


def test_record_finding_falls_back_to_other_q_on_unknown(state):
    ctx = _FakeCtx(userdata=state)
    _call(
        tools_mod.record_finding,
        ctx,
        section_id="not_a_real_id",
        header="Stray finding",
        body="Where did this go?",
    )
    answers = [
        s for s in state.sections
        if s.parent_id == OTHER_QUESTION_ID and s.kind == SectionKind.ANSWER
    ]
    assert len(answers) == 1


def test_record_finding_falls_back_to_other_q_on_non_question(state):
    ctx = _FakeCtx(userdata=state)
    # pain_points is a TOPIC, not a QUESTION
    _call(
        tools_mod.record_finding,
        ctx,
        section_id="pain_points",
        header="Misrouted",
        body="Topic-targeted finding.",
    )
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
