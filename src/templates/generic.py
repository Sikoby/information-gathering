"""Generic fallback template — single scheduled top-level TOPIC.

Use when no other template clearly fits, or as the safe default when extraction
is unsure. Preserves the pre-template-library behaviour of a single bucket of
free-form notes.
"""

from __future__ import annotations

from .schema import ROOT_SECTION_ID, Section, SectionKind, Template

GENERIC_TEMPLATE = Template(
    name="generic",
    description=(
        "Generic meeting with no specific structural expectations. Use this when "
        "no other template clearly fits the briefing."
    ),
    sections=[
        Section(
            id="meeting",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Cover the briefing's objectives within the time budget",
            body="Adapt to the briefing; capture material learnings as you go.",
            target_fraction=1.0,
        ),
        Section(
            id="meeting/notes",
            parent_id="meeting",
            kind=SectionKind.TOPIC,
            header="Material learnings of any kind",
        ),
        Section(
            id="meeting/notes/q1",
            parent_id="meeting/notes",
            kind=SectionKind.QUESTION,
            header="What's the most important thing for me to understand here?",
        ),
        Section(
            id="meeting/notes/q2",
            parent_id="meeting/notes",
            kind=SectionKind.QUESTION,
            header="What would I miss if I only read the briefing?",
        ),
        # deeper-nested TOPIC (the depth example for this template)
        Section(
            id="meeting/notes/follow_ups",
            parent_id="meeting/notes",
            kind=SectionKind.TOPIC,
            header="Follow-ups worth coming back to",
        ),
        Section(
            id="meeting/notes/follow_ups/q1",
            parent_id="meeting/notes/follow_ups",
            kind=SectionKind.QUESTION,
            header="What should I look into more after this conversation?",
        ),
    ],
)
