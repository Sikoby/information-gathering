"""Offline briefing -> objectives extraction via the OpenAI Responses API."""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from .harness import Objective


class _ObjectivesPayload(BaseModel):
    """Wrapper Pydantic schema for structured output."""

    objectives: list[Objective] = Field(min_length=1)


_SYSTEM = """\
You read a free-form meeting briefing in markdown and return the substantive
objectives the consultant must cover. Each objective has:
- id: a short uppercase identifier (OBJ1, OBJ2, ...)
- objective: one sentence phrased as an outcome (not a question)
- success_criteria: one or two sentences describing what evidence in the
  conversation would mark this objective as covered

Aim for three to six objectives. Stay grounded in the briefing; do not invent.
Skip meta-instructions to the consultant (time budget, tone, opening style).
Focus on the substantive content the conversation must surface.
"""


def extract_objectives(briefing_markdown: str, model: str = "gpt-5-mini") -> list[Objective]:
    client = OpenAI()
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": briefing_markdown},
        ],
        text_format=_ObjectivesPayload,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("objectives extraction returned no parsed output")
    return parsed.objectives
