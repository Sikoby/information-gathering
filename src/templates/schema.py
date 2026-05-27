"""Pydantic models for meeting templates and runtime sections.

The meeting model is a single tree of `Section` nodes discriminated by `kind`.
The notebook *is* the tree:

    root (MEETING)
    ├─ TOPIC                ──── scheduled (has target_fraction): a "phase"
    │   ├─ TOPIC            ──── nested topic (no target_fraction)
    │   │   └─ QUESTION
    │   │       └─ ANSWER   ──── runtime, created by record_finding
    │   └─ QUESTION
    │       └─ ANSWER
    └─ TOPIC                ──── non-scheduled top-level (e.g. "other", closing)
        └─ QUESTION
            └─ ANSWER

A "phase" is just a top-level TOPIC with `target_fraction` set. The pyramid
wrap-up is just a top-level TOPIC with the well-known id `_root/closing`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


ROOT_SECTION_ID = "_root"
OTHER_SECTION_ID = "other"
OTHER_QUESTION_ID = "other/q"
CLOSING_SECTION_ID = "_root/closing"
MAX_DEPTH = 5


class SectionKind(str, Enum):
    MEETING = "meeting"
    TOPIC = "topic"
    QUESTION = "question"
    ANSWER = "answer"


class Section(BaseModel):
    id: str
    parent_id: str | None = None
    kind: SectionKind = SectionKind.TOPIC
    header: str
    body: str | None = None
    private_notes: str | None = None
    target_fraction: float | None = Field(default=None, gt=0.0, le=1.0)
    opening_signpost: str | None = None
    closing_signpost: str | None = None
    ts: datetime | None = None


# ---- free tree helpers (also imported by harness, tools, persistence, tests) ----


def section_by_id(sections: list[Section], sid: str) -> Section | None:
    for s in sections:
        if s.id == sid:
            return s
    return None


def children_of(sections: list[Section], sid: str) -> list[Section]:
    return [s for s in sections if s.parent_id == sid]


def children_of_kind(
    sections: list[Section], sid: str, kind: SectionKind
) -> list[Section]:
    return [s for s in sections if s.parent_id == sid and s.kind == kind]


def descendants_of(sections: list[Section], sid: str) -> list[Section]:
    out: list[Section] = []
    frontier = [sid]
    while frontier:
        pid = frontier.pop()
        for s in sections:
            if s.parent_id == pid:
                out.append(s)
                frontier.append(s.id)
    return out


def answers_under(sections: list[Section], sid: str) -> list[Section]:
    return [s for s in descendants_of(sections, sid) if s.kind == SectionKind.ANSWER]


def path_to(sections: list[Section], sid: str) -> list[Section]:
    """Root → node list, inclusive. Empty if sid is unknown."""
    by_id = {s.id: s for s in sections}
    if sid not in by_id:
        return []
    chain: list[Section] = []
    cur: Section | None = by_id[sid]
    while cur is not None:
        chain.append(cur)
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    chain.reverse()
    return chain


def depth_of(sections: list[Section], sid: str) -> int:
    """Root has depth 0; its children depth 1; etc. -1 if unknown."""
    p = path_to(sections, sid)
    return len(p) - 1 if p else -1


def is_scheduled(section: Section) -> bool:
    return section.kind == SectionKind.TOPIC and section.target_fraction is not None


def scheduled_nodes(sections: list[Section]) -> list[Section]:
    """Top-level scheduled TOPICs in declared order."""
    return [
        s
        for s in sections
        if s.parent_id == ROOT_SECTION_ID and is_scheduled(s)
    ]


def enclosing_phase(sections: list[Section], sid: str) -> Section | None:
    """Walk up to the first scheduled TOPIC. None if there is none on the path."""
    for s in reversed(path_to(sections, sid)):
        if is_scheduled(s):
            return s
    return None


# ---- Template ----


class Template(BaseModel):
    name: str
    description: str
    sections: list[Section]

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> "Template":
        sections = self.sections

        # 1. Auto-prepend root if missing.
        if not any(s.id == ROOT_SECTION_ID for s in sections):
            sections.insert(
                0,
                Section(
                    id=ROOT_SECTION_ID,
                    parent_id=None,
                    kind=SectionKind.MEETING,
                    header="Meeting",
                ),
            )

        # 2. Auto-rewire non-root sections with parent_id=None → "_root".
        for s in sections:
            if s.id != ROOT_SECTION_ID and s.parent_id is None:
                s.parent_id = ROOT_SECTION_ID

        # 3. Auto-append "other" TOPIC + its child "other/q" QUESTION if missing.
        if not any(s.id == OTHER_SECTION_ID for s in sections):
            sections.append(
                Section(
                    id=OTHER_SECTION_ID,
                    parent_id=ROOT_SECTION_ID,
                    kind=SectionKind.TOPIC,
                    header="Other",
                    body=(
                        "Findings that don't fit declared structure. "
                        "Prefer the declared topics; use this only when nothing else fits."
                    ),
                )
            )
        if not any(s.id == OTHER_QUESTION_ID for s in sections):
            sections.append(
                Section(
                    id=OTHER_QUESTION_ID,
                    parent_id=OTHER_SECTION_ID,
                    kind=SectionKind.QUESTION,
                    header="Anything else worth capturing?",
                )
            )

        # 4. Validate the tree.
        _validate_tree(sections)
        return self


def _validate_tree(sections: list[Section]) -> None:
    # Unique ids.
    seen: set[str] = set()
    for s in sections:
        if s.id in seen:
            raise ValueError(f"duplicate section id: {s.id!r}")
        seen.add(s.id)

    by_id = {s.id: s for s in sections}

    # parent_id resolves; exactly one MEETING; MEETING has no parent.
    meetings = [s for s in sections if s.kind == SectionKind.MEETING]
    if len(meetings) != 1:
        raise ValueError(f"expected exactly one MEETING section, got {len(meetings)}")
    root = meetings[0]
    if root.id != ROOT_SECTION_ID:
        raise ValueError(
            f"MEETING section must have id {ROOT_SECTION_ID!r}, got {root.id!r}"
        )
    if root.parent_id is not None:
        raise ValueError("MEETING section must have parent_id=None")

    for s in sections:
        if s.id == ROOT_SECTION_ID:
            continue
        if s.parent_id is None:
            raise ValueError(f"section {s.id!r} has no parent_id")
        if s.parent_id not in by_id:
            raise ValueError(
                f"section {s.id!r} parent_id {s.parent_id!r} does not resolve"
            )

    # No cycles + depth cap.
    for s in sections:
        chain: list[str] = []
        cur: Section | None = s
        while cur is not None:
            if cur.id in chain:
                raise ValueError(f"cycle detected through section {s.id!r}")
            chain.append(cur.id)
            if len(chain) > MAX_DEPTH + 1:
                raise ValueError(
                    f"section {s.id!r} exceeds MAX_DEPTH={MAX_DEPTH} "
                    f"(chain length {len(chain)})"
                )
            cur = by_id.get(cur.parent_id) if cur.parent_id else None

    # Parent-kind rules.
    for s in sections:
        if s.id == ROOT_SECTION_ID:
            continue
        parent = by_id[s.parent_id]  # type: ignore[index]
        if parent.kind == SectionKind.MEETING and s.kind != SectionKind.TOPIC:
            raise ValueError(
                f"section {s.id!r} ({s.kind}): MEETING children must be TOPIC"
            )
        if parent.kind == SectionKind.TOPIC and s.kind not in (
            SectionKind.TOPIC,
            SectionKind.QUESTION,
        ):
            raise ValueError(
                f"section {s.id!r} ({s.kind}): TOPIC children must be TOPIC or QUESTION"
            )
        if parent.kind == SectionKind.QUESTION and s.kind != SectionKind.ANSWER:
            raise ValueError(
                f"section {s.id!r} ({s.kind}): QUESTION children must be ANSWER"
            )
        if parent.kind == SectionKind.ANSWER:
            raise ValueError(
                f"section {s.id!r}: ANSWER sections cannot have children"
            )
        if s.kind == SectionKind.ANSWER and not (s.body and s.body.strip()):
            raise ValueError(
                f"ANSWER section {s.id!r}: body must be non-empty"
            )

    # target_fraction rules — only on TOPIC, only top-level, no scheduled ancestor.
    for s in sections:
        if s.target_fraction is None:
            continue
        if s.kind != SectionKind.TOPIC:
            raise ValueError(
                f"section {s.id!r}: target_fraction only allowed on TOPIC sections"
            )
        if s.parent_id != ROOT_SECTION_ID:
            raise ValueError(
                f"section {s.id!r}: scheduled TOPICs must be direct children of root "
                f"(got parent_id={s.parent_id!r})"
            )

    # Sum of scheduled top-level TOPICs ≈ 1.0.
    sched = [s for s in sections if s.parent_id == ROOT_SECTION_ID and is_scheduled(s)]
    if sched:
        total = sum(s.target_fraction or 0.0 for s in sched)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"scheduled TOPICs target_fraction sum {total:.6f} != 1.0"
            )


# Public re-exports — the helpers above are the canonical place for tree walks.
__all__ = [
    "ROOT_SECTION_ID",
    "OTHER_SECTION_ID",
    "OTHER_QUESTION_ID",
    "CLOSING_SECTION_ID",
    "MAX_DEPTH",
    "SectionKind",
    "Section",
    "Template",
    "section_by_id",
    "children_of",
    "children_of_kind",
    "descendants_of",
    "answers_under",
    "path_to",
    "depth_of",
    "is_scheduled",
    "scheduled_nodes",
    "enclosing_phase",
]
