"""aiohttp JSON API for the meeting participant app.

The agent process writes meeting state to Redis; this server reads it. There is
no direct connection to the agent — every route is satisfied by a Redis `GET`
(for state), a `SUBSCRIBE` (for events), a read of the console-owned
`meeting:<id>` record (for the join flow), or one outbound call to dispatch
(to mint a voice-join token).

Static files and the SPA shell are served by the `meeting-frontend` nginx
container, not here. This service is data-only under `/api/*`.

Routes:
- GET  /api/runs/{run_id}/state    → JSON snapshot of MeetingState (from Redis)
- GET  /api/runs/{run_id}/events   → SSE stream of MeetingState snapshots
- GET  /api/join/{meeting_id}      → {status, scheduled_at, ready} (never leaks pin/room)
- POST /api/join/{meeting_id}/token → verify PIN, mint a token via dispatch, return {join_url}
- GET  /healthz                    → 200 if Redis ping succeeds, 503 otherwise
"""

from __future__ import annotations

import asyncio
import os

import aiohttp
from aiohttp import web
from loguru import logger

from . import publisher


async def _serve_state(request: web.Request) -> web.Response:
    run_id = request.match_info["run_id"]
    snapshot = await publisher.get_state_json(run_id)
    if snapshot is None:
        return web.Response(status=404, text=f"unknown run_id: {run_id}")
    return web.Response(body=snapshot, content_type="application/json")


async def _serve_events(request: web.Request) -> web.StreamResponse:
    run_id = request.match_info["run_id"]
    initial = await publisher.get_state_json(run_id)
    if initial is None:
        return web.Response(status=404, text=f"unknown run_id: {run_id}")

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)
    await response.write(f"data: {initial}\n\n".encode())

    pubsub = publisher.get_client().pubsub()
    channel = publisher.events_channel(run_id)
    await pubsub.subscribe(channel)
    logger.info("SSE subscriber connected run_id={}", run_id)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                await response.write(b": keepalive\n\n")
            elif msg.get("type") == "message":
                data = msg["data"]
                await response.write(f"data: {data}\n\n".encode())
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception as e:
            logger.warning("pubsub cleanup failed for run_id={}: {}", run_id, e)
        logger.info("SSE subscriber disconnected run_id={}", run_id)
    return response


def _dispatch_url() -> str:
    return os.environ.get("DISPATCH_URL", "http://dispatch:8766").rstrip("/")


def _is_ready(rec: dict) -> bool:
    return rec.get("status") == "running" and bool(rec.get("room"))


async def _serve_join(request: web.Request) -> web.Response:
    """Public join status. Never leaks `join_pin` or `room`."""
    meeting_id = request.match_info["meeting_id"]
    rec = await publisher.get_meeting_json(meeting_id)
    if rec is None:
        return web.json_response({"status": "not_found"}, status=404)
    return web.json_response(
        {
            "status": rec.get("status"),
            "scheduled_at": rec.get("scheduled_at"),
            "ready": _is_ready(rec),
        }
    )


async def _post_join_token(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    rec = await publisher.get_meeting_json(meeting_id)
    if rec is None:
        return web.json_response({"error": "Unknown meeting link."}, status=404)
    if not _is_ready(rec):
        return web.json_response({"error": "This meeting isn't open to join right now."}, status=409)

    try:
        body = await request.json()
    except Exception:
        body = {}
    submitted = str(body.get("pin", "")).strip()
    expected = rec.get("join_pin")
    if not expected or submitted != expected:
        return web.json_response({"error": "Incorrect PIN. Please try again."}, status=403)

    payload = {"room": rec["room"], "name": rec.get("title_override") or "Participant"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_dispatch_url()}/join-token",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                ok = resp.status == 200
    except Exception as e:  # noqa: BLE001 - dispatch unreachable / bad response
        logger.warning("join-token call failed for meeting_id={}: {}", meeting_id, e)
        ok, data = False, {}

    join_url = data.get("join_url") if ok else None
    if not join_url:
        return web.json_response(
            {"error": "Couldn't open the room. Please try again."}, status=502
        )
    return web.json_response({"join_url": join_url})


async def _serve_healthz(_request: web.Request) -> web.Response:
    ok = await publisher.ping()
    return web.Response(status=200 if ok else 503, text="ok" if ok else "redis unreachable")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", _serve_healthz)
    app.router.add_get("/api/runs/{run_id}/state", _serve_state)
    app.router.add_get("/api/runs/{run_id}/events", _serve_events)
    app.router.add_get("/api/join/{meeting_id}", _serve_join)
    app.router.add_post("/api/join/{meeting_id}/token", _post_join_token)
    return app
