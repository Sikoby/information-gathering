"""CLI: extract objectives from a briefing markdown file (offline).

Usage:
    python scripts/extract_objectives.py briefings/01_dwh_requirements.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.objectives import extract_objectives


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("briefing", type=Path)
    parser.add_argument("--model", default="gpt-5-mini")
    args = parser.parse_args()

    briefing_md = args.briefing.read_text()
    objectives = extract_objectives(briefing_md, model=args.model)
    print(json.dumps([o.model_dump() for o in objectives], indent=2))


if __name__ == "__main__":
    main()
