"""Implementation + critique loop that synthesises a meeting `Template`.

Two OpenAI Responses API calls per iteration:
- `propose` — produces a `Template` (structured output via Pydantic).
- `critique` — produces a `CritiqueResult` judging the proposal.

The loop runs until the critique returns `approved=true` or `max_iterations` is
reached. The final template plus the full iteration history are returned.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

from loguru import logger
from openai import OpenAI

from ..templates import TEMPLATES, Template
from .schemas import (
    CritiqueResult,
    GenerateRequest,
    GenerationIteration,
)


DEFAULT_IMPL_MODEL = os.environ.get("TEMPLATE_GEN_IMPL_MODEL", "gpt-5")
DEFAULT_CRITIQUE_MODEL = os.environ.get("TEMPLATE_GEN_CRITIQUE_MODEL", "gpt-5")


@dataclass
class GenerationResult:
    template: Template
    iterations: list[GenerationIteration]
    approved: bool


def _resolve_reference(name: str | None) -> Template | None:
    if not name:
        return None
    template = TEMPLATES.get(name)
    if template is None:
        raise ValueError(
            f"unknown reference_template '{name}'. "
            f"Known templates: {sorted(TEMPLATES.keys())}"
        )
    return template


def _propose_system_prompt() -> str:
    return """\
You design meeting templates for a briefing-driven voice meeting agent. The
agent uses the template to (a) bucket findings into notebook sections and (b)
pace the conversation through phases.

A Template has:

- name: short snake_case identifier (e.g. "design_review", "compliance_audit").
- description: one or two sentences naming the meeting type and what it is for.
- sections: 4-8 NotebookSection items, each with:
  - id: snake_case
  - label: human-readable
  - description: one sentence the agent reads to decide what belongs in the
    section. Be specific and action-oriented.
  - repeated: true if many findings of this kind are expected (the default).
    Set false only for one-shot facts (e.g. "stakeholders_and_decision_process").
  Sections must be substantive, mutually exclusive, and collectively
  exhaustive for this meeting's purpose. DO NOT include a generic
  "other"/"misc"/"notes" bucket; one is appended automatically.
- phases: 3-5 Phase items, each with:
  - id: snake_case
  - label: human-readable
  - goal: one sentence describing what the consultant is trying to achieve
    in this phase.
  - target_fraction: share of total meeting time (0 < x <= 1). All phase
    fractions should sum to approximately 1.0.
  - sections_in_focus: ids of sections that should mostly be filled during
    this phase. May be empty for rapport / wrap phases.
  Most meetings should start with a short rapport phase and end with a wrap
  phase that confirms next steps.

Quality bar:
- A human reading the template alone should be able to predict what the
  conversation will look like and what notes will come out of it.
- Section descriptions should distinguish themselves from each other so an
  LLM filing a finding can pick the right bucket without ambiguity.
- Phase goals should be different enough that "what phase am I in?" is a
  meaningful question.

Return ONLY the Template; do not narrate.
"""


def _critique_system_prompt() -> str:
    return """\
You are a strict reviewer of meeting templates produced for a briefing-driven
voice meeting agent. You will receive (a) the user's description of the
meeting, (b) a proposed Template, and optionally (c) a reference template the
proposer used for inspiration.

Judge the proposal against:

- STRUCTURE: 4-8 substantive sections (the auto-appended "other" does not
  count); 3-5 phases; phase target_fractions sum to ~1.0 (0.95-1.05 is fine).
- SECTIONS: substantive, mutually exclusive, collectively exhaustive for the
  meeting's purpose. Descriptions are concrete and distinguishable. No
  trivial or redundant sections. `repeated=false` only when truly one-shot.
- PHASES: pacing makes sense for the meeting type. Each phase has a real
  goal distinct from its neighbours. sections_in_focus references existing
  section ids.
- COVERAGE: read the user's description carefully. Are there aspects it
  implies that the template fails to capture? Name them.
- NAMING: ids are snake_case, labels are human-readable, names are not
  generic ("topic_1") or off-theme.

Severity rubric:
- blocker — template is structurally invalid or unusable as-is.
- major — important coverage gap, ambiguity that an LLM filer would mis-bucket,
  or pacing that would harm the meeting.
- minor — wording, polish, naming preferences.

`approved` is true ONLY when there are zero blocker and zero major issues.
Minor issues alone do not block approval.

Be specific. Vague feedback ("add more sections") is useless. Cite section
ids and quote the user's description when you point at coverage gaps.

