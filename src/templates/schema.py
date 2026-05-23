"""Pydantic models for meeting templates — one tree, one Section type.

A meeting is a tree of `Section` nodes. Each node has a `kind` discriminator:

    meeting   the root; holds the BLUF (header) and SCQA (body)
    phase     owns a fraction of meeting time; has no PHASE ancestor
    topic     a branch / area of inquiry
    question  something to ask the stakeholder
    answer    a finding (the leaf — created at runtime via record_finding)
    closing   the pyramid wrap (created at runtime via deliver_pyramid_summary)

Templates declare the static structure (meeting → phases → topics → questions).
ANSWER and CLOSING nodes are created at runtime and live in `MeetingState.sections`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


ROOT_SECTION_ID = "_root"
OTHER_SECTION_ID = "other"
MAX_DEPTH = 5  # root(0) → phase(1) → topic(2) → question(3) → topic-under-q(4) → answer(5)


class SectionKind(str, Enum):
    MEETING = "meeting"
    PHASE = "phase"
    TOPIC = "topic"
    QUESTION = "question"
    ANSWER = "answer"
    CLOSING = "closing"


class Section(BaseModel):
    id: str
    parent_id: str | None = None
    kind: SectionKind = SectionKind.TOPIC

    # The two text fields. Meaning shifts by kind:
    #   meeting  → header = BLUF;                      body = SCQA framing
    #   phase    → header = phase headline (claim);    body = goal / what we do here
    #   topic    → header = topic claim;               body = optional context
    #   question → header = the question text;         body = optional context for the agent
    #   answer   → header = short finding headline;    body = full content (required)
    #   closing  → header = top conclusion;            body = supports + next actions
    header: str
    body: str | None = None

    # Whether this node accepts multiple ANSWER children. Meaningful for TOPIC / QUESTION.
    repeated: bool = True

    # PHASE only.
    target_fraction: float | None = Field(default=None, gt=0.0, le=1.0)
    opening_signpost: str | None = None
    closing_signpost: str | None = None

    # ANSWER only — set automatically by record_finding.
    ts: datetime | None = None


# -- Free tree-walk helpers (operate on any list[Section]) ----------------------


def section_by_id(sections: list[Section], sid: str) -> Section | None:
    for s in sections:
        if s.id == sid:
            return s
    return None


def children_of(sections: list[Section], sid: str) -> list[Section]:
    return [s for s in sections if s.parent_id == sid]


def children_of_kind(sections: list[Section], sid: str, kind: SectionKind) -> list[Section]:
    return [s for s in children_of(sections, sid) if s.kind == kind]


def descendants_of(sections: list[Section], sid: str) -> list[Section]:
    out: list[Section] = []
    stack = [sid]
    while stack:
        cur = stack.pop()
        for child in children_of(sections, cur):
            out.append(child)
            stack.append(child.id)
    return out


def answers_under(sections: list[Section], sid: str) -> list[Section]:
    return [s for s in descendants_of(sections, sid) if s.kind == SectionKind.ANSWER]


def path_to(sections: list[Section], sid: str) -> list[Section]:
    """Root-first chain to `sid`. Empty list if `sid` is unknown."""
    by_id = {s.id: s for s in sections}
    if sid not in by_id:
        return []
    chain: list[Section] = []
    cur: Section | None = by_id[sid]
    while cur is not None:
        chain.append(cur)
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    return list(reversed(chain))


def depth_of(sections: list[Section], sid: str) -> int:
    return max(0, len(path_to(sections, sid)) - 1)


def scheduled_nodes(sections: list[Section]) -> list[Section]:
    return [s for s in sections if s.kind == SectionKind.PHASE]


def enclosing_phase(sections: list[Section], sid: str) -> Section | None:
    chain = path_to(sections, sid)
    for s in reversed(chain):
        if s.kind == SectionKind.PHASE:
            return s
    return None


# -- Template (the declared spec) ----------------------------------------------


class Template(BaseModel):
    name: str
    description: str
    sections: list[Section]

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> "Template":
        # Auto-prepend the meeting root if missing.
        if not any(s.id == ROOT_SECTION_ID for s in self.sections):
            self.sections.insert(
                0,
                Section(
                    id=ROOT_SECTION_ID,
                    parent_id=None,
                    kind=SectionKind.MEETING,
                    header="Meeting",
                    body=None,
                    repeated=False,
                ),
            )

        # Auto-rewire any unparented node to the meeting root.
        for s in self.sections:
            if s.id != ROOT_SECTION_ID and s.parent_id is None:
                s.parent_id = ROOT_SECTION_ID

        # Auto-append a catch-all "other" topic under root if missing.
        if not any(s.id == OTHER_SECTION_ID for s in self.sections):
            self.sections.append(
                Section(
                    id=OTHER_SECTION_ID,
                    parent_id=ROOT_SECTION_ID,
                    kind=SectionKind.TOPIC,
                    header="Other",
                    body=(
                        "Anything material that doesn't fit a declared section. "
                        "Prefer declared sections; use this only when nothing else fits."
                    ),
                    repeated=True,
                ),
            )

        _validate_tree(self.sections)
        return self

    # Convenience methods (delegate to free helpers).
    def section_ids(self) -> list[str]:
        return [s.id for s in self.sections]

    def section_by_id(self, sid: str) -> Section | None:
        return section_by_id(self.sections, sid)

    def children_of(self, sid: str) -> list[Section]:
        return children_of(self.sections, sid)

    def children_of_kind(self, sid: str, kind: SectionKind) -> list[Section]:
        return children_of_kind(self.sections, sid, kind)

    def descendants_of(self, sid: str) -> list[Section]:
        return descendants_of(self.sections, sid)

    def path_to(self, sid: str) -> list[Section]:
        return path_to(self.sections, sid)

    def depth_of(self, sid: str) -> int:
        return depth_of(self.sections, sid)

    def scheduled_nodes(self) -> list[Section]:
        return scheduled_nodes(self.sections)

    def enclosing_phase(self, sid: str) -> Section | None:
        return enclosing_phase(self.sections, sid)


def _validate_tree(sections: list[Section]) -> None:
    """Run the kind-aware validation suite. Raises ValueError on any violation."""
    ids = [s.id for s in sections]
    dupes = sorted({sid for sid in ids if ids.count(sid) > 1})
    if dupes:
        raise ValueError(f"Duplicate section ids: {dupes}")
    id_set = set(ids)
    by_id = {s.id: s for s in sections}

    # parent_id resolves
    for s in sections:
        if s.parent_id is not None and s.parent_id not in id_set:
            raise ValueError(f"Section '{s.id}' has unknown parent_id '{s.parent_id}'")

    # Exactly one MEETING root, no parent
    meetings = [s for s in sections if s.kind == SectionKind.MEETING]
    if len(meetings) != 1:
        raise ValueError(f"Expected exactly one MEETING node; got {len(meetings)}")
    root = meetings[0]
    if root.id != ROOT_SECTION_ID:
        raise ValueError(f"MEETING node must have id '{ROOT_SECTION_ID}', got '{root.id}'")
    if root.parent_id is not None:
        raise ValueError("MEETING node must have no parent")

    # Cycle detection + depth cap
    for s in sections:
        seen = {s.id}
        cur = s
        depth = 0
        while cur.parent_id is not None:
            if cur.parent_id in seen:
                raise ValueError(f"Cycle detected involving section '{s.id}'")
            seen.add(cur.parent_id)
            cur = by_id[cur.parent_id]
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError(
                    f"Section '{s.id}' exceeds MAX_DEPTH={MAX_DEPTH}"
                )

    # Kind-aware parent constraints
    closing_count = 0
    for s in sections:
        if s.kind == SectionKind.PHASE:
            if s.target_fraction is None:
                raise ValueError(f"PHASE '{s.id}' must set target_fraction")
            cur = s
            while cur.parent_id is not None:
                cur = by_id[cur.parent_id]
                if cur.kind == SectionKind.PHASE:
                    raise ValueError(
                        f"PHASE '{s.id}' has PHASE ancestor '{cur.id}' (no nested phases)"
                    )
        elif s.kind == SectionKind.QUESTION:
            if s.parent_id is None:
                raise ValueError(f"QUESTION '{s.id}' must have a parent")
            parent = by_id[s.parent_id]
            if parent.kind not in (SectionKind.TOPIC, SectionKind.PHASE):
                raise ValueError(
                    f"QUESTION '{s.id}' parent must be TOPIC or PHASE (got {parent.kind})"
                )
        elif s.kind == SectionKind.ANSWER:
            if s.parent_id is None:
                raise ValueError(f"ANSWER '{s.id}' must have a parent")
            parent = by_id[s.parent_id]
            if parent.kind not in (SectionKind.TOPIC, SectionKind.QUESTION):
                raise ValueError(
                    f"ANSWER '{s.id}' parent must be TOPIC or QUESTION (got {parent.kind})"
                )
            if not s.body:
                raise ValueError(f"ANSWER '{s.id}' must have non-empty body")
        elif s.kind == SectionKind.CLOSING:
            if s.parent_id != ROOT_SECTION_ID:
                raise ValueError(f"CLOSING '{s.id}' parent must be the meeting root")
            closing_count += 1

    if closing_count > 1:
        raise ValueError(f"At most one CLOSING node allowed; got {closing_count}")

    # PHASE target_fractions sum to 1.0
    phases = [s for s in sections if s.kind == SectionKind.PHASE]
    if phases:
        total = sum(p.target_fraction or 0.0 for p in phases)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"PHASE target_fractions must sum to 1.0 (got {total:.6f})"
            )
