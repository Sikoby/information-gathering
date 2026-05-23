"""Meeting template library.

A Template declares the structural shape of a meeting: a tree of `Section`
nodes (meeting → phases → topics → questions). The briefing selects a template
via front-matter or extractor inference.
"""

from __future__ import annotations

from .eval import EVAL_TEMPLATE
from .generic import GENERIC_TEMPLATE
from .requirements import REQUIREMENTS_TEMPLATE
from .research import RESEARCH_TEMPLATE
from .schema import (
    OTHER_SECTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    Template,
)

TEMPLATES: dict[str, Template] = {
    REQUIREMENTS_TEMPLATE.name: REQUIREMENTS_TEMPLATE,
    RESEARCH_TEMPLATE.name: RESEARCH_TEMPLATE,
    EVAL_TEMPLATE.name: EVAL_TEMPLATE,
    GENERIC_TEMPLATE.name: GENERIC_TEMPLATE,
}


__all__ = [
    "OTHER_SECTION_ID",
    "ROOT_SECTION_ID",
    "Section",
    "SectionKind",
    "Template",
    "TEMPLATES",
]
