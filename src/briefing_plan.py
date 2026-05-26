"""Offline briefing -> Template selection via front-matter or OpenAI.

Briefings may declare a template inline via YAML-style front-matter at the top:

    ---
    template: requirements
    ---
    # Briefing for ...

If front-matter is present and the template name is known, that template is
used directly. Otherwise a short LLM call picks one of the four built-ins
(`requirements`, `research`, `eval`, `generic`).
"""

from __future__ import annotations

import re
from typing import Literal

from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

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


class _SelectionPayload(BaseModel):
    template: Literal["requirements", "research", "eval", "generic"]


def _build_selection_system_prompt() -> str:
    template_lines = [f"- {name}: {tmpl.description}" for name, tmpl in TEMPLATES.items()]
    return (
        "You read a free-form meeting briefing in markdown and pick the "
        "template that best matches its purpose. Choose exactly one of:\n\n"
        + "\n".join(template_lines)
        + "\n\nPick `generic` if no other template clearly fits — do not force-fit."
    )


def _select_via_llm(briefing_body: str, model: str = "gpt-5-mini") -> Template:
    client = OpenAI()
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _build_selection_system_prompt()},
            {"role": "user", "content": briefing_body},
        ],
        text_format=_SelectionPayload,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("template selection returned no parsed output")
    return TEMPLATES.get(parsed.template, TEMPLATES["generic"])


def select_template(
    briefing_markdown: str,
    model: str = "gpt-5-mini",
    custom_template: Template | None = None,
) -> tuple[Template, str]:
    """Pick a Template for the briefing.

    Returns (template, body_markdown) where body_markdown has any front-matter
    stripped — that's what gets embedded in the live system prompt.

    Precedence: explicit `custom_template` > front-matter `template:` field >
    LLM inference > `generic` fallback.
    """
    fields, body = split_frontmatter(briefing_markdown)

    if custom_template is not None:
        logger.info("template supplied by caller: {}", custom_template.name)
        return custom_template, body

    fm_template_name = fields.get("template")
    if fm_template_name and fm_template_name in TEMPLATES:
        template = TEMPLATES[fm_template_name]
        logger.info("template selected via front-matter: {}", template.name)
        return template, body
    if fm_template_name and fm_template_name not in TEMPLATES:
        logger.warning(
            "front-matter requested unknown template '{}'; falling back to inference",
            fm_template_name,
        )

    template = _select_via_llm(body, model=model)
    logger.info("template selected via inference: {}", template.name)
    return template, body
