"""Briefing → template selection.

The briefing can declare its template via YAML-style front-matter:

    ---
    template: requirements
    ---
    # Briefing for ...

If front-matter names a known template, it wins. Otherwise an LLM picks the
best fit (defaulting to `generic` when nothing matches cleanly).
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
    """Return (frontmatter_fields, body_markdown). No nesting, no lists."""
    m = _FRONTMATTER_RE.match(briefing_markdown)
    if not m:
        return {}, briefing_markdown
    fields: dict[str, str] = {}
    for fm in _FM_FIELD_RE.finditer(m.group(1)):
        key, value = fm.group(1), fm.group(2)
        fields[key] = value.strip().strip('"').strip("'")
    body = briefing_markdown[m.end() :]
    return fields, body


class _TemplateChoice(BaseModel):
    template: Literal["requirements", "research", "eval", "generic"]


def _system_prompt() -> str:
    options = "\n".join(f"- {name}: {tmpl.description}" for name, tmpl in TEMPLATES.items())
    return f"""\
You read a free-form meeting briefing in markdown. Pick the template that best
matches the meeting type. Choose exactly one of:
{options}

Pick `generic` if no other template clearly fits — do not force-fit.
"""


def _pick_via_llm(briefing_body: str, model: str = "gpt-5-mini") -> Template:
    client = OpenAI()
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": briefing_body},
        ],
        text_format=_TemplateChoice,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("template selection returned no parsed output")
    return TEMPLATES.get(parsed.template, TEMPLATES["generic"])


def select_template(
    briefing_markdown: str, model: str = "gpt-5-mini"
) -> tuple[Template, str]:
    """Pick a template and return (template, body_markdown).

    `body_markdown` is the briefing with any front-matter stripped — this is
    what gets embedded in the live system prompt.
    """
    fields, body = split_frontmatter(briefing_markdown)
    fm_name = fields.get("template")

    if fm_name and fm_name in TEMPLATES:
        logger.info("template selected via front-matter: {}", fm_name)
        return TEMPLATES[fm_name], body

    if fm_name and fm_name not in TEMPLATES:
        logger.warning(
            "front-matter requested unknown template '{}'; falling back to inference",
            fm_name,
        )

    template = _pick_via_llm(body, model=model)
    logger.info("template selected via inference: {}", template.name)
    return template, body
