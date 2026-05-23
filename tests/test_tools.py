"""Smoke tests for the function_tools — exercising their state mutations directly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.harness import MeetingState, TransitionKind, new_state_sections
from src.templates import ROOT_SECTION_ID, SectionKind, TEMPLATES


class _FakeSession:
    async def drain(self) -> None: ...
    async def aclose(self) -> None: ...


class _FakeCtx:
    def __init__(self, state: MeetingState) -> None:
        self.userdata = state
        self.session = _FakeSession()


@pytest.fixture
def state() -> MeetingState:
    template = TEMPLATES["requirements"]
    return MeetingState(
        run_id="t",
        briefing_path="x.md",
        target_minutes=10,
        started_at=datetime.now(timezone.utc),
        briefing_markdown="brief",
        template=template,
        sections=new_state_sections(template),
    )


async def _run(tool: Any, ctx: _FakeCtx, **kwargs: Any) -> str:
    # @function_tool wraps the callable; call .real_fn to bypass LiveKit's plumbing
    fn = getattr(tool, "real_fn", None) or getattr(tool, "func", None) or tool
    return await fn(ctx, **kwargs)


@pytest.mark.asyncio
async def test_frame_meeting_writes_bluf_and_scqa(state: MeetingState, monkeypatch) -> None:
    from src import tools, webapp

    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(webapp, "publish", _noop)
    ctx = _FakeCtx(state)
    msg = await _run(
        tools.frame_meeting,
        ctx,
        bluf="Replace the manual CSV pipeline with a daily-refreshed warehouse.",
        situation="Sales, finance, and product pull different numbers from CSVs.",
        complication="A SOC2 audit lands in Q1 and PII residency must be solved.",
    )
    root = state.section_by_id(ROOT_SECTION_ID)
    assert "manual CSV" in root.header
    assert "Situation" in (root.body or "")
    assert "Complication" in (root.body or "")
    assert "Agenda" in msg


@pytest.mark.asyncio
async def test_record_finding_creates_answer_node(state: MeetingState, monkeypatch) -> None:
    from src import tools, webapp

    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(webapp, "publish", _noop)
    ctx = _FakeCtx(state)
    msg = await _run(
        tools.record_finding,
        ctx,
        section_id="pain_points/q_symptom",
        header="Mobile lag",
        body="Sales reports 60% mobile demand; lag pushes them to competitors.",
    )
    answers = state.children_of_kind("pain_points/q_symptom", SectionKind.ANSWER)
    assert len(answers) == 1
    assert answers[0].header == "Mobile lag"
    assert answers[0].body.startswith("Sales reports")
    assert answers[0].ts is not None
    assert "Recorded" in msg


@pytest.mark.asyncio
async def test_record_finding_unknown_routes_to_other(state: MeetingState, monkeypatch) -> None:
    from src import tools, webapp

    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(webapp, "publish", _noop)
    ctx = _FakeCtx(state)
    await _run(
        tools.record_finding,
        ctx,
        section_id="does_not_exist",
        header="Unrelated thing",
        body="something the agent thought worth noting",
    )
    other_answers = state.children_of_kind("other", SectionKind.ANSWER)
    assert len(other_answers) == 1


@pytest.mark.asyncio
async def test_navigate_records_typed_transition(state: MeetingState, monkeypatch) -> None:
    from src import tools, webapp

    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(webapp, "publish", _noop)
    ctx = _FakeCtx(state)
    await _run(tools.navigate, ctx, to_section_id="rapport")
    assert state.current_section_id == "rapport"
    assert state.transitions[-1].kind == TransitionKind.OPEN
    assert state.transitions[-1].crossed_phase_boundary is True

    # Drill down
    await _run(tools.navigate, ctx, to_section_id="stakeholders")
    assert state.transitions[-1].kind == TransitionKind.DRILL_DOWN
    assert state.transitions[-1].crossed_phase_boundary is False


@pytest.mark.asyncio
async def test_navigate_revisit_requires_bridge(state: MeetingState, monkeypatch) -> None:
    from src import tools, webapp

    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(webapp, "publish", _noop)
    ctx = _FakeCtx(state)
    # Hop down to a question in `define`, then to a question in `constraints`,
    # then back to the first question — a cousin-jump to a visited node = REVISIT.
    await _run(tools.navigate, ctx, to_section_id="define")
    await _run(tools.navigate, ctx, to_section_id="pain_points")
    await _run(tools.navigate, ctx, to_section_id="pain_points/q_symptom")
    await _run(tools.navigate, ctx, to_section_id="constraints")
    await _run(tools.navigate, ctx, to_section_id="constraints/q_source")
    # Now jump back to pain_points/q_symptom — cousin, visited → REVISIT, needs bridge.
    msg = await _run(tools.navigate, ctx, to_section_id="pain_points/q_symptom")
    assert "bridge" in msg.lower()
    # With a bridge, it goes through.
    msg2 = await _run(
        tools.navigate,
        ctx,
        to_section_id="pain_points/q_symptom",
        bridge="want to dig deeper on symptom severity",
    )
    assert state.current_section_id == "pain_points/q_symptom"
    assert "REVISIT" in msg2


@pytest.mark.asyncio
async def test_deliver_pyramid_summary_creates_closing(state: MeetingState, monkeypatch) -> None:
    from src import tools, webapp

    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(webapp, "publish", _noop)
    ctx = _FakeCtx(state)
    await _run(
        tools.deliver_pyramid_summary,
        ctx,
        top_conclusion="Daily warehouse, EU residency, SOC2-ready.",
        supporting_findings=["Mobile lag", "GDPR pin", "Finance/product disagreement"],
        next_actions=["Send Stripe schema", "Confirm SOC2 timeline"],
    )
    closings = state.children_of_kind(ROOT_SECTION_ID, SectionKind.CLOSING)
    assert len(closings) == 1
    assert "warehouse" in closings[0].header.lower()
    assert "Supports" in (closings[0].body or "")
    assert "Next actions" in (closings[0].body or "")
