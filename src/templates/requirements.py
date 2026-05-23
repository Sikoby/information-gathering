"""Requirements definition and prioritisation template."""

from __future__ import annotations

from .schema import Section, SectionKind, Template

REQUIREMENTS_TEMPLATE = Template(
    name="requirements",
    description=(
        "Requirements definition and prioritisation interview. The stakeholder "
        "describes a need; the consultant captures pain, constraints, and what "
        "matters most vs nice-to-have."
    ),
    sections=[
        # ── phases ──
        Section(
            id="rapport",
            kind=SectionKind.PHASE,
            target_fraction=0.10,
            header="Set the room before digging in.",
            body="Confirm scope, time, and who is in the room. Then get to substance.",
        ),
        Section(
            id="define",
            kind=SectionKind.PHASE,
            target_fraction=0.45,
            header="Pin down concrete pain.",
            body=(
                "Surface concrete pain points, must-haves, constraints, and "
                "dependencies. Do not solution; keep probing for specifics."
            ),
        ),
        Section(
            id="prioritise",
            kind=SectionKind.PHASE,
            target_fraction=0.35,
            header="Separate must from nice.",
            body=(
                "Press on must vs nice. Identify success metrics. Test tradeoffs "
                "with concrete scenarios."
            ),
        ),
        Section(
            id="wrap",
            kind=SectionKind.PHASE,
            target_fraction=0.10,
            header="Pyramid-summarise and confirm next actions.",
            body="Read back the top priorities, confirm follow-ups, close warmly.",
        ),

        # ── rapport children ──
        Section(
            id="stakeholders",
            kind=SectionKind.TOPIC,
            parent_id="rapport",
            header="Who is in the room, who decides.",
            repeated=False,
        ),
        Section(
            id="stakeholders/q_decider",
            kind=SectionKind.QUESTION,
            parent_id="stakeholders",
            header="Who is the final decision maker on this?",
        ),
        Section(
            id="stakeholders/q_affected",
            kind=SectionKind.QUESTION,
            parent_id="stakeholders",
            header="Who else is materially affected by this decision?",
        ),

        # ── define children ──
        Section(
            id="pain_points",
            kind=SectionKind.TOPIC,
            parent_id="define",
            header="What hurts today, and how much.",
            body="Concrete problems the stakeholder is trying to solve.",
        ),
        Section(
            id="pain_points/q_symptom",
            kind=SectionKind.QUESTION,
            parent_id="pain_points",
            header="What symptom do you see today?",
        ),
        Section(
            id="pain_points/q_cost",
            kind=SectionKind.QUESTION,
            parent_id="pain_points",
            header="What's the cost of not fixing it?",
        ),
        Section(
            id="pain_points/q_workaround",
            kind=SectionKind.QUESTION,
            parent_id="pain_points",
            header="What workarounds exist today?",
        ),
        # One illustrative deeper nesting: severity gets its own sub-topic.
        Section(
            id="pain_points/severity",
            kind=SectionKind.TOPIC,
            parent_id="pain_points",
            header="How severe is the worst pain point.",
        ),
        Section(
            id="pain_points/severity/q_frequency",
            kind=SectionKind.QUESTION,
            parent_id="pain_points/severity",
            header="How often does the worst symptom recur?",
        ),
        Section(
            id="pain_points/severity/q_blast_radius",
            kind=SectionKind.QUESTION,
            parent_id="pain_points/severity",
            header="How many people or processes does each incident hit?",
        ),

        Section(
            id="constraints",
            kind=SectionKind.TOPIC,
            parent_id="define",
            header="Hard limits that box solutions in.",
            body="Budget caps, compliance, tech-stack lock-in, deadlines.",
        ),
        Section(
            id="constraints/q_source",
            kind=SectionKind.QUESTION,
            parent_id="constraints",
            header="Where does each constraint come from?",
        ),
        Section(
            id="constraints/q_firmness",
            kind=SectionKind.QUESTION,
            parent_id="constraints",
            header="Hard, soft, or aspirational?",
        ),

        Section(
            id="dependencies",
            kind=SectionKind.TOPIC,
            parent_id="define",
            header="Upstream and downstream systems this depends on.",
        ),
        Section(
            id="dependencies/q_systems",
            kind=SectionKind.QUESTION,
            parent_id="dependencies",
            header="Which systems must this integrate with on day one?",
        ),
        Section(
            id="dependencies/q_owners",
            kind=SectionKind.QUESTION,
            parent_id="dependencies",
            header="Who owns each of those systems on your side?",
        ),

        # ── prioritise children ──
        Section(
            id="must_haves",
            kind=SectionKind.TOPIC,
            parent_id="prioritise",
            header="Non-negotiables.",
            body="Capabilities the solution cannot ship without.",
        ),
        Section(
            id="must_haves/q_evidence",
            kind=SectionKind.QUESTION,
            parent_id="must_haves",
            header="Why is each item a must rather than a strong-want?",
        ),

        Section(
            id="nice_to_haves",
            kind=SectionKind.TOPIC,
            parent_id="prioritise",
            header="Strong-wants we'd drop if forced to.",
            body="Capabilities that add value but aren't blockers.",
        ),

        Section(
            id="success_metrics",
            kind=SectionKind.TOPIC,
            parent_id="prioritise",
            header="How we'll know it worked.",
        ),
        Section(
            id="success_metrics/q_today",
            kind=SectionKind.QUESTION,
            parent_id="success_metrics",
            header="What's the baseline today for that metric?",
        ),
        Section(
            id="success_metrics/q_target",
            kind=SectionKind.QUESTION,
            parent_id="success_metrics",
            header="What number, by when, would count as success?",
        ),
    ],
)
