"""Offline briefing -> (template, objectives) extraction via the OpenAI Responses API.

Briefings may declare a template inline via YAML-style front-matter at the top:

    ---
    template: requirements
    ---
    # Briefing for ...

If front-matter is present and the template name is known, that template is used
directly and only objectives are extracted. Otherwise the LLM picks both.
"""

from __future__ import annotations

import re
from typing import Literal

from loguru import logger
from openai import OpenAI
from pydantic import BaseModel, Field

from .harness import Objective
from .templates import TEMPLATES, Template

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FM_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)\s*$", re.MULTILINE)


def split_frontmatter(briefing_markdown: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_fields, body_markdown).

    If no front-matter is present, returns ({}, briefing_markdown) unchanged.
    Only recognises top-level scalar `key: value` lines — no nesting, no lists.
    """
    m = _FRONTMATTER_RE.match(briefing_markdown)
    if not m:
        return {}, briefing_markdown
    fields: dict[str, str] = {}
    for fm in _FM_FIELD_RE.finditer(m.group(1)):
        key, value = fm.group(1), fm.group(2)
        fields[key] = value.strip().strip('"').strip("'")
    body = briefing_markdown[m.end() :]
    return fields, body


class _ExtractionPayload(BaseModel):
    """Wrapper Pydantic schema for structured output."""

    template: Literal["requirements", "research", "eval", "generic"]
    objectives: list[Objective] = Field(min_length=1)


def _build_extraction_system_prompt() -> str:
    template_lines = []
    for name, tmpl in TEMPLATES.items():
        template_lines.append(f"- {name}: {tmpl.description}")
    template_block = "\n".join(template_lines)

    return f"""\
You read a free-form meeting briefing in markdown. Return two things:

1) The template that best matches the meeting type. Choose exactly one of:
{template_block}

Pick `generic` if no other template clearly fits — do not force-fit.

2) The substantive objectives the consultant must cover. Each objective has:
- id: a short uppercase identifier (OBJ1, OBJ2, ...)
- objective: one sentence phrased as an outcome (not a question)
- success_criteria: one or two sentences describing what evidence in the
  conversation would mark this objective as covered

Aim for three to six objectives. Stay grounded in the briefing; do not invent.
Skip meta-instructions to the consultant (time budget, tone, opening style).
Focus on the substantive content the conversation must surface.
"""


def _extract_via_llm(
    briefing_body: str, model: str = "gpt-5-mini"
) -> tuple[Template, list[Objective]]:
    client = OpenAI()
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _build_extraction_system_prompt()},
            {"role": "user", "content": briefing_body},
        ],
        text_format=_ExtractionPayload,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("extraction returned no parsed output")
    template = TEMPLATES.get(parsed.template, TEMPLATES["generic"])
    return template, parsed.objectives


def extract_briefing_plan(
    briefing_markdown: str,
    model: str = "gpt-5-mini",
    custom_template: Template | None = None,
) -> tuple[Template, list[Objective], str]:
    """Pick a template and extract objectives from a briefing.

    Returns (template, objectives, body_markdown) where body_markdown is the
    briefing content with any front-matter stripped — this is what gets embedded
    in the live system prompt.

    If `custom_template` is supplied, it is used directly: template selection
    (front-matter / inference) is skipped, but objectives are still extracted
    from the briefing body.
    """
    fields, body = split_frontmatter(briefing_markdown)

    if custom_template is not None:
        _, objectives = _extract_via_llm(body, model=model)
        logger.info("template supplied by caller: {}", custom_template.name)
        return custom_template, objectives, body

    fm_template_name = fields.get("template")

    if fm_template_name and fm_template_name in TEMPLATES:
        template = TEMPLATES[fm_template_name]
        _, objectives = _extract_via_llm(body, model=model)
        logger.info("template selected via front-matter: {}", template.name)
        return template, objectives, body

    if fm_template_name and fm_template_name not in TEMPLATES:
        logger.warning(
            "front-matter requested unknown template '{}'; falling back to inference",
            fm_template_name,
        )

    template, objectives = _extract_via_llm(body, model=model)
    logger.info("template selected via inference: {}", template.name)
    return template, objectives, body


def extract_objectives(briefing_markdown: str, model: str = "gpt-5-mini") -> list[Objective]:
    """Backwards-compatible thin wrapper that returns objectives only."""
    _, objectives, _ = extract_briefing_plan(briefing_markdown, model=model)
    return objectives
