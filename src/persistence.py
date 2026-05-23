"""Per-run file IO. No LiveKit dependencies.

Artifacts written per run under `out/<run_id>/`:
  - briefing.md           the raw briefing
  - tree.json             canonical: the full Section tree (template + runtime)
  - transitions.json      chronological navigate() events
  - followups.json        follow-up items
  - notebook.json         derived view: dict[parent_id, list[{header, body, ts}]]
                          (rebuilt from ANSWER nodes — for back-compat readers)
  - meta.json             run metadata (current_section_id, visited list, etc.)
  - transcript.jsonl      append-only chat lines (role, text, ts)
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .harness import MeetingState
from .templates import SectionKind


class Persistence:
    """Owns the out/<run_id>/ directory and writes session artifacts."""

    def __init__(self, run_id: str, out_root: Path | str = "out") -> None:
        self.run_id = run_id
        self.run_dir = Path(out_root) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def copy_briefing(self, briefing_path: str | Path) -> None:
        shutil.copy(briefing_path, self.run_dir / "briefing.md")

    def write_briefing_inline(self, briefing_markdown: str) -> None:
        (self.run_dir / "briefing.md").write_text(briefing_markdown)

    def append_transcript(self, role: str, text: str) -> None:
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "text": text,
        }
        with (self.run_dir / "transcript.jsonl").open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def flush_state(self, state: MeetingState, model_name: str = "gpt-realtime") -> None:
        tree = [s.model_dump(mode="json") for s in state.sections]
        transitions = [t.model_dump(mode="json") for t in state.transitions]
        followups = [f.model_dump(mode="json") for f in state.followups]

        # Derived notebook view: parent_id -> list of answers (header/body/ts).
        notebook: dict[str, list[dict]] = {}
        for s in state.sections:
            if s.kind == SectionKind.ANSWER and s.parent_id is not None:
                notebook.setdefault(s.parent_id, []).append(
                    {
                        "header": s.header,
                        "body": s.body,
                        "ts": s.ts.isoformat() if s.ts else None,
                    }
                )

        (self.run_dir / "tree.json").write_text(json.dumps(tree, indent=2))
        (self.run_dir / "transitions.json").write_text(json.dumps(transitions, indent=2))
        (self.run_dir / "followups.json").write_text(json.dumps(followups, indent=2))
        (self.run_dir / "notebook.json").write_text(json.dumps(notebook, indent=2))

        current_phase = state.enclosing_phase(state.current_section_id)
        meta = {
            "run_id": state.run_id,
            "briefing_path": state.briefing_path,
            "target_minutes": state.target_minutes,
            "model": model_name,
            "template": state.template.name,
            "current_section_id": state.current_section_id,
            "current_phase_id": current_phase.id if current_phase else None,
            "visited_section_ids": state.visited_section_ids,
            "started_at": state.started_at.isoformat(),
            "ended_at": state.ended_at.isoformat() if state.ended_at else None,
            "end_reason": state.end_reason,
            "user_turn_count": state.user_turn_count,
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
