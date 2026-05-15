"""User research interview template."""

from __future__ import annotations

from .schema import NotebookSection, Phase, Template

RESEARCH_TEMPLATE = Template(
    name="research",
    description=(
        "User research interview. The consultant explores how someone actually "
        "works, what jobs they're trying to do, and tests hypotheses about their "
        "behaviour."
    ),
    sections=[
        NotebookSection(
            id="jobs_to_be_done",
            label="Jobs to be done",
            description="The outcomes the person is trying to achieve, in their own framing.",
        ),
        NotebookSection(
            id="behaviours",
            label="Behaviours",
            description="What the person actually does today: steps, tools, routines.",
        ),
        NotebookSection(
            id="contexts_of_use",
            label="Contexts of use",
            description="Where, when, with whom, under what conditions.",
        ),
        NotebookSection(
            id="surprises",
            label="Surprises",
            description="Anything the consultant did not expect; signals worth investigating later.",
        ),
        NotebookSection(
            id="hypotheses_tested",
            label="Hypotheses tested",
            description=(
                "Hypotheses the briefing came in with, and whether the conversation "
                "supported, contradicted, or left them open."
            ),
        ),
        NotebookSection(
            id="quotes_to_save",
            label="Quotes to save",
            description="Verbatim phrasing worth preserving for downstream use.",
        ),
    ],
    phases=[
        Phase(
            id="rapport",
            label="Rapport",
            goal="Set the person at ease, confirm consent, explain you're listening not selling.",
            target_fraction=0.10,
            sections_in_focus=[],
        ),
        Phase(
            id="explore_behaviour",
            label="Explore behaviour",
            goal=(
                "Walk through how the person actually does the thing today. "
                "Concrete, recent examples. Avoid hypothetical 'would you'."
            ),
            target_fraction=0.55,
            sections_in_focus=["behaviours", "contexts_of_use", "jobs_to_be_done"],
        ),
        Phase(
            id="probe_motivation",
            label="Probe motivation",
            goal=(
                "Why this way, what would they change, what surprised you. "
                "Test the briefing's hypotheses."
            ),
            target_fraction=0.25,
            sections_in_focus=["jobs_to_be_done", "surprises", "hypotheses_tested"],
        ),
        Phase(
            id="wrap",
            label="Wrap",
            goal="Thank them, confirm any follow-up permission, close.",
            target_fraction=0.10,
            sections_in_focus=[],
        ),
    ],
)
