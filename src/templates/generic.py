"""Generic fallback template — single phase, single topic.

Use when no other template clearly fits. Preserves the pre-template-library
behaviour of a single bucket of free-form notes.
"""

from __future__ import annotations

from .schema import Section, SectionKind, Template

GENERIC_TEMPLATE = Template(
    name="generic",
    description=(
        "Generic meeting with no specific structural expectations. Use this when "
        "no other template clearly fits the briefing."
    ),
    sections=[
        Section(
            id="meeting_phase",
            kind=SectionKind.PHASE,
            target_fraction=1.0,
            header="Cover the briefing within the time budget.",
        ),
        Section(
            id="notes",
            kind=SectionKind.TOPIC,
            parent_id="meeting_phase",
            header="Material learnings of any kind.",
        ),
    ],
)
