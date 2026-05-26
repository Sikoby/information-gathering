"""Requirements definition interview template."""

from __future__ import annotations

from .schema import ROOT_SECTION_ID, Section, SectionKind, Template

REQUIREMENTS_TEMPLATE = Template(
    name="requirements",
    description=(
        "Requirements definition and prioritisation interview. The stakeholder "
        "describes a need; the consultant captures pain, constraints, and what "
        "matters most vs nice-to-have."
    ),
    sections=[
        # ---- scheduled top-level TOPICs (the "phases") ----
        Section(
            id="rapport",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Build rapport and frame the conversation",
            body=(
                "Build rapport, confirm scope and time, identify who is in the room "
                "and how decisions get made."
            ),
            target_fraction=0.10,
        ),
        Section(
            id="define",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Surface concrete pain points and constraints",
            body=(
                "Surface concrete pain points, must-haves, constraints, and "
                "dependencies. Do not solution; keep probing for specifics."
            ),
            target_fraction=0.45,
        ),
        Section(
            id="prioritise",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Separate must-haves from nice-to-haves and define success",
            body=(
                "Press on must vs nice. Identify success metrics. Test tradeoffs "
                "with concrete scenarios."
            ),
            target_fraction=0.35,
        ),
        Section(
            id="wrap",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Read back priorities and confirm next steps",
            body="Read back the top priorities, confirm follow-ups, close warmly.",
            target_fraction=0.10,
        ),
        # ---- rapport children ----
        Section(
            id="stakeholders",
            parent_id="rapport",
            kind=SectionKind.TOPIC,
            header="Who's in the room and how decisions get made",
        ),
        Section(
            id="stakeholders/q1",
            parent_id="stakeholders",
            kind=SectionKind.QUESTION,
            header="Who else needs to be consulted on this decision?",
        ),
        Section(
            id="stakeholders/q2",
            parent_id="stakeholders",
            kind=SectionKind.QUESTION,
            header="How does your team typically reach decisions like this?",
        ),
        # ---- define children ----
        Section(
            id="pain_points",
            parent_id="define",
            kind=SectionKind.TOPIC,
            header="Concrete problems the stakeholder is trying to solve",
        ),
        Section(
            id="pain_points/q1",
            parent_id="pain_points",
            kind=SectionKind.QUESTION,
            header="What hurts about how this works today?",
        ),
        Section(
            id="pain_points/q2",
            parent_id="pain_points",
            kind=SectionKind.QUESTION,
            header="When did you last notice the problem? Walk me through it.",
        ),
        Section(
            id="pain_points/q3",
            parent_id="pain_points",
            kind=SectionKind.QUESTION,
            header="What have you tried so far to address it?",
        ),
        # deeper-nested TOPIC under pain_points (the depth example for this template)
        Section(
            id="pain_points/severity",
            parent_id="pain_points",
            kind=SectionKind.TOPIC,
            header="How bad it actually is",
        ),
        Section(
            id="pain_points/severity/q1",
            parent_id="pain_points/severity",
            kind=SectionKind.QUESTION,
            header="How often does this happen?",
        ),
        Section(
            id="pain_points/severity/q2",
            parent_id="pain_points/severity",
            kind=SectionKind.QUESTION,
            header="What does each occurrence cost you in time or money?",
        ),
        Section(
            id="constraints",
            parent_id="define",
            kind=SectionKind.TOPIC,
            header="Hard limits we have to design around",
        ),
        Section(
            id="constraints/q1",
            parent_id="constraints",
            kind=SectionKind.QUESTION,
            header="What's your budget envelope for this?",
        ),
        Section(
            id="constraints/q2",
            parent_id="constraints",
            kind=SectionKind.QUESTION,
            header="Any compliance, security, or regulatory boundaries we need to respect?",
        ),
        Section(
            id="constraints/q3",
            parent_id="constraints",
            kind=SectionKind.QUESTION,
            header="Anything in the existing tech stack this has to fit into?",
        ),
        Section(
            id="dependencies",
            parent_id="define",
            kind=SectionKind.TOPIC,
            header="Upstream and downstream systems",
        ),
        Section(
            id="dependencies/q1",
            parent_id="dependencies",
            kind=SectionKind.QUESTION,
            header="What systems feed into this today?",
        ),
        Section(
            id="dependencies/q2",
            parent_id="dependencies",
            kind=SectionKind.QUESTION,
            header="Whose work depends on the outcome of this?",
        ),
        # ---- prioritise children ----
        Section(
            id="must_haves",
            parent_id="prioritise",
            kind=SectionKind.TOPIC,
            header="Capabilities the solution cannot ship without",
        ),
        Section(
            id="must_haves/q1",
            parent_id="must_haves",
            kind=SectionKind.QUESTION,
            header="If you could only ship one thing, what would it be?",
        ),
        Section(
            id="must_haves/q2",
            parent_id="must_haves",
            kind=SectionKind.QUESTION,
            header="What would make you reject a proposal outright?",
        ),
        Section(
            id="nice_to_haves",
            parent_id="prioritise",
            kind=SectionKind.TOPIC,
            header="Capabilities that add value but are negotiable",
        ),
        Section(
            id="nice_to_haves/q1",
            parent_id="nice_to_haves",
            kind=SectionKind.QUESTION,
            header="What would be nice but you could defer to a later phase?",
        ),
        Section(
            id="nice_to_haves/q2",
            parent_id="nice_to_haves",
            kind=SectionKind.QUESTION,
            header="If you had to drop something to hit the deadline, what goes first?",
        ),
        Section(
            id="success_metrics",
            parent_id="prioritise",
            kind=SectionKind.TOPIC,
            header="How you'll judge whether it worked",
        ),
        Section(
            id="success_metrics/q1",
            parent_id="success_metrics",
            kind=SectionKind.QUESTION,
            header="Six months in, what does success look like concretely?",
        ),
        Section(
            id="success_metrics/q2",
            parent_id="success_metrics",
            kind=SectionKind.QUESTION,
            header="What number on your dashboard would have to move?",
        ),
        # ---- wrap children ----
        Section(
            id="wrap/next_steps",
            parent_id="wrap",
            kind=SectionKind.TOPIC,
            header="Next steps and follow-ups",
        ),
        Section(
            id="wrap/next_steps/q1",
            parent_id="wrap/next_steps",
            kind=SectionKind.QUESTION,
            header="What's the right next step from your side?",
        ),
        Section(
            id="wrap/next_steps/q2",
            parent_id="wrap/next_steps",
            kind=SectionKind.QUESTION,
            header="Anything I should follow up on with someone else?",
        ),
    ],
)
