"""Standalone dev server: serves the webapp with a synthetic MeetingState.

Used for previewing the frontend without running a real LiveKit session.
Opens at http://localhost:8767/dev/ (run_id="dev"). The root "/" redirects
to "/dev/" for convenience.

Requires Redis to be running locally (the webapp reads state from Redis).
Easiest: `docker compose up -d redis` from the repo root before launching
this script, or `docker run --rm -p 6379:6379 redis:7-alpine`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python scripts/preview_dev_server.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp import web

from src import webapp
from src.harness import (
    Followup,
    MeetingState,
    Transition,
    TransitionKind,
    new_state_sections,
)
from src.templates import ROOT_SECTION_ID, Section, SectionKind, TEMPLATES
from src.webapp.publisher import register
from src.webapp.server import build_app


PORT = 8767
RUN_ID = "dev"


def _build_state() -> MeetingState:
    started = datetime.now(timezone.utc) - timedelta(minutes=7)
    template = TEMPLATES["requirements"]
    sections = new_state_sections(template)

    # Frame the meeting (as if frame_meeting had been called).
    root = next(s for s in sections if s.id == ROOT_SECTION_ID)
    root.header = (
        "Build a single source of truth for revenue and a daily-refreshed "
        "warehouse before the EOY budget freeze."
    )
    root.body = (
        "Situation: Sales, Finance, and Product each pull metrics from "
        "different CSV exports — numbers disagree by ~5%.\n\n"
        "Complication: A SOC2 audit lands in Q1 and PII residency for EU "
        "customers must be handled before then."
    )

    # Simulate a few recorded answers (created by record_finding).
    def _ans(parent_id: str, header: str, body: str, minutes_in: float) -> Section:
        return Section(
            id=f"{parent_id}/a1",
            parent_id=parent_id,
            kind=SectionKind.ANSWER,
            header=header,
            body=body,
            ts=started + timedelta(minutes=minutes_in),
        )

    sections.append(
        _ans(
            "pain_points/q_symptom",
            "Mobile lag",
            "Sales team reports 60% mobile demand; lag pushes them to competitors.",
            2.0,
        )
    )
    sections.append(
        _ans(
            "pain_points/q_cost",
            "Two-hour Monday loss",
            "Analytics team re-exports every Monday morning; data stale by Wednesday.",
            4.0,
        )
    )
    sections.append(
        _ans(
            "constraints/q_source",
            "GDPR for EU customer data",
            "Customer PII in Salesforce must remain region-pinned; considering a Frankfurt warehouse.",
            5.5,
        )
    )

    transitions = [
        Transition(
            from_section_id=ROOT_SECTION_ID,
            to_section_id="rapport",
            kind=TransitionKind.OPEN,
            crossed_phase_boundary=True,
            recap=None,
            bridge=None,
            preview="Set the room before digging in.",
            ts=started,
        ),
        Transition(
            from_section_id="rapport",
            to_section_id="define",
            kind=TransitionKind.SIBLING,
            crossed_phase_boundary=True,
            recap="Rapport done — they're ready.",
            preview="Pin down concrete pain.",
            bridge=None,
            ts=started + timedelta(minutes=1, seconds=30),
        ),
        Transition(
            from_section_id="define",
            to_section_id="pain_points",
            kind=TransitionKind.DRILL_DOWN,
            crossed_phase_boundary=False,
            recap=None,
            bridge=None,
            preview="What hurts today and how much.",
            ts=started + timedelta(minutes=1, seconds=45),
        ),
        Transition(
            from_section_id="pain_points",
            to_section_id="pain_points/q_symptom",
            kind=TransitionKind.DRILL_DOWN,
            crossed_phase_boundary=False,
            recap=None,
            bridge=None,
            preview=None,
            ts=started + timedelta(minutes=2),
        ),
        Transition(
            from_section_id="pain_points/q_symptom",
            to_section_id="pain_points/q_cost",
            kind=TransitionKind.SIBLING,
            crossed_phase_boundary=False,
            recap="Captured mobile lag as the headline pain.",
            preview=None,
            bridge=None,
            ts=started + timedelta(minutes=3),
        ),
    ]

    return MeetingState(
        run_id=RUN_ID,
        briefing_path="briefings/01_dwh_requirements.md",
        target_minutes=30,
        started_at=started,
        briefing_markdown=(
            "# Briefing: Data Warehouse Requirements Interview\n\n"
            "Conduct a data warehouse requirements interview covering:\n"
            "- Source systems (which apps, which databases, which APIs)\n"
            "- Data volumes (rough TB, growth rate)\n"
            "- Refresh frequency expectations per domain\n"
            "- BI tools currently in use\n"
            "- Cloud provider preferences and constraints\n"
            "- Compliance (GDPR, SOC2, industry-specific)\n\n"
            "Aim for 30 minutes. End with a confirmation of the top three priorities."
        ),
        template=template,
        sections=sections,
        current_section_id="pain_points/q_cost",
        visited_section_ids=[
            ROOT_SECTION_ID,
            "rapport",
            "define",
            "pain_points",
            "pain_points/q_symptom",
            "pain_points/q_cost",
        ],
        transitions=transitions,
        followups=[
            Followup(
                item="Send Stripe schema sample to data team",
                kind="action",
                ts=started + timedelta(minutes=3),
            ),
            Followup(
                item="Do they have a SOC2 audit underway?",
                kind="open_question",
                ts=started + timedelta(minutes=5),
            ),
        ],
        user_turn_count=12,
    )


async def _redirect_root(_request: web.Request) -> web.Response:
    raise web.HTTPFound(f"/{RUN_ID}/")


async def main() -> None:
    state = _build_state()
    await register(state)

    app = build_app()
    app.router.add_get("/", _redirect_root)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"preview dev server listening on http://localhost:{PORT}/")
    print(f"navigate to http://localhost:{PORT}/{RUN_ID}/")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    _ = webapp
    asyncio.run(main())
