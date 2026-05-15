"""Dispatch a briefing-driven meeting agent into a fresh LiveKit room.

Generates a run_id, creates the room, mints a stakeholder access token,
prints the join URL, and dispatches the agent with JSON metadata
{briefing_path, run_id, target_minutes}.

Usage:
    python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from livekit.api import (
    AccessToken,
    CreateAgentDispatchRequest,
    CreateRoomRequest,
    LiveKitAPI,
    VideoGrants,
)


AGENT_NAME = "briefing-agent"


async def dispatch(briefing_path: Path, target_minutes: int) -> None:
    if not briefing_path.exists():
        raise FileNotFoundError(f"briefing not found: {briefing_path}")

    livekit_url = os.environ["LIVEKIT_URL"]
    api_key = os.environ["LIVEKIT_API_KEY"]
    api_secret = os.environ["LIVEKIT_API_SECRET"]

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    room_name = f"briefing-{run_id.lower().replace(':', '-')}"

    metadata = {
        "briefing_path": str(briefing_path.resolve()),
        "run_id": run_id,
        "target_minutes": target_minutes,
    }

    api = LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
    try:
        await api.room.create_room(CreateRoomRequest(
            name=room_name,
            empty_timeout=15 * 60,
            max_participants=4,
        ))

        token = (
            AccessToken(api_key, api_secret)
            .with_identity("stakeholder")
            .with_name("Stakeholder")
            .with_grants(VideoGrants(
                room=room_name,
                room_join=True,
                can_publish=True,
                can_subscribe=True,
            ))
            .with_ttl(timedelta(hours=2))
            .to_jwt()
        )

        join_url = "https://meet.livekit.io/custom?" + urllib.parse.urlencode({
            "liveKitUrl": livekit_url,
            "token": token,
        })

        await api.agent_dispatch.create_dispatch(CreateAgentDispatchRequest(
            agent_name=AGENT_NAME,
            room=room_name,
            metadata=json.dumps(metadata),
        ))

        print(f"run_id        {run_id}")
        print(f"room          {room_name}")
        print(f"briefing      {briefing_path}")
        print(f"target_min    {target_minutes}")
        print()
        print("Open this URL in a browser, allow mic, and join:")
        print(join_url)
    finally:
        await api.aclose()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", type=Path, required=True)
    parser.add_argument("--target-minutes", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(dispatch(args.briefing, args.target_minutes))


if __name__ == "__main__":
    main()
