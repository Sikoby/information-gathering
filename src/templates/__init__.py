"""Meeting template library.

A Template declares the structural shape of a meeting as a tree of `Section`
nodes (one MEETING root, scheduled top-level TOPICs for phases, nested TOPICs,
QUESTIONs the agent will work through). ANSWERs and the closing TOPIC are
added at runtime. The briefing selects a template via front-matter or extractor
inference.
"""

from __future__ import annotations

from .eval import EVAL_TEMPLATE
from .generic import GENERIC_TEMPLATE
from .requirements import REQUIREMENTS_TEMPLATE
from .research import RESEARCH_TEMPLATE
from .schema import (
    CLOSING_SECTION_ID,
    MAX_DEPTH,
    OTHER_QUESTION_ID,
    OTHER_SECTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    Template,
    children_of,
    children_of_kind,
    depth_of,
    descendants_of,
    enclosing_phase,
    is_scheduled,
    path_to,
    scheduled_nodes,
    section_by_id,
)

TEMPLATES: dict[str, Template] = {
    REQUIREMENTS_TEMPLATE.name: REQUIREMENTS_TEMPLATE,
    RESEARCH_TEMPLATE.name: RESEARCH_TEMPLATE,
    EVAL_TEMPLATE.name: EVAL_TEMPLATE,
    GENERIC_TEMPLATE.name: GENERIC_TEMPLATE,
}


__all__ = [
    "ROOT_SECTION_ID",
    "OTHER_SECTION_ID",
    "OTHER_QUESTION_ID",
    "CLOSING_SECTION_ID",
    "MAX_DEPTH",
    "Section",
    "SectionKind",
    "Template",
    "TEMPLATES",
    "section_by_id",
    "children_of",
    "children_of_kind",
    "descendants_of",
    "path_to",
    "depth_of",
    "is_scheduled",
    "scheduled_nodes",
    "enclosing_phase",
]
