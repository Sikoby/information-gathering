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
    NotebookEntry,
    ObjectiveStatus,
    Objective,
    PhaseTransition,
)
from src.templates import TEMPLATES
from src.webapp.publisher import register
from src.webapp.server import build_app


PORT = 8767
RUN_ID = "dev"


def _build_state() -> MeetingState:
    started = datetime.now(timezone.utc) - timedelta(minutes=7)
    objectives = [
        Objective(
            id="OBJ1",
            objective="Map upstream source systems",
            success_criteria="Names of the 3-5 systems the warehouse must ingest.",
        ),
        Objective(
            id="OBJ2",
            objective="Identify compliance constraints",
            success_criteria="GDPR / SOC2 / industry-specific requirements named.",
        ),
        Objective(
            id="OBJ3",
            objective="Confirm cloud preference",
            success_criteria="A specific cloud or 'no preference' clearly stated.",
        ),
        Objective(
            id="OBJ4",
            objective="Surface BI tool landscape",
            success_criteria="Current BI tools and any planned migrations listed.",
        ),
    ]
    tracker = {o.id: ObjectiveStatus() for o in objectives}
    tracker["OBJ1"].status = "covered"
    tracker["OBJ1"].note = "Salesforce, Stripe, internal Postgres for orders"
    tracker["OBJ2"].status = "partial"
    tracker["OBJ2"].note = "Confirmed GDPR; SOC2 unclear"
    tracker["OBJ3"].status = "open"

    template = TEMPLATES["requirements"]
    notebook: dict[str, list[NotebookEntry]] = {}
    notebook["pain_points"] = [
        NotebookEntry(
            title="Manual CSV exports from Salesforce",
            content=(
                "Analytics team currently re-exports every Monday morning. "
                "Two-hour manual process; data is stale by Wednesday."
            ),
            objective_ids=["OBJ1"],
            ts=started + timedelta(minutes=2),
        ),
        NotebookEntry(
            title="No single source of truth for revenue",
            content=(
                "Finance and product disagree on Q-end numbers because they "
                "pull from different exports."
            ),
            objective_ids=["OBJ1", "OBJ4"],
            ts=started + timedelta(minutes=4, seconds=20),
        ),
    ]
    notebook["constraints"] = [
        NotebookEntry(
            title="GDPR for EU customer data",
            content=(
                "Customer PII in Salesforce must remain region-pinned. "
                "Considering a Frankfurt region warehouse."
            ),
            objective_ids=["OBJ2"],
            ts=started + timedelta(minutes=5, seconds=10),
        ),
    ]
    notebook["must_haves"] = [
        NotebookEntry(
            title="Daily refresh of revenue domain",
            content="Finance needs revenue numbers refreshed by 9 AM each weekday.",
            objective_ids=[],
            ts=started + timedelta(minutes=6),
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
        objectives=objectives,
        tracker=tracker,
        template=template,
        notebook=notebook,
        current_phase="define",
        phase_history=[
            PhaseTransition(
                phase_id="rapport",
                note="",
                ts=started,
            ),
            PhaseTransition(
                phase_id="define",
                note="Stakeholder ready, moving to substance",
                ts=started + timedelta(minutes=1, seconds=45),
            ),
        ],
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
