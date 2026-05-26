"""Vendor evaluation template."""

from __future__ import annotations

from .schema import ROOT_SECTION_ID, Section, SectionKind, Template

EVAL_TEMPLATE = Template(
    name="eval",
    description=(
        "Vendor evaluation conversation. The consultant probes whether a vendor's "
        "offering meets specific requirements, where the gaps are, and on what "
        "commercial terms."
    ),
    sections=[
        # ---- scheduled top-level TOPICs ----
        Section(
            id="rapport",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Introduce and set the agenda",
            body="Introduce, confirm agenda, set time expectations.",
            target_fraction=0.10,
        ),
        Section(
            id="capability_check",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Press on capabilities and surface real gaps",
            body=(
                "Walk through requirements; press for evidence, not just yes/no. "
                "Surface gaps and integration concerns."
            ),
            target_fraction=0.50,
        ),
        Section(
            id="commercial_terms",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Probe pricing, timeline, references, and what tips the decision",
            body=(
                "Probe pricing model, timeline, references, what tips the decision. "
                "Avoid committing on our side."
            ),
            target_fraction=0.30,
        ),
        Section(
            id="wrap",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Summarise gaps and confirm follow-ups",
            body="Summarise gaps, confirm follow-ups, close.",
            target_fraction=0.10,
        ),
        # ---- rapport children ----
        Section(
            id="introduction",
            parent_id="rapport",
            kind=SectionKind.TOPIC,
            header="Who's on the call and what we're evaluating",
        ),
        Section(
            id="introduction/q1",
            parent_id="introduction",
            kind=SectionKind.QUESTION,
            header="Who do we have on your side today and what's their role?",
        ),
        Section(
            id="introduction/q2",
            parent_id="introduction",
            kind=SectionKind.QUESTION,
            header="What outcome would you like from this conversation?",
        ),
        # ---- capability_check children ----
        Section(
            id="requirements_coverage",
            parent_id="capability_check",
            kind=SectionKind.TOPIC,
            header="What the vendor claims to meet — with evidence",
        ),
        Section(
            id="requirements_coverage/q1",
            parent_id="requirements_coverage",
            kind=SectionKind.QUESTION,
            header="Walk me through how your product handles our top requirements.",
        ),
        Section(
            id="requirements_coverage/q2",
            parent_id="requirements_coverage",
            kind=SectionKind.QUESTION,
            header="Where do you have working customers doing exactly this today?",
        ),
        Section(
            id="gaps",
            parent_id="capability_check",
            kind=SectionKind.TOPIC,
            header="What you don't (yet) handle",
        ),
        Section(
            id="gaps/q1",
            parent_id="gaps",
            kind=SectionKind.QUESTION,
            header="Which of our requirements are partial today?",
        ),
        Section(
            id="gaps/q2",
            parent_id="gaps",
            kind=SectionKind.QUESTION,
            header="What's actually unsupported, and is it on the roadmap?",
        ),
        # deeper-nested TOPIC under gaps (the depth example for this template)
        Section(
            id="gaps/workarounds",
            parent_id="gaps",
            kind=SectionKind.TOPIC,
            header="Workarounds and configuration to close gaps",
        ),
        Section(
            id="gaps/workarounds/q1",
            parent_id="gaps/workarounds",
            kind=SectionKind.QUESTION,
            header="If we hit a gap, what's your usual workaround?",
        ),
        Section(
            id="gaps/workarounds/q2",
            parent_id="gaps/workarounds",
            kind=SectionKind.QUESTION,
            header="Where does that workaround break down at scale?",
        ),
        Section(
            id="integration_concerns",
            parent_id="capability_check",
            kind=SectionKind.TOPIC,
            header="Integration — what falls on us vs. you",
        ),
        Section(
            id="integration_concerns/q1",
            parent_id="integration_concerns",
            kind=SectionKind.QUESTION,
            header="How does your product plug into the systems we already run?",
        ),
        Section(
            id="integration_concerns/q2",
            parent_id="integration_concerns",
            kind=SectionKind.QUESTION,
            header="What integration work would my team be responsible for?",
        ),
        # ---- commercial_terms children ----
        Section(
            id="pricing",
            parent_id="commercial_terms",
            kind=SectionKind.TOPIC,
            header="Pricing model and what drives cost up or down",
        ),
        Section(
            id="pricing/q1",
            parent_id="pricing",
            kind=SectionKind.QUESTION,
            header="Walk me through your pricing model in concrete numbers.",
        ),
        Section(
            id="pricing/q2",
            parent_id="pricing",
            kind=SectionKind.QUESTION,
            header="What pushes the price up the most for customers our size?",
        ),
        Section(
            id="timeline",
            parent_id="commercial_terms",
            kind=SectionKind.TOPIC,
            header="Implementation timeline and contract terms",
        ),
        Section(
            id="timeline/q1",
            parent_id="timeline",
            kind=SectionKind.QUESTION,
            header="What does a realistic implementation timeline look like?",
        ),
        Section(
            id="timeline/q2",
            parent_id="timeline",
            kind=SectionKind.QUESTION,
            header="What's your typical contract length and exit terms?",
        ),
        Section(
            id="references",
            parent_id="commercial_terms",
            kind=SectionKind.TOPIC,
            header="Comparable customers we could talk to",
        ),
        Section(
            id="references/q1",
            parent_id="references",
            kind=SectionKind.QUESTION,
            header="Who do you have running this at similar scale to us?",
        ),
        Section(
            id="decision_criteria",
            parent_id="commercial_terms",
            kind=SectionKind.TOPIC,
            header="What the vendor believes will tip our decision",
        ),
        Section(
            id="decision_criteria/q1",
            parent_id="decision_criteria",
            kind=SectionKind.QUESTION,
            header="In your experience, what tips customers like us toward yes or no?",
        ),
        # ---- wrap children ----
        Section(
            id="wrap/next_steps",
            parent_id="wrap",
            kind=SectionKind.TOPIC,
            header="Confirm gaps, next steps, and follow-ups",
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
            header="Anything I should send you to make a follow-up easier?",
        ),
    ],
)
