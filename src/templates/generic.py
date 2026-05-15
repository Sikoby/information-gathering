"""Generic fallback template — flat notebook, single phase.

Use when no other template clearly fits, or as the safe default when extraction
is unsure. Preserves the pre-template-library behaviour of a single bucket of
free-form notes.
"""

from __future__ import annotations

from .schema import NotebookSection, Phase, Template

GENERIC_TEMPLATE = Template(
    name="generic",
    description=(
        "Generic meeting with no specific structural expectations. Use this when "
        "no other template clearly fits the briefing."
    ),
    sections=[
        NotebookSection(
            id="notes",
            label="Notes",
            description="Material learnings of any kind.",
        ),
    ],
    phases=[
        Phase(
            id="meeting",
            label="Meeting",
            goal="Cover the briefing's objectives within the time budget.",
            target_fraction=1.0,
            sections_in_focus=["notes"],
        ),
    ],
)
