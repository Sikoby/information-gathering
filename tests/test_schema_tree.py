"""Unit tests for the unified Section tree."""

from __future__ import annotations

import pytest

from src.templates import (
    OTHER_SECTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    TEMPLATES,
    Template,
)
from src.templates.schema import MAX_DEPTH


def _flat_template(name: str = "t", sections: list[Section] | None = None) -> Template:
    return Template(
        name=name,
        description="test",
        sections=sections or [
            Section(id="p1", kind=SectionKind.PHASE, target_fraction=1.0, header="P1"),
        ],
    )


def test_root_is_auto_prepended() -> None:
    t = _flat_template()
    assert t.section_by_id(ROOT_SECTION_ID) is not None
    assert t.section_by_id(ROOT_SECTION_ID).kind == SectionKind.MEETING


def test_root_not_duplicated_if_present() -> None:
    t = Template(
        name="t", description="x",
        sections=[
            Section(id=ROOT_SECTION_ID, kind=SectionKind.MEETING, header="My Meeting"),
            Section(id="p", kind=SectionKind.PHASE, target_fraction=1.0, header="P"),
        ],
    )
    roots = [s for s in t.sections if s.id == ROOT_SECTION_ID]
    assert len(roots) == 1
    assert roots[0].header == "My Meeting"


def test_other_is_auto_appended() -> None:
    t = _flat_template()
    other = t.section_by_id(OTHER_SECTION_ID)
    assert other is not None
    assert other.kind == SectionKind.TOPIC
    assert other.parent_id == ROOT_SECTION_ID


def test_unparented_nodes_rewired_to_root() -> None:
    t = _flat_template()
    p1 = t.section_by_id("p1")
    assert p1.parent_id == ROOT_SECTION_ID


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(Exception) as excinfo:
        Template(
            name="t", description="x",
            sections=[
                Section(id="dup", kind=SectionKind.PHASE, target_fraction=0.5, header="A"),
                Section(id="dup", kind=SectionKind.PHASE, target_fraction=0.5, header="B"),
            ],
        )
    assert "duplicate" in str(excinfo.value).lower()


def test_unknown_parent_rejected() -> None:
    with pytest.raises(Exception) as excinfo:
        Template(
            name="t", description="x",
            sections=[
                Section(id="p", kind=SectionKind.PHASE, target_fraction=1.0, header="P"),
                Section(id="t1", kind=SectionKind.TOPIC, parent_id="ghost", header="T"),
            ],
        )
    assert "unknown parent" in str(excinfo.value).lower()


def test_nested_phase_rejected() -> None:
    with pytest.raises(Exception) as excinfo:
        Template(
            name="t", description="x",
            sections=[
                Section(id="p1", kind=SectionKind.PHASE, target_fraction=1.0, header="P1"),
                Section(id="p2", kind=SectionKind.PHASE, target_fraction=0.0001,
                        parent_id="p1", header="P2"),
            ],
        )
    assert "phase" in str(excinfo.value).lower()


def test_target_fraction_must_sum_to_one() -> None:
    with pytest.raises(Exception) as excinfo:
        Template(
            name="t", description="x",
            sections=[
                Section(id="p1", kind=SectionKind.PHASE, target_fraction=0.3, header="P1"),
                Section(id="p2", kind=SectionKind.PHASE, target_fraction=0.3, header="P2"),
            ],
        )
    assert "sum" in str(excinfo.value).lower()


def test_question_under_question_rejected() -> None:
    with pytest.raises(Exception) as excinfo:
        Template(
            name="t", description="x",
            sections=[
                Section(id="p", kind=SectionKind.PHASE, target_fraction=1.0, header="P"),
                Section(id="t", kind=SectionKind.TOPIC, parent_id="p", header="T"),
                Section(id="q1", kind=SectionKind.QUESTION, parent_id="t", header="Q1?"),
                Section(id="q2", kind=SectionKind.QUESTION, parent_id="q1", header="Q2?"),
            ],
        )
    assert "question" in str(excinfo.value).lower()


def test_depth_cap_enforced() -> None:
    # Build chain root → phase → topic → question → topic → topic → topic → topic
    sections = [
        Section(id="p", kind=SectionKind.PHASE, target_fraction=1.0, header="P"),
    ]
    parent = "p"
    # Add depth chain: phase(1) topic(2) question(3) topic(4) topic(5) topic(6) -> depth 6 > MAX_DEPTH=5
    sections.append(Section(id="t1", kind=SectionKind.TOPIC, parent_id=parent, header="T1"))
    sections.append(Section(id="q1", kind=SectionKind.QUESTION, parent_id="t1", header="Q?"))
    sections.append(Section(id="t2", kind=SectionKind.TOPIC, parent_id="q1", header="T2"))
    sections.append(Section(id="t3", kind=SectionKind.TOPIC, parent_id="t2", header="T3"))
    # depth_of t3 = 5 — at the limit
    Template(name="t", description="x", sections=list(sections))
    # depth 6 trips the limit
    sections.append(Section(id="t4", kind=SectionKind.TOPIC, parent_id="t3", header="T4"))
    with pytest.raises(Exception) as excinfo:
        Template(name="t", description="x", sections=list(sections))
    assert "max_depth" in str(excinfo.value).lower()
    assert MAX_DEPTH == 5  # sanity check the constant


def test_path_to_and_depth_of() -> None:
    t = TEMPLATES["requirements"]
    chain = t.path_to("pain_points/q_symptom")
    assert [s.id for s in chain] == [
        ROOT_SECTION_ID, "define", "pain_points", "pain_points/q_symptom"
    ]
    assert t.depth_of("pain_points/q_symptom") == 3
    assert t.depth_of(ROOT_SECTION_ID) == 0


def test_children_of_and_kind_filter() -> None:
    t = TEMPLATES["requirements"]
    questions = t.children_of_kind("pain_points", SectionKind.QUESTION)
    assert len(questions) >= 2
    assert all(q.kind == SectionKind.QUESTION for q in questions)


def test_scheduled_nodes_in_order() -> None:
    t = TEMPLATES["requirements"]
    phase_ids = [p.id for p in t.scheduled_nodes()]
    assert phase_ids == ["rapport", "define", "prioritise", "wrap"]


def test_enclosing_phase() -> None:
    t = TEMPLATES["requirements"]
    assert t.enclosing_phase("pain_points/q_symptom").id == "define"
    assert t.enclosing_phase("wrap").id == "wrap"
    assert t.enclosing_phase(ROOT_SECTION_ID) is None


def test_all_shipped_templates_validate() -> None:
    for name, tmpl in TEMPLATES.items():
        # validation runs in the Template constructor; if we got here it passed.
        assert tmpl.name == name
        assert tmpl.section_by_id(ROOT_SECTION_ID) is not None
        assert len(tmpl.scheduled_nodes()) >= 1
