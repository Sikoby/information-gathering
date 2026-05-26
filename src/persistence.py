"""Per-run file IO. No LiveKit dependencies."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .harness import MeetingState
from .templates import SectionKind, enclosing_phase


class Persistence:
    """Owns the out/<run_id>/ directory and writes session artifacts."""

    def __init__(self, run_id: str, out_root: Path | str = "out") -> None:
        self.run_id = run_id
        self.run_dir = Path(out_root) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def briefing_path(self) -> Path:
        return self.run_dir / "briefing.md"

    def write_briefing_inline(self, briefing_markdown: str) -> None:
        self.briefing_path.write_text(briefing_markdown)

    def append_transcript(self, role: str, text: str) -> None:
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "text": text,
        }
        with (self.run_dir / "transcript.jsonl").open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def flush_state(self, state: MeetingState, model_name: str = "gpt-realtime") -> None:
        # 1. Canonical: the full Section tree.
        tree = [s.model_dump(mode="json") for s in state.sections]
        (self.run_dir / "tree.json").write_text(json.dumps(tree, indent=2))

        # 2. Chronological transitions.
        transitions = [t.model_dump(mode="json") for t in state.transitions]
        (self.run_dir / "transitions.json").write_text(json.dumps(transitions, indent=2))

        # 3. Derived back-compat view over ANSWER nodes, keyed by parent QUESTION id.
        notebook: dict[str, list[dict]] = defaultdict(list)
        for s in state.sections:
            if s.kind != SectionKind.ANSWER:
                continue
            assert s.parent_id is not None
            notebook[s.parent_id].append(
                {
                    "header": s.header,
                    "body": s.body,
                    "ts": s.ts.isoformat() if s.ts else None,
                }
            )
        (self.run_dir / "notebook.json").write_text(json.dumps(dict(notebook), indent=2))

        # 4. Followups (unchanged shape).
        followups = [f.model_dump(mode="json") for f in state.followups]
        (self.run_dir / "followups.json").write_text(json.dumps(followups, indent=2))

        # 5. Meta — drops tracker, adds tree-position fields.
        cur_phase = enclosing_phase(state.sections, state.current_section_id)
        meta = {
            "run_id": state.run_id,
            "briefing_path": state.briefing_path,
            "target_minutes": state.target_minutes,
            "model": model_name,
            "template": state.template.name,
            "current_section_id": state.current_section_id,
            "current_phase_id": cur_phase.id if cur_phase is not None else None,
            "visited_section_ids": list(state.visited_section_ids),
            "started_at": state.started_at.isoformat(),
            "ended_at": state.ended_at.isoformat() if state.ended_at else None,
            "end_reason": state.end_reason,
            "user_turn_count": state.user_turn_count,
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
