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
from src.templates import (
    CLOSING_SECTION_ID,
    ROOT_SECTION_ID,
    Section,
    SectionKind,
    TEMPLATES,
)
from src.webapp.publisher import register
from src.webapp.server import build_app


PORT = 8767
RUN_ID = "dev"


def _build_state() -> MeetingState:
    started = datetime.now(timezone.utc) - timedelta(minutes=7)
    template = TEMPLATES["requirements"]
    sections = new_state_sections(template)

    # Frame the meeting (what frame_meeting would have written).
    root = next(s for s in sections if s.id == ROOT_SECTION_ID)
    root.header = (
        "We need a phased migration off CSV exports to a region-pinned warehouse."
    )
    root.body = (
        "Situation: Analytics, finance, and product all build from manual CSV "
        "exports out of Salesforce and Stripe.\n\n"
        "Complication: Numbers diverge across teams; PII has to stay in the EU "
        "or compliance flags us."
    )

    # A few ANSWERs as if record_finding had been called.
    sections.extend(
        [
            Section(
                id="pain_points/q1/a1",
                parent_id="pain_points/q1",
                kind=SectionKind.ANSWER,
                header="Manual Monday CSV exports",
                body=(
                    "Analytics re-exports Salesforce + Stripe every Monday. "
                    "Two-hour manual process; data is stale by Wednesday."
                ),
                ts=started + timedelta(minutes=2),
            ),
            Section(
                id="pain_points/q1/a2",
                parent_id="pain_points/q1",
                kind=SectionKind.ANSWER,
                header="Revenue numbers diverge across teams",
                body=(
                    "Finance and product disagree on Q-end numbers because "
                    "they pull from different exports."
                ),
                ts=started + timedelta(minutes=3),
            ),
            Section(
                id="constraints/q2/a1",
                parent_id="constraints/q2",
                kind=SectionKind.ANSWER,
                header="GDPR for EU customer data",
                body=(
                    "Customer PII in Salesforce must remain region-pinned; "
                    "Frankfurt region warehouse on the table."
                ),
                ts=started + timedelta(minutes=4, seconds=30),
            ),
            Section(
                id="pain_points/severity/q1/a1",
                parent_id="pain_points/severity/q1",
                kind=SectionKind.ANSWER,
                header="Happens every week",
                body="The CSV process happens every Monday without fail.",
                ts=started + timedelta(minutes=5),
            ),
        ]
    )

    # A closing TOPIC as if deliver_pyramid_summary had been called once
    # (the synthetic state shows the post-summary look).
    sections.append(
        Section(
            id=CLOSING_SECTION_ID,
            parent_id=ROOT_SECTION_ID,
            kind=SectionKind.TOPIC,
            header="Recommend a phased Frankfurt warehouse landing finance first.",
            body=(
                "Supports:\n"
                "- Weekly CSV process is high-cost and high-risk for stale data.\n"
                "- GDPR forces region-pinned storage anyway.\n"
                "- Finance has the clearest single-source-of-truth pain.\n\n"
                "Next actions:\n"
                "- Send Stripe schema sample to data team\n"
                "- Confirm whether a SOC2 audit is underway"
            ),
            ts=started + timedelta(minutes=6, seconds=30),
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
            preview="We'll cover rapport, define, prioritise, and wrap.",
            ts=started,
        ),
        Transition(
            from_section_id="rapport",
            to_section_id="define",
            kind=TransitionKind.SIBLING,
            crossed_phase_boundary=True,
            recap="Stakeholders mapped; decision flow clear.",
            bridge=None,
            preview=None,
            ts=started + timedelta(minutes=1, seconds=45),
        ),
        Transition(
            from_section_id="define",
            to_section_id="pain_points",
            kind=TransitionKind.DRILL_DOWN,
            crossed_phase_boundary=False,
            recap=None,
            bridge=None,
            preview=None,
            ts=started + timedelta(minutes=2),
        ),
        Transition(
            from_section_id="pain_points",
            to_section_id="pain_points/severity",
            kind=TransitionKind.DRILL_DOWN,
            crossed_phase_boundary=False,
            recap=None,
            bridge=None,
            preview=None,
            ts=started + timedelta(minutes=4, seconds=45),
        ),
        Transition(
            from_section_id="pain_points/severity",
            to_section_id="pain_points",
            kind=TransitionKind.ZOOM_OUT,
            crossed_phase_boundary=False,
            recap="Pain is weekly and costs ~2 hours of analyst time.",
            bridge=None,
            preview=None,
            ts=started + timedelta(minutes=5, seconds=30),
        ),
    ]

    return MeetingState(
        run_id=RUN_ID,
        briefing_path="briefing.md",
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
        current_section_id="pain_points/q3",
        visited_section_ids=[
            "rapport",
            "stakeholders",
            "define",
            "pain_points",
            "pain_points/q1",
            "pain_points/severity",
            "pain_points/severity/q1",
            "pain_points/q3",
            "constraints",
            "constraints/q2",
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
    # Keep the loop alive
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    # Unused-import suppression for re-exports above
    _ = webapp
    asyncio.run(main())
