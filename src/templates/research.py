"""User research interview template."""

from __future__ import annotations

from .schema import Section, SectionKind, Template

RESEARCH_TEMPLATE = Template(
    name="research",
    description=(
        "User research interview. The consultant explores how someone actually "
        "works, what jobs they're trying to do, and tests hypotheses about their "
        "behaviour."
    ),
    sections=[
        # ── phases ──
        Section(
            id="rapport",
            kind=SectionKind.PHASE,
            target_fraction=0.10,
            header="Set them at ease; we're listening, not selling.",
            body="Confirm consent. Explain you're listening, not pitching.",
        ),
        Section(
            id="explore_behaviour",
            kind=SectionKind.PHASE,
            target_fraction=0.55,
            header="Walk through what they actually do today.",
            body=(
                "Concrete, recent examples. Avoid hypothetical 'would you'. "
                "Surface jobs, behaviours, contexts of use."
            ),
        ),
        Section(
            id="probe_motivation",
            kind=SectionKind.PHASE,
            target_fraction=0.25,
            header="Test why this way; surface surprises.",
            body=(
                "Why this way, what would they change, what surprised you. "
                "Test the briefing's hypotheses."
            ),
        ),
        Section(
            id="wrap",
            kind=SectionKind.PHASE,
            target_fraction=0.10,
            header="Thank them; confirm follow-up permission.",
        ),

        # ── explore_behaviour children ──
        Section(
            id="jobs_to_be_done",
            kind=SectionKind.TOPIC,
            parent_id="explore_behaviour",
            header="The outcomes they're chasing, in their own framing.",
        ),
        Section(
            id="jobs_to_be_done/q_outcome",
            kind=SectionKind.QUESTION,
            parent_id="jobs_to_be_done",
            header="When you do this task, what does done look like for you?",
        ),
        Section(
            id="jobs_to_be_done/q_trigger",
            kind=SectionKind.QUESTION,
            parent_id="jobs_to_be_done",
            header="What kicks off this task in a normal week?",
        ),

        Section(
            id="behaviours",
            kind=SectionKind.TOPIC,
            parent_id="explore_behaviour",
            header="What they actually do, step by step.",
        ),
        Section(
            id="behaviours/q_walkthrough",
            kind=SectionKind.QUESTION,
            parent_id="behaviours",
            header="Walk me through the last time you did this — what did you do first?",
        ),
        Section(
            id="behaviours/q_tools",
            kind=SectionKind.QUESTION,
            parent_id="behaviours",
            header="Which tools did you touch, in what order?",
        ),
        # Illustrative deeper nesting: one question owns a sub-topic.
        Section(
            id="behaviours/handoffs",
            kind=SectionKind.TOPIC,
            parent_id="behaviours",
            header="Where the work crosses people or teams.",
        ),
        Section(
            id="behaviours/handoffs/q_friction",
            kind=SectionKind.QUESTION,
            parent_id="behaviours/handoffs",
            header="Where in those handoffs does work most often stall?",
        ),

        Section(
            id="contexts_of_use",
            kind=SectionKind.TOPIC,
            parent_id="explore_behaviour",
            header="Where, when, with whom, under what conditions.",
        ),
        Section(
            id="contexts_of_use/q_where",
            kind=SectionKind.QUESTION,
            parent_id="contexts_of_use",
            header="Are you usually at a desk, on the floor, on the road?",
        ),

        # ── probe_motivation children ──
        Section(
            id="surprises",
            kind=SectionKind.TOPIC,
            parent_id="probe_motivation",
            header="Things you did not expect to hear.",
        ),
        Section(
            id="hypotheses_tested",
            kind=SectionKind.TOPIC,
            parent_id="probe_motivation",
            header="What the briefing assumed; what evidence supports or breaks it.",
        ),
        Section(
            id="hypotheses_tested/q_support",
            kind=SectionKind.QUESTION,
            parent_id="hypotheses_tested",
            header="Does what they're saying match the briefing's hypothesis here?",
        ),
        Section(
            id="quotes_to_save",
            kind=SectionKind.TOPIC,
            parent_id="probe_motivation",
            header="Verbatim phrasing worth preserving.",
        ),
    ],
)
