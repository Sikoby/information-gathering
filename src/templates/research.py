"""User research interview template."""

from __future__ import annotations

from .schema import ROOT_SECTION_ID, Section, SectionKind, Template

RESEARCH_TEMPLATE = Template(
    name="research",
    description=(
        "User research interview. The consultant explores how someone actually "
        "works, what jobs they're trying to do, and tests hypotheses about their "
        "behaviour."
    ),
    sections=[
        # ---- scheduled top-level TOPICs ----
        Section(
            id="rapport",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Set the person at ease and confirm consent",
            body="Set the person at ease, confirm consent, explain you're listening, not selling.",
            target_fraction=0.10,
        ),
        Section(
            id="explore_behaviour",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Walk through how they actually do the thing today",
            body=(
                "Concrete, recent examples. Avoid hypothetical 'would you'. "
                "Get specific about steps, tools, routines, and context."
            ),
            target_fraction=0.55,
        ),
        Section(
            id="probe_motivation",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Probe motivation and test the briefing's hypotheses",
            body=(
                "Why this way, what would they change, what surprised you. "
                "Push lightly on hypotheses without leading."
            ),
            target_fraction=0.25,
        ),
        Section(
            id="wrap",
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Thank them and close",
            body="Thank them, confirm any follow-up permission, close.",
            target_fraction=0.10,
        ),
        # ---- rapport children ----
        Section(
            id="context_intro",
            parent_id="rapport",
            kind=SectionKind.TOPIC,
            header="Their role and current context",
        ),
        Section(
            id="context_intro/q1",
            parent_id="context_intro",
            kind=SectionKind.QUESTION,
            header="Tell me a bit about your role and what your week looks like.",
        ),
        Section(
            id="context_intro/q2",
            parent_id="context_intro",
            kind=SectionKind.QUESTION,
            header="What's been on your mind lately at work?",
        ),
        # ---- explore_behaviour children ----
        Section(
            id="jobs_to_be_done",
            parent_id="explore_behaviour",
            kind=SectionKind.TOPIC,
            header="The outcomes they're trying to achieve",
        ),
        Section(
            id="jobs_to_be_done/q1",
            parent_id="jobs_to_be_done",
            kind=SectionKind.QUESTION,
            header="When you sit down to do this, what are you actually trying to get done?",
        ),
        Section(
            id="jobs_to_be_done/q2",
            parent_id="jobs_to_be_done",
            kind=SectionKind.QUESTION,
            header="How do you know when you're done?",
        ),
        Section(
            id="behaviours",
            parent_id="explore_behaviour",
            kind=SectionKind.TOPIC,
            header="What they actually do today — steps, tools, routines",
        ),
        Section(
            id="behaviours/q1",
            parent_id="behaviours",
            kind=SectionKind.QUESTION,
            header="Walk me through the last time you did this, step by step.",
        ),
        Section(
            id="behaviours/q2",
            parent_id="behaviours",
            kind=SectionKind.QUESTION,
            header="Which tools or apps are you in while you do it?",
        ),
        # deeper-nested TOPIC under behaviours (the depth example for this template)
        Section(
            id="behaviours/workarounds",
            parent_id="behaviours",
            kind=SectionKind.TOPIC,
            header="Workarounds and side-paths they've improvised",
        ),
        Section(
            id="behaviours/workarounds/q1",
            parent_id="behaviours/workarounds",
            kind=SectionKind.QUESTION,
            header="Anywhere you've hacked together your own way of doing something?",
        ),
        Section(
            id="behaviours/workarounds/q2",
            parent_id="behaviours/workarounds",
            kind=SectionKind.QUESTION,
            header="What does the official process not handle that you have to work around?",
        ),
        Section(
            id="contexts_of_use",
            parent_id="explore_behaviour",
            kind=SectionKind.TOPIC,
            header="Where, when, with whom, under what conditions",
        ),
        Section(
            id="contexts_of_use/q1",
            parent_id="contexts_of_use",
            kind=SectionKind.QUESTION,
            header="Where are you and what's around you when you do this?",
        ),
        Section(
            id="contexts_of_use/q2",
            parent_id="contexts_of_use",
            kind=SectionKind.QUESTION,
            header="Who else is involved or watching when this happens?",
        ),
        # ---- probe_motivation children ----
        Section(
            id="surprises",
            parent_id="probe_motivation",
            kind=SectionKind.TOPIC,
            header="Things you didn't expect — worth investigating later",
        ),
        Section(
            id="surprises/q1",
            parent_id="surprises",
            kind=SectionKind.QUESTION,
            header="Is anything about how you do this that surprises people from outside?",
        ),
        Section(
            id="surprises/q2",
            parent_id="surprises",
            kind=SectionKind.QUESTION,
            header="If you could change one thing about it, what would it be?",
        ),
        Section(
            id="hypotheses_tested",
            parent_id="probe_motivation",
            kind=SectionKind.TOPIC,
            header="Hypotheses from the briefing — supported, contradicted, or open",
        ),
        Section(
            id="hypotheses_tested/q1",
            parent_id="hypotheses_tested",
            kind=SectionKind.QUESTION,
            header="What do you think drives the choices you make here?",
        ),
        Section(
            id="hypotheses_tested/q2",
            parent_id="hypotheses_tested",
            kind=SectionKind.QUESTION,
            header="What would make you switch to a different approach?",
        ),
        Section(
            id="quotes_to_save",
            parent_id="probe_motivation",
            kind=SectionKind.TOPIC,
            header="Verbatim phrasing worth preserving",
        ),
        Section(
            id="quotes_to_save/q1",
            parent_id="quotes_to_save",
            kind=SectionKind.QUESTION,
            header="How would you describe this in your own words to a colleague?",
        ),
        # ---- wrap children ----
        Section(
            id="wrap/closing",
            parent_id="wrap",
            kind=SectionKind.TOPIC,
            header="Closing and any follow-up permission",
        ),
        Section(
            id="wrap/closing/q1",
            parent_id="wrap/closing",
            kind=SectionKind.QUESTION,
            header="Anything else you wish I'd asked?",
        ),
        Section(
            id="wrap/closing/q2",
            parent_id="wrap/closing",
            kind=SectionKind.QUESTION,
            header="Would it be okay to follow up if anything else comes up later?",
        ),
    ],
)
