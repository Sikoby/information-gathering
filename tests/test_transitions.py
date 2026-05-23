"""Unit tests for transition-kind computation."""

from __future__ import annotations

from src.harness import TransitionKind, compute_transition_kind
from src.templates import ROOT_SECTION_ID, TEMPLATES


def test_open_from_root() -> None:
    t = TEMPLATES["requirements"]
    kind = compute_transition_kind(t.sections, set(), ROOT_SECTION_ID, "rapport")
    assert kind == TransitionKind.OPEN


def test_drill_down_into_child() -> None:
    t = TEMPLATES["requirements"]
    kind = compute_transition_kind(t.sections, set(), "define", "pain_points")
    assert kind == TransitionKind.DRILL_DOWN


def test_sibling_under_same_parent() -> None:
    t = TEMPLATES["requirements"]
    kind = compute_transition_kind(
        t.sections, set(), "pain_points/q_symptom", "pain_points/q_cost"
    )
    assert kind == TransitionKind.SIBLING


def test_zoom_out_to_ancestor() -> None:
    t = TEMPLATES["requirements"]
    kind = compute_transition_kind(
        t.sections, set(), "pain_points/q_symptom", "pain_points"
    )
    assert kind == TransitionKind.ZOOM_OUT


def test_zoom_out_skips_levels() -> None:
    t = TEMPLATES["requirements"]
    kind = compute_transition_kind(
        t.sections, set(), "pain_points/q_symptom", "define"
    )
    assert kind == TransitionKind.ZOOM_OUT


def test_revisit_when_previously_visited() -> None:
    t = TEMPLATES["requirements"]
    # Not ancestor, not direct child, not sibling, but visited → revisit.
    visited = {"constraints"}
    kind = compute_transition_kind(
        t.sections, visited, "pain_points/q_symptom", "constraints"
    )
    assert kind == TransitionKind.REVISIT


def test_phase_to_sibling_phase_is_sibling() -> None:
    t = TEMPLATES["requirements"]
    kind = compute_transition_kind(t.sections, set(), "rapport", "define")
    assert kind == TransitionKind.SIBLING


def test_phase_boundary_crossing_via_enclosing_phase() -> None:
    t = TEMPLATES["requirements"]
    # Within a phase
    assert t.enclosing_phase("pain_points/q_symptom").id == "define"
    assert t.enclosing_phase("constraints").id == "define"
    # Across phases
    assert t.enclosing_phase("must_haves").id == "prioritise"
    assert t.enclosing_phase("pain_points").id == "define"
