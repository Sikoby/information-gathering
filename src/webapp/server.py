"""aiohttp routes for the per-meeting read-only view.

The agent process writes meeting state to Redis; this server reads it.
There is no direct connection to the agent — every route is satisfied by
a Redis `GET` (for `/state`), a `SUBSCRIBE` (for `/events`), or a static
file from the bundled frontend (for `/<run_id>/` and `/assets/*`).

Routes:
- GET  /<run_id>/         → frontend/dist/index.html
- GET  /<run_id>/state    → JSON snapshot of MeetingState (from Redis)
- GET  /<run_id>/events   → SSE stream of MeetingState snapshots (Redis pub/sub)
- GET  /join/<id>         → public, PIN-gated join page for an invited meeting
- POST /join/<id>         → verify PIN, mint a token via dispatch, 302 into room
- GET  /healthz           → 200 if Redis ping succeeds, 503 otherwise
- GET  /assets/*          → Vite-built static assets
"""

from __future__ import annotations

import asyncio
import html
import os
from pathlib import Path

import aiohttp
from aiohttp import web
from loguru import logger

from . import publisher


_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_BUILD_MISSING_HTML = (
    "<!doctype html><html><body style='font-family: system-ui; padding: 2rem;'>"
    "<h1>Frontend build missing</h1>"
    "<p>Run <code>pnpm install &amp;&amp; pnpm build</code> in the "
    "<code>frontend/</code> directory, then refresh.</p>"
    "</body></html>"
)


async def _serve_index(request: web.Request) -> web.Response:
    run_id = request.match_info["run_id"]
    if await publisher.get_state_json(run_id) is None:
        return web.Response(status=404, text=f"unknown run_id: {run_id}")
    index = _FRONTEND_DIST / "index.html"
    if not index.exists():
        return web.Response(status=500, text=_BUILD_MISSING_HTML, content_type="text/html")
    return web.FileResponse(index)


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


def _join_page(message_html: str, *, status: int = 200) -> web.Response:
    """Wrap a fragment in the minimal join-page shell."""
    doc = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Join meeting</title><style>"
        "body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;"
        "display:flex;min-height:100vh;margin:0;align-items:center;justify-content:center}"
        ".card{background:#1e293b;padding:2.5rem;border-radius:12px;max-width:24rem;"
        "width:100%;box-shadow:0 10px 30px rgba(0,0,0,.4)}"
        "h1{font-size:1.25rem;margin:0 0 1rem}p{line-height:1.5;color:#94a3b8}"
        "input{width:100%;box-sizing:border-box;font-size:1.5rem;letter-spacing:.3em;"
        "text-align:center;padding:.6rem;margin:1rem 0;border-radius:8px;border:1px solid #334155;"
        "background:#0f172a;color:#e2e8f0}"
        "button{width:100%;padding:.7rem;font-size:1rem;border:0;border-radius:8px;"
        "background:#6366f1;color:#fff;cursor:pointer}button:hover{background:#4f46e5}"
        ".err{color:#f87171;margin:.5rem 0 0}"
        "</style></head><body><div class='card'>" + message_html + "</div></body></html>"
    )
    return web.Response(text=doc, content_type="text/html", status=status)


def _pin_form(meeting_id: str, *, error: str | None = None) -> web.Response:
    err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    body = (
        "<h1>Join the meeting</h1>"
        "<p>Enter the PIN from your invitation to enter the room.</p>"
        f"<form method='post' action='/join/{html.escape(meeting_id)}'>"
        "<input name='pin' inputmode='numeric' autocomplete='off' autofocus "
        "maxlength='6' placeholder='••••••'>"
        f"{err}<button type='submit'>Join</button></form>"
    )
    return _join_page(body)


def _not_ready_page(rec: dict) -> web.Response:
    status = rec.get("status")
    if status == "scheduled":
        when = rec.get("scheduled_at") or "the scheduled time"
        body = (
            "<h1>Not started yet</h1>"
            f"<p>This meeting starts at <strong>{html.escape(str(when))}</strong>. "
            "Open this link again at the start time to join.</p>"
        )
    elif status == "done":
        body = "<h1>Meeting ended</h1><p>This meeting has already finished.</p>"
    else:
        body = "<h1>Not available</h1><p>This meeting isn't open to join right now.</p>"
    return _join_page(body, status=200)


async def _serve_join(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    rec = await publisher.get_meeting_json(meeting_id)
    if rec is None:
        return _join_page("<h1>Not found</h1><p>Unknown meeting link.</p>", status=404)
    if rec.get("status") != "running" or not rec.get("room"):
        return _not_ready_page(rec)
    return _pin_form(meeting_id)


async def _post_join(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    rec = await publisher.get_meeting_json(meeting_id)
    if rec is None:
        return _join_page("<h1>Not found</h1><p>Unknown meeting link.</p>", status=404)
    if rec.get("status") != "running" or not rec.get("room"):
        return _not_ready_page(rec)

    form = await request.post()
    submitted = str(form.get("pin", "")).strip()
    expected = rec.get("join_pin")
    if not expected or submitted != expected:
        return _pin_form(meeting_id, error="Incorrect PIN. Please try again.")

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
        return _join_page(
            "<h1>Couldn't open the room</h1>"
            "<p>Something went wrong starting your session. Please try again.</p>",
            status=502,
        )
    raise web.HTTPFound(join_url)


async def _serve_healthz(_request: web.Request) -> web.Response:
    ok = await publisher.ping()
    return web.Response(status=200 if ok else 503, text="ok" if ok else "redis unreachable")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", _serve_healthz)
    app.router.add_get("/join/{meeting_id}", _serve_join)
    app.router.add_post("/join/{meeting_id}", _post_join)
    app.router.add_get("/{run_id}/", _serve_index)
    app.router.add_get("/{run_id}/state", _serve_state)
    app.router.add_get("/{run_id}/events", _serve_events)
    app.router.add_get("/favicon.ico", lambda _r: web.Response(status=404))

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.router.add_static("/assets/", assets_dir, show_index=False)
    return app
