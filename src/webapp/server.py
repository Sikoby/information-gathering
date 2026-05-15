"""aiohttp routes for the per-meeting read-only view.

Routes:
- GET /<run_id>/         → frontend/dist/index.html
- GET /<run_id>/state    → JSON snapshot of MeetingState
- GET /<run_id>/events   → SSE stream of MeetingState snapshots
- GET /assets/*          → Vite-built static assets
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web
from loguru import logger

from .publisher import get_publisher


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
    if get_publisher(run_id) is None:
        return web.Response(status=404, text=f"unknown run_id: {run_id}")
    index = _FRONTEND_DIST / "index.html"
    if not index.exists():
        return web.Response(status=500, text=_BUILD_MISSING_HTML, content_type="text/html")
    return web.FileResponse(index)


async def _serve_state(request: web.Request) -> web.Response:
    run_id = request.match_info["run_id"]
    pub = get_publisher(run_id)
    if pub is None:
        return web.Response(status=404, text=f"unknown run_id: {run_id}")
    return web.json_response(pub.state.model_dump(mode="json"))


async def _serve_events(request: web.Request) -> web.StreamResponse:
    run_id = request.match_info["run_id"]
    pub = get_publisher(run_id)
    if pub is None:
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
    queue = pub.subscribe()
    logger.info("SSE subscriber connected run_id={}", run_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                await response.write(f"data: {msg}\n\n".encode())
            except asyncio.TimeoutError:
                await response.write(b": keepalive\n\n")
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        pub.unsubscribe(queue)
        logger.info("SSE subscriber disconnected run_id={}", run_id)
    return response


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/{run_id}/", _serve_index)
    app.router.add_get("/{run_id}/state", _serve_state)
    app.router.add_get("/{run_id}/events", _serve_events)
    app.router.add_get("/favicon.ico", lambda _r: web.Response(status=404))

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.router.add_static("/assets/", assets_dir, show_index=False)
    return app
