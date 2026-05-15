"""Vendor evaluation template."""

from __future__ import annotations

from .schema import NotebookSection, Phase, Template

EVAL_TEMPLATE = Template(
    name="eval",
    description=(
        "Vendor evaluation conversation. The consultant probes whether a vendor's "
        "offering meets specific requirements, where the gaps are, and on what "
        "commercial terms."
    ),
    sections=[
        NotebookSection(
            id="requirements_coverage",
            label="Requirements coverage",
            description="Which of our requirements the vendor claims to meet, with evidence.",
        ),
        NotebookSection(
            id="gaps",
            label="Gaps",
            description="Requirements the vendor does not meet, or only partially.",
        ),
        NotebookSection(
            id="pricing",
            label="Pricing",
            description="Pricing model, ranges, what drives cost up or down.",
            repeated=False,
        ),
        NotebookSection(
            id="integration_concerns",
            label="Integration concerns",
            description="How they integrate with our stack; what work falls on us vs them.",
        ),
        NotebookSection(
            id="references",
            label="References",
            description="Comparable customers we could talk to.",
        ),
        NotebookSection(
            id="decision_criteria",
            label="Decision criteria",
            description="What the vendor believes will tip our decision either way.",
            repeated=False,
        ),
        NotebookSection(
            id="timeline",
            label="Timeline",
            description="Implementation timeline, contract length, next steps.",
            repeated=False,
        ),
    ],
    phases=[
        Phase(
            id="rapport",
            label="Rapport",
            goal="Introduce, confirm agenda, set time expectations.",
            target_fraction=0.10,
            sections_in_focus=[],
        ),
        Phase(
            id="capability_check",
            label="Capability check",
            goal=(
                "Walk through our requirements; press for evidence, not just yes/no. "
                "Surface gaps and integration concerns."
            ),
            target_fraction=0.50,
            sections_in_focus=["requirements_coverage", "gaps", "integration_concerns"],
        ),
        Phase(
            id="commercial_terms",
            label="Commercial terms",
            goal=(
                "Probe pricing model, timeline, references, what tips the decision. "
                "Avoid committing on our side."
            ),
            target_fraction=0.30,
            sections_in_focus=["pricing", "timeline", "decision_criteria", "references"],
        ),
        Phase(
            id="wrap",
            label="Wrap",
            goal="Summarise gaps, confirm follow-ups, close.",
            target_fraction=0.10,
            sections_in_focus=[],
        ),
    ],
)
