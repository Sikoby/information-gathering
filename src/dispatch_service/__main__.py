"""Long-running dispatch HTTP service.

Creates a LiveKit room, mints a stakeholder token, and dispatches the agent
worker. The briefing is always passed inline as a raw markdown string
(`briefing_description`); there is no file-path input. An optional
`custom_template` (a Template JSON object) and an optional caller-supplied
`run_id` may also be passed.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

from aiohttp import web
from dotenv import load_dotenv
from livekit.api import (
    AccessToken,
    CreateAgentDispatchRequest,
    CreateRoomRequest,
    LiveKitAPI,
    VideoGrants,
)
from loguru import logger

import redis.asyncio as aioredis


AGENT_NAME = "briefing-agent"
_RUNS_ACTIVE_KEY = "runs:active"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required env var: {name}")
    return value


async def _dispatch(
    *,
    briefing_description: str,
    custom_template: dict | None,
    target_minutes: int,
    run_id: str | None,
) -> dict:
    livekit_url = _required_env("LIVEKIT_URL")
    api_key = _required_env("LIVEKIT_API_KEY")
    api_secret = _required_env("LIVEKIT_API_SECRET")

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    room_name = f"briefing-{run_id.lower().replace(':', '-')}"

    metadata: dict = {
        "run_id": run_id,
        "target_minutes": target_minutes,
        "briefing_description": briefing_description,
    }
    if custom_template is not None:
        metadata["custom_template"] = custom_template

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
    finally:
        await api.aclose()

    webapp_base = os.environ.get("WEBAPP_PUBLIC_URL", "http://localhost:8765")
    return {
        "run_id": run_id,
        "room": room_name,
        "target_minutes": target_minutes,
        "join_url": join_url,
        "webapp_url": f"{webapp_base}/{run_id}/",
    }


_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis = aioredis.from_url(url, decode_responses=True)
    return _redis


async def _post_dispatch(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON body"}, status=400)

    briefing_description = payload.get("briefing_description")
    target_minutes = payload.get("target_minutes")
    if not briefing_description or target_minutes is None:
        return web.json_response(
            {"error": "missing required fields: briefing_description, target_minutes"},
            status=400,
        )

    custom_template = payload.get("custom_template")
    if custom_template is not None and not isinstance(custom_template, dict):
        return web.json_response(
            {"error": "custom_template must be a JSON object"},
            status=400,
        )

    try:
        result = await _dispatch(
            briefing_description=str(briefing_description),
            custom_template=custom_template,
            target_minutes=int(target_minutes),
            run_id=payload.get("run_id"),
        )
    except (ValueError, TypeError) as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("dispatch failed")
        return web.json_response({"error": str(e)}, status=500)

    logger.info("dispatched run_id={} room={}", result["run_id"], result["room"])
    return web.json_response(result)


async def _get_runs(_request: web.Request) -> web.Response:
    try:
        members = await _get_redis().smembers(_RUNS_ACTIVE_KEY)
        return web.json_response({"active": sorted(members)})
    except Exception as e:
        logger.warning("smembers failed: {}", e)
        return web.json_response({"active": [], "error": str(e)}, status=503)


async def _get_healthz(_request: web.Request) -> web.Response:
    for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        if not os.environ.get(name):
            return web.Response(status=503, text=f"missing env var: {name}")
    return web.Response(status=200, text="ok")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/dispatch", _post_dispatch)
    app.router.add_get("/runs", _get_runs)
    app.router.add_get("/healthz", _get_healthz)
    return app


def main() -> None:
    load_dotenv()
    port = int(os.environ.get("DISPATCH_PORT", "8766"))
    web.run_app(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
