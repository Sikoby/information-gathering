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
agent uses the template to (a) pace the conversation through "phases" and
(b) drive through topics + questions whose answers are recorded at runtime.

A Template is a single tree of `Section` nodes. Each Section has:

- id: short, slash-separated path of snake_case tokens (e.g. "define",
  "define/pain_points", "define/pain_points/q1"). Must be unique within the
  template.
- parent_id: id of the parent section, or null for the root.
- kind: exactly one of
    - "meeting": the root of the tree (id "_root"). Auto-added if missing —
      you do not need to emit it.
    - "topic": a thematic unit. Owns child topics and questions.
    - "question": a specific thing the consultant wants to find out. Owns
      ANSWERs at runtime. DO NOT include answers in the template.
    - "answer": runtime-only. Do not emit any of these.
- header: human-readable headline. For topics, a short noun phrase; for
  questions, a question (ending in "?").
- body: optional one or two sentences of context. For "scheduled" top-level
  topics (phases), put the phase goal here. The participant sees `body` in the
  live meeting viewer, so write it as if speaking to them.
- private_notes: optional "speaker notes" for the meeting agent — delivery
  cues the agent reads but the participant never sees (think of the notes
  panel under a PowerPoint slide). Use for tone, pacing, what to say or
  avoid, sensitivities, or framing context that should colour how the agent
  handles the section. Examples: "the stakeholder was burned by a previous
  vendor — open with curiosity, not capability claims" or "if they deflect
  on budget, don't push; move to constraints". Optional — leave null when
  there's nothing speaker-specific to say. Do NOT duplicate body content
  here; body is the public goal/description, private_notes are delivery cues.
- target_fraction: only set on top-level TOPICs you want to schedule as
  "phases" (0 < x ≤ 1). The set of scheduled top-level topics is the agenda;
  their target_fractions must sum to approximately 1.0.

Tree rules:
- MEETING children are TOPICs only.
- TOPIC children are TOPICs or QUESTIONs (in any mix).
- QUESTION children are ANSWERs only (which the runtime adds — do NOT emit).
- A scheduled TOPIC must be a direct child of the root. Nested scheduled
  topics are rejected.
- Depth is capped at 5 (root → phase → topic → question is 3).

Shape we want:
- 3-5 scheduled top-level TOPICs (the agenda). target_fractions sum to ~1.0.
  Most meetings start with a short rapport phase and end with a wrap phase
  that confirms next steps.
- Each phase owns 1-3 child TOPICs (inner topics).
- Each inner TOPIC owns 2-3 child QUESTIONs.
- Optionally, one example of deeper TOPIC nesting (TOPIC under TOPIC) for a
  particularly rich area. Do NOT nest a TOPIC under a QUESTION.

DO NOT include a generic "other"/"misc"/"notes" topic — one is auto-appended.
DO NOT emit a closing/wrap-up section with a fixed id; the agent writes that
at runtime.

Quality bar:
- A human reading the template alone should be able to predict what the
  conversation will look like and what notes will come out of it.
- Topic headers should distinguish themselves from each other so an LLM
  routing a finding can pick the right question without ambiguity.
- Phase headers (the scheduled top-level topics) should be different enough
  that "which phase am I in?" is a meaningful question.

Return ONLY the Template; do not narrate.
"""


def _critique_system_prompt() -> str:
    return """\
You are a strict reviewer of meeting templates produced for a briefing-driven
voice meeting agent. You will receive (a) the user's description of the
meeting, (b) a proposed Template (a Section tree), and optionally (c) a
reference template the proposer used for inspiration.

Background on the template shape:
- The template is one tree of Section nodes with kind in {meeting, topic,
  question, answer}. ANSWERs are runtime-only and must not appear here.
- A "phase" is a top-level TOPIC with `target_fraction` set. The set of those
  TOPICs is the agenda; their target_fractions must sum to ~1.0.
- TOPICs own TOPICs + QUESTIONs. QUESTIONs own only ANSWERs (so QUESTIONs in
  the template have no children).
- The auto-appended "other" topic + "other/q" question are not part of the
  proposal — don't penalise the proposer for omitting them.

Judge the proposal against:

- STRUCTURE: 3-5 scheduled top-level TOPICs (the agenda) summing to ~1.0
  (0.95-1.05 is fine); 4-8 substantive inner TOPICs in total; 2-3 QUESTIONs
  per inner TOPIC; ANSWER nodes must NOT appear; no scheduled-TOPIC nesting;
  QUESTIONs have no children.
- TOPICS: substantive, mutually exclusive, collectively exhaustive for the
  meeting's purpose. Headers are concrete and distinguishable. No trivial or
  redundant topics.
- QUESTIONS: phrased as questions (ideally ending in "?"). Specific enough
  that an answer would be substantive. Not duplicates of each other or of
  the parent topic header.
- PHASES (scheduled top-level TOPICs): pacing makes sense for the meeting
  type. Each has a real goal distinct from its neighbours. Most meetings
  open with a short rapport phase and end with a wrap phase.
- COVERAGE: read the user's description carefully. Are there aspects it
  implies that the template fails to capture? Name them.
- NAMING: ids are slash-separated snake_case paths; headers are human-readable
  and not generic ("topic_1") or off-theme.
- PRIVATE_NOTES (when used): genuine speaker notes — tone/pacing/what-to-say
  cues for the agent, not visible to the participant. Reject when it
  duplicates body or restates the obvious. OK to be direct since the
  participant will never see them. Leaving private_notes null is fine when
  there's nothing speaker-specific to say.

Severity rubric:
- blocker — template is structurally invalid or unusable as-is (e.g. ANSWERs
  in the template, QUESTIONs with children, scheduled topic nested under
  another scheduled topic, target_fractions don't sum to ~1.0).
- major — important coverage gap, ambiguity that would mis-route a finding,
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
