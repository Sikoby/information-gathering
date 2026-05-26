"""Tests for compute_transition_kind."""

from __future__ import annotations

from src.harness import TransitionKind, compute_transition_kind
from src.templates import TEMPLATES, ROOT_SECTION_ID


def _sections():
    # Use the shipped requirements template — it has the shape we need.
    return [s.model_copy(deep=True) for s in TEMPLATES["requirements"].sections]


def test_open_from_root_regardless_of_target():
    sections = _sections()
    # any move out of root is OPEN
    kind = compute_transition_kind(sections, [], ROOT_SECTION_ID, "define")
    assert kind == TransitionKind.OPEN
    kind = compute_transition_kind(sections, [], ROOT_SECTION_ID, "pain_points")
    assert kind == TransitionKind.OPEN


def test_sibling_phase_to_phase():
    sections = _sections()
    kind = compute_transition_kind(sections, ["rapport"], "rapport", "define")
    assert kind == TransitionKind.SIBLING


def test_drill_down_topic_to_child_question():
    sections = _sections()
    kind = compute_transition_kind(sections, [], "pain_points", "pain_points/q1")
    assert kind == TransitionKind.DRILL_DOWN


def test_drill_down_phase_to_child_topic():
    sections = _sections()
    kind = compute_transition_kind(sections, [], "define", "pain_points")
    assert kind == TransitionKind.DRILL_DOWN


def test_zoom_out_to_parent():
    sections = _sections()
    kind = compute_transition_kind(
        sections, [], "pain_points/q1", "pain_points"
    )
    assert kind == TransitionKind.ZOOM_OUT


def test_zoom_out_multi_level():
    sections = _sections()
    # pain_points/severity/q1 → define (skips two levels)
    kind = compute_transition_kind(
        sections, [], "pain_points/severity/q1", "define"
    )
    assert kind == TransitionKind.ZOOM_OUT


def test_revisit_to_already_visited_cousin():
    sections = _sections()
    visited = ["pain_points/q1", "constraints/q1"]
    # constraints/q1 was already visited and we're not in its parent's tree;
    # constraints/q1's sibling/parent relationship to pain_points/q1's parent
    # ('pain_points') is "cousin" (different parent, but in visited).
    kind = compute_transition_kind(
        sections, visited, "pain_points/q2", "constraints/q1"
    )
    # Not a sibling (different parents pain_points vs constraints), not an
    # ancestor, not a drill-down → falls through to "in visited" → REVISIT.
    assert kind == TransitionKind.REVISIT


def test_self_move_is_revisit():
    sections = _sections()
    kind = compute_transition_kind(sections, ["define"], "define", "define")
    assert kind == TransitionKind.REVISIT