If not approved, set `next_iteration_focus` to the SINGLE most important
change the next revision should prioritise.
"""


def _format_reference_block(reference: Template | None) -> str:
    if reference is None:
        return "No reference template was provided.\n"
    body = reference.model_dump_json(indent=2)
    return (
        "Reference template (use as structural inspiration, but adapt to the "
        "user's description; do not copy verbatim):\n"
        f"```json\n{body}\n```\n"
    )


def _format_previous_block(
    previous_template: Template | None,
    previous_critique: CritiqueResult | None,
) -> str:
    if previous_template is None or previous_critique is None:
        return ""
    tmpl_json = previous_template.model_dump_json(indent=2)
    crit_json = previous_critique.model_dump_json(indent=2)
    return (
        "Your previous draft was reviewed. Address every blocker and major "
        "issue. Consider minor suggestions where they improve clarity.\n\n"
        f"Previous draft:\n```json\n{tmpl_json}\n```\n\n"
        f"Reviewer critique:\n```json\n{crit_json}\n```\n"
    )


def _build_propose_user_message(
    request: GenerateRequest,
    reference: Template | None,
    previous_template: Template | None,
    previous_critique: CritiqueResult | None,
) -> str:
    parts = [
        "User's description of the meeting:",
        request.description.strip(),
        "",
        _format_reference_block(reference),
    ]
    if request.name_hint:
        parts.append(
            f"Naming hint (the user suggests `{request.name_hint}` as the "
            "template id; use it if reasonable, otherwise pick something better).\n"
        )
    previous = _format_previous_block(previous_template, previous_critique)
    if previous:
        parts.append(previous)
    return "\n".join(p for p in parts if p)


def _build_critique_user_message(
    request: GenerateRequest,
    reference: Template | None,
    proposed: Template,
) -> str:
    parts = [
        "User's description of the meeting:",
        request.description.strip(),
        "",
        _format_reference_block(reference),
        "Proposed template:",
        f"```json\n{proposed.model_dump_json(indent=2)}\n```",
    ]
    return "\n".join(parts)


def _propose_sync(
    request: GenerateRequest,
    reference: Template | None,
    previous_template: Template | None,
    previous_critique: CritiqueResult | None,
    model: str,
) -> Template:
    client = OpenAI()
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _propose_system_prompt()},
            {
                "role": "user",
                "content": _build_propose_user_message(
                    request, reference, previous_template, previous_critique
                ),
            },
        ],
        text_format=Template,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("implementation agent returned no parsed Template")
    return parsed


def _critique_sync(
    request: GenerateRequest,
    reference: Template | None,
    proposed: Template,
    model: str,
) -> CritiqueResult:
    client = OpenAI()
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _critique_system_prompt()},
            {
                "role": "user",
                "content": _build_critique_user_message(request, reference, proposed),
            },
        ],
        text_format=CritiqueResult,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("critique agent returned no parsed CritiqueResult")
    return parsed


async def generate(
    request: GenerateRequest,
    impl_model: str = DEFAULT_IMPL_MODEL,
    critique_model: str = DEFAULT_CRITIQUE_MODEL,
) -> GenerationResult:
    """Run the implementation + critique loop and return the final result."""
    reference = _resolve_reference(request.reference_template)
    iterations: list[GenerationIteration] = []
    template: Template | None = None
    critique: CritiqueResult | None = None

    for i in range(request.max_iterations):
        logger.info(
            "iteration {}/{} — proposing template (impl_model={})",
            i + 1,
            request.max_iterations,
            impl_model,
        )
        template = await asyncio.to_thread(
            _propose_sync,
            request,
            reference,
            template,
            critique,
            impl_model,
        )
        logger.info(
            "iteration {} — critiquing template (critique_model={})",
            i + 1,
            critique_model,
        )
        critique = await asyncio.to_thread(
            _critique_sync,
            request,
            reference,
            template,
            critique_model,
        )
        iterations.append(
            GenerationIteration(iteration=i + 1, template=template, critique=critique)
        )
        if critique.approved:
            logger.info("iteration {} approved by critique — stopping", i + 1)
            break
        logger.info(
            "iteration {} not approved (issues={}); focus for next: {}",
            i + 1,
            len(critique.issues),
            critique.next_iteration_focus,
        )

    assert template is not None and critique is not None
    return GenerationResult(
        template=template,
        iterations=iterations,
        approved=critique.approved,
    )
