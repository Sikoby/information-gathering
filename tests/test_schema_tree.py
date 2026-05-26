"""Tests for the Section tree schema validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.templates import TEMPLATES
from src.templates.schema import (
    OTHER_QUESTION_ID,
    OTHER_SECTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    Template,
    depth_of,
    enclosing_phase,
    is_scheduled,
    path_to,
    scheduled_nodes,
)


def _section(**kwargs) -> Section:
    return Section(**kwargs)


def _make_template(sections: list[Section]) -> Template:
    return Template(name="t", description="d", sections=sections)


# ---- auto-normalization ----


def test_root_is_auto_prepended_if_missing():
    t = _make_template([
        _section(id="phase1", parent_id=None, kind=SectionKind.TOPIC,
                 header="P1", target_fraction=1.0),
    ])
    ids = [s.id for s in t.sections]
    assert ROOT_SECTION_ID in ids
    # The non-root section was rewired to root.
    assert any(s.id == "phase1" and s.parent_id == ROOT_SECTION_ID for s in t.sections)


def test_other_topic_and_question_auto_appended():
    t = _make_template([
        _section(id="phase1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                 header="P1", target_fraction=1.0),
    ])
    ids = {s.id for s in t.sections}
    assert OTHER_SECTION_ID in ids
    assert OTHER_QUESTION_ID in ids


# ---- validators ----


def test_duplicate_ids_rejected():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="a", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="A", target_fraction=1.0),
            _section(id="a", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="A2"),
        ])


def test_unresolved_parent_id_rejected():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="phase1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=1.0),
            _section(id="orphan", parent_id="ghost", kind=SectionKind.TOPIC,
                     header="O"),
        ])


def test_meeting_uniqueness():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id=ROOT_SECTION_ID, parent_id=None, kind=SectionKind.MEETING,
                     header="Meeting"),
            _section(id="m2", parent_id=None, kind=SectionKind.MEETING,
                     header="Second meeting"),
        ])


def test_scheduled_topic_must_be_top_level():
    # A scheduled TOPIC cannot live below another scheduled TOPIC.
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=0.5),
            _section(id="p2", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P2", target_fraction=0.5),
            _section(id="p1/sub", parent_id="p1", kind=SectionKind.TOPIC,
                     header="Nested scheduled", target_fraction=0.3),
        ])


def test_target_fraction_sum_must_be_one():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=0.3),
            _section(id="p2", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P2", target_fraction=0.3),
        ])


def test_target_fraction_only_on_topic():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=1.0),
            _section(id="p1/q", parent_id="p1", kind=SectionKind.QUESTION,
                     header="Q?", target_fraction=0.5),
        ])


def test_question_under_question_rejected():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=1.0),
            _section(id="p1/q1", parent_id="p1", kind=SectionKind.QUESTION,
                     header="Q?"),
            _section(id="p1/q1/q2", parent_id="p1/q1", kind=SectionKind.QUESTION,
                     header="Nested Q?"),
        ])


def test_topic_under_question_rejected():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=1.0),
            _section(id="p1/q1", parent_id="p1", kind=SectionKind.QUESTION,
                     header="Q?"),
            _section(id="p1/q1/t", parent_id="p1/q1", kind=SectionKind.TOPIC,
                     header="No topic under question"),
        ])


def test_answer_under_topic_rejected():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=1.0),
            _section(id="p1/a", parent_id="p1", kind=SectionKind.ANSWER,
                     header="Bad", body="x"),
        ])


def test_answer_body_must_be_nonempty():
    with pytest.raises(ValidationError):
        _make_template([
            _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                     header="P1", target_fraction=1.0),
            _section(id="p1/q", parent_id="p1", kind=SectionKind.QUESTION,
                     header="Q?"),
            _section(id="p1/q/a", parent_id="p1/q", kind=SectionKind.ANSWER,
                     header="A", body=""),
        ])


def test_depth_cap_enforced():
    # Build a deep chain that exceeds MAX_DEPTH=5.
    sections = [
        _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                 header="P1", target_fraction=1.0),
    ]
    chain = ["p1", "t1", "t2", "t3", "t4", "t5", "t6"]
    for i in range(1, len(chain)):
        sections.append(
            _section(
                id=chain[i], parent_id=chain[i - 1], kind=SectionKind.TOPIC,
                header=chain[i],
            )
        )
    with pytest.raises(ValidationError):
        _make_template(sections)


# ---- helpers ----


def test_path_to_and_depth():
    t = _make_template([
        _section(id="p1", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                 header="P1", target_fraction=1.0),
        _section(id="p1/inner", parent_id="p1", kind=SectionKind.TOPIC,
                 header="Inner"),
        _section(id="p1/inner/q", parent_id="p1/inner", kind=SectionKind.QUESTION,
                 header="Q?"),
    ])
    chain = path_to(t.sections, "p1/inner/q")
    assert [s.id for s in chain] == [ROOT_SECTION_ID, "p1", "p1/inner", "p1/inner/q"]
    assert depth_of(t.sections, "p1/inner/q") == 3


def test_scheduled_nodes_and_enclosing_phase():
    t = _make_template([
        _section(id="rapport", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                 header="R", target_fraction=0.5),
        _section(id="define", parent_id=ROOT_SECTION_ID, kind=SectionKind.TOPIC,
                 header="D", target_fraction=0.5),
        _section(id="define/inner", parent_id="define", kind=SectionKind.TOPIC,
                 header="Inner"),
        _section(id="define/inner/q", parent_id="define/inner",
                 kind=SectionKind.QUESTION, header="Q?"),
    ])
    sched = scheduled_nodes(t.sections)
    assert [s.id for s in sched] == ["rapport", "define"]
    assert all(is_scheduled(s) for s in sched)
    phase = enclosing_phase(t.sections, "define/inner/q")
    assert phase is not None and phase.id == "define"


# ---- shipped templates parse cleanly ----


@pytest.mark.parametrize("name", ["requirements", "research", "eval", "generic"])
def test_shipped_template_parses(name: str):
    t = TEMPLATES[name]
    assert isinstance(t, Template)
    # Round-trip through JSON to confirm serialisability.
    dumped = t.model_dump_json()
    Template.model_validate_json(dumped)
    # Should always include the auto-appended fallback question.
    ids = {s.id for s in t.sections}
    assert OTHER_QUESTION_ID in ids
