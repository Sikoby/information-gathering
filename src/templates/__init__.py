"""Meeting template library.

A Template declares the structural shape of a meeting: the notebook sections
the agent fills, and the phases the conversation moves through. The briefing
selects a template via front-matter or extractor inference.
"""

from __future__ import annotations

from .eval import EVAL_TEMPLATE
from .generic import GENERIC_TEMPLATE
from .requirements import REQUIREMENTS_TEMPLATE
from .research import RESEARCH_TEMPLATE
from .schema import NotebookSection, Phase, Template

TEMPLATES: dict[str, Template] = {
    REQUIREMENTS_TEMPLATE.name: REQUIREMENTS_TEMPLATE,
    RESEARCH_TEMPLATE.name: RESEARCH_TEMPLATE,
    EVAL_TEMPLATE.name: EVAL_TEMPLATE,
    GENERIC_TEMPLATE.name: GENERIC_TEMPLATE,
}


__all__ = [
    "NotebookSection",
    "Phase",
    "Template",
    "TEMPLATES",
]
