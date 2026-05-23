"""Vendor evaluation template."""

from __future__ import annotations

from .schema import Section, SectionKind, Template

EVAL_TEMPLATE = Template(
    name="eval",
    description=(
        "Vendor evaluation conversation. The consultant probes whether a vendor's "
        "offering meets specific requirements, where the gaps are, and on what "
        "commercial terms."
    ),
    sections=[
        # ── phases ──
        Section(
            id="rapport",
            kind=SectionKind.PHASE,
            target_fraction=0.10,
            header="Introduce; confirm agenda and time.",
        ),
        Section(
            id="capability_check",
            kind=SectionKind.PHASE,
            target_fraction=0.50,
            header="Match the vendor's offering against our requirements.",
            body="Press for evidence, not yes/no. Surface gaps and integration concerns.",
        ),
        Section(
            id="commercial_terms",
            kind=SectionKind.PHASE,
            target_fraction=0.30,
            header="Probe pricing, timeline, and references.",
            body="Avoid committing on our side; understand what tips their decision.",
        ),
        Section(
            id="wrap",
            kind=SectionKind.PHASE,
            target_fraction=0.10,
            header="Summarise gaps; confirm follow-ups.",
        ),

        # ── capability_check children ──
        Section(
            id="requirements_coverage",
            kind=SectionKind.TOPIC,
            parent_id="capability_check",
            header="Which of our requirements they claim to meet.",
        ),
        Section(
            id="requirements_coverage/q_evidence",
            kind=SectionKind.QUESTION,
            parent_id="requirements_coverage",
            header="What concrete evidence supports each 'yes'?",
        ),
        # Illustrative deeper nesting: one specific requirement gets its own subtree.
        Section(
            id="requirements_coverage/critical_one",
            kind=SectionKind.TOPIC,
            parent_id="requirements_coverage",
            header="The single most critical requirement, deep-dived.",
        ),
        Section(
            id="requirements_coverage/critical_one/q_demo",
            kind=SectionKind.QUESTION,
            parent_id="requirements_coverage/critical_one",
            header="Can you show this working in a live demo, not slides?",
        ),

        Section(
            id="gaps",
            kind=SectionKind.TOPIC,
            parent_id="capability_check",
            header="Requirements the vendor only partially meets.",
        ),
        Section(
            id="gaps/q_workaround",
            kind=SectionKind.QUESTION,
            parent_id="gaps",
            header="What workaround exists for each gap, and at what cost?",
        ),

        Section(
            id="integration_concerns",
            kind=SectionKind.TOPIC,
            parent_id="capability_check",
            header="How they integrate; what work falls on us vs them.",
        ),
        Section(
            id="integration_concerns/q_division",
            kind=SectionKind.QUESTION,
            parent_id="integration_concerns",
            header="In a typical integration, what's on us vs on you?",
        ),

        # ── commercial_terms children ──
        Section(
            id="pricing",
            kind=SectionKind.TOPIC,
            parent_id="commercial_terms",
            header="Pricing model and ranges.",
            repeated=False,
        ),
        Section(
            id="pricing/q_drivers",
            kind=SectionKind.QUESTION,
            parent_id="pricing",
            header="What drives cost up or down most?",
        ),

        Section(
            id="timeline",
            kind=SectionKind.TOPIC,
            parent_id="commercial_terms",
            header="Implementation and contract timeline.",
            repeated=False,
        ),

        Section(
            id="references",
            kind=SectionKind.TOPIC,
            parent_id="commercial_terms",
            header="Comparable customers we could talk to.",
        ),

        Section(
            id="decision_criteria",
            kind=SectionKind.TOPIC,
            parent_id="commercial_terms",
            header="What the vendor believes will tip our decision.",
            repeated=False,
        ),
    ],
)
