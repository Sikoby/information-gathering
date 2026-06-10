"""Background finding extractor.

The voice tool `record_finding` is fire-and-forget: it drops a one-string `RawNote`
on a queue and returns instantly, so the realtime model never blocks on JSON it has
to stream or a Redis round trip. This module's single worker drains that queue, calls
gpt-5-mini **off the event loop** to turn each raw note into a structured, *terse*
`ExtractedFinding`, and inserts it into the live `MeetingState` tree — a few seconds
after the agent has already moved on.

Isolated on purpose: this is the first step toward the future supervisor container that
subscribes to `events:*` (see the root CLAUDE.md). Keep the OpenAI call and the tree
insert here so they can move out cleanly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger
from openai import OpenAI
from pydantic import BaseModel, Field

from . import meeting
from .templates import (
    OTHER_QUESTION_ID,
    Section,
    SectionKind,
    children_of,
    enclosing_phase,
    section_by_id,
)

if TYPE_CHECKING:
    from .harness import MeetingState

_EXTRACT_MODEL = "gpt-5-mini"


@dataclass
class RawNote:
    """A note captured verbatim by the voice tool, awaiting structuring."""

    note: str
    section_id: str
    user_turn: int = 0
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractedFinding(BaseModel):
    section_id: str = Field(
        description=(
            "Id of the single best-matching QUESTION from the candidate list. "
            "Use 'other/q' if none clearly fits."
        )
    )
    header: str = Field(description="A few-word noun phrase naming the finding.")
    body: str = Field(
        description=(
            "One or two dense, telegraphic sentences. Facts, numbers, names, dates, "
            "decisions only — no filler, adjectives, or conversational framing."
        )
    )


_SYSTEM_PROMPT = """\
You file a meeting note into a structured notebook in real time.

You are given (1) a raw note the interviewer jotted while talking and (2) the list of
QUESTION slots it could belong to. Produce a structured finding:

- section_id: the id of the single best-matching QUESTION from the list. Prefer a slot in
  the CURRENT AREA when it fits. If nothing fits, use "other/q".
- header: a few-word noun phrase naming the finding.
- body: one or two DENSE sentences. Strip filler, adjectives, hedging, and conversational
  framing — keep only facts, numbers, names, dates, and decisions. Write a terse,
  information-complete note, not prose.

Be lossless on substance: drop words, never facts. Never invent anything that is not in
the raw note.
"""


# ---- shared placement logic (also the verbatim fallback path) ----


def insert_finding(
    state: "MeetingState", section_id: str, header: str, body: str
) -> Section:
    """Append an ANSWER under the given QUESTION, routing unknown/non-QUESTION ids
    to the fallback question. Returns the created Section."""
    parent = section_by_id(state.sections, section_id)
    if parent is None or parent.kind != SectionKind.QUESTION:
        logger.warning(
            "insert_finding: section_id {!r} is not a QUESTION; routing to {!r}",
            section_id,
            OTHER_QUESTION_ID,
        )
        section_id = OTHER_QUESTION_ID
        parent = section_by_id(state.sections, section_id)
    assert parent is not None  # auto-appended by the Template validator

    existing_answers = [
        s for s in children_of(state.sections, parent.id) if s.kind == SectionKind.ANSWER
    ]
    n = len(existing_answers) + 1
    while any(s.id == f"{parent.id}/a{n}" for s in existing_answers):
        n += 1
    answer_id = f"{parent.id}/a{n}"

    section = Section(
        id=answer_id,
        parent_id=parent.id,
        kind=SectionKind.ANSWER,
        header=header,
        body=body,
        ts=datetime.now(timezone.utc),
    )
    state.sections.append(section)
    return section


def _candidate_questions(state: "MeetingState", current_section_id: str) -> str:
    """One line per QUESTION slot, marking those in the current phase."""
    cur_phase = enclosing_phase(state.sections, current_section_id)
    lines: list[str] = []
    for s in state.sections:
        if s.kind != SectionKind.QUESTION:
            continue
        phase = enclosing_phase(state.sections, s.id)
        topic = section_by_id(state.sections, s.parent_id) if s.parent_id else None
        topic_h = topic.header if topic is not None else "?"
        in_current = (
            cur_phase is not None and phase is not None and phase.id == cur_phase.id
        )
        marker = "  (CURRENT AREA)" if in_current else ""
        lines.append(f"- {s.id}: {s.header} [topic: {topic_h}]{marker}")
    return "\n".join(lines)


def _verbatim_header(note: str) -> str:
    words = note.split()
    head = " ".join(words[:8])
    return head + ("…" if len(words) > 8 else "")


# ---- worker ----


def _extract_sync(client: OpenAI, raw: RawNote, questions: str) -> ExtractedFinding:
    resp = client.responses.parse(
        model=_EXTRACT_MODEL,
        input=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"RAW NOTE:\n{raw.note}\n\n"
                    f"CANDIDATE QUESTIONS:\n{questions}"
                ),
            },
        ],
        text_format=ExtractedFinding,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise RuntimeError("extractor returned no parsed output")
    return parsed


async def _file_note(state: "MeetingState", client: OpenAI, raw: RawNote) -> None:
    questions = _candidate_questions(state, raw.section_id)
    parsed = await asyncio.to_thread(_extract_sync, client, raw, questions)
    insert_finding(state, parsed.section_id, parsed.header, parsed.body)
    await meeting.publish(state)
    logger.info(
        "finding filed under {}: {} | {}", parsed.section_id, parsed.header, parsed.body
    )


async def run_extractor(state: "MeetingState") -> None:
    """Drain the note queue forever, filing each note into the tree.

    A single worker → ordered inserts, one in-flight API call, and the tree mutation
    runs in this event loop *after* the await, so it never races the voice-model tools.
    """
    queue = state._note_queue
    assert queue is not None, "run_extractor started without a note queue"
    client = OpenAI()
    logger.info("note extractor started")
    while True:
        raw = await queue.get()
        try:
            await _file_note(state, client, raw)
        except Exception as e:
            # Never lose a finding: file the raw note verbatim under the fallback.
            logger.exception("extractor failed for note {!r}: {}", raw.note, e)
            try:
                insert_finding(
                    state, OTHER_QUESTION_ID, _verbatim_header(raw.note), raw.note
                )
                await meeting.publish(state)
            except Exception:
                logger.exception("extractor verbatim fallback also failed")
        finally:
            queue.task_done()
