"""aiohttp routes for the per-meeting read-only view.

The agent process writes meeting state to Redis; this server reads it.
There is no direct connection to the agent — every route is satisfied by
a Redis `GET` (for `/state`), a `SUBSCRIBE` (for `/events`), or a static
file from the bundled frontend (for `/<run_id>/` and `/assets/*`).

Routes:
- GET /<run_id>/         → frontend/dist/index.html
- GET /<run_id>/state    → JSON snapshot of MeetingState (from Redis)
- GET /<run_id>/events   → SSE stream of MeetingState snapshots (Redis pub/sub)
- GET /healthz           → 200 if Redis ping succeeds, 503 otherwise
- GET /assets/*          → Vite-built static assets
"""

from __future__ import annotations

import asyncio
from pathlib import Path

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


async def _serve_healthz(_request: web.Request) -> web.Response:
    ok = await publisher.ping()
    return web.Response(status=200 if ok else 503, text="ok" if ok else "redis unreachable")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", _serve_healthz)
    app.router.add_get("/{run_id}/", _serve_index)
    app.router.add_get("/{run_id}/state", _serve_state)
    app.router.add_get("/{run_id}/events", _serve_events)
    app.router.add_get("/favicon.ico", lambda _r: web.Response(status=404))

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.router.add_static("/assets/", assets_dir, show_index=False)
    return app
