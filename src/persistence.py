"""Per-run file IO. No LiveKit dependencies."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .harness import MeetingState, Objective


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

    def write_objectives(self, objectives: list[Objective]) -> None:
        data = [o.model_dump() for o in objectives]
        (self.run_dir / "objectives.json").write_text(json.dumps(data, indent=2))

    def append_transcript(self, role: str, text: str) -> None:
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "text": text,
        }
        with (self.run_dir / "transcript.jsonl").open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def flush_state(self, state: MeetingState, model_name: str = "gpt-realtime") -> None:
        findings = [f.model_dump(mode="json") for f in state.findings]
        followups = [f.model_dump(mode="json") for f in state.followups]
        tracker = {k: v.model_dump() for k, v in state.tracker.items()}

        (self.run_dir / "findings.json").write_text(json.dumps(findings, indent=2))
        (self.run_dir / "followups.json").write_text(json.dumps(followups, indent=2))

        meta = {
            "run_id": state.run_id,
            "briefing_path": state.briefing_path,
            "target_minutes": state.target_minutes,
            "model": model_name,
            "started_at": state.started_at.isoformat(),
            "ended_at": state.ended_at.isoformat() if state.ended_at else None,
            "end_reason": state.end_reason,
            "user_turn_count": state.user_turn_count,
            "tracker": tracker,
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
