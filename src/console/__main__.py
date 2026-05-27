"""Meeting console API service. Run with `python -m src.console`.

Serves the `/api/*` JSON API consumed by the console-frontend SPA (which is a
separate nginx container that reverse-proxies `/api` here). Owns the Redis
`meeting:*` registry and runs the reconcile background loop.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from loguru import logger

from . import handlers, reconcile


async def _on_startup(app: web.Application) -> None:
    app["http_session"] = aiohttp.ClientSession()
    app["reconcile_stop"] = asyncio.Event()
    app["reconcile_task"] = asyncio.create_task(
        reconcile.run_loop(app["reconcile_stop"])
    )
    logger.info("console started")


async def _on_cleanup(app: web.Application) -> None:
    stop: asyncio.Event = app.get("reconcile_stop")
    if stop is not None:
        stop.set()
    task: asyncio.Task | None = app.get("reconcile_task")
    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
    session: aiohttp.ClientSession | None = app.get("http_session")
    if session is not None:
        await session.close()
    logger.info("console stopped")


def build_app() -> web.Application:
    # 50 MB ceiling — accommodates PPTX uploads on /api/meetings/upload.
    app = web.Application(client_max_size=50 * 1024 * 1024)
    app.router.add_post("/api/meetings", handlers.post_meetings)
    app.router.add_post("/api/meetings/upload", handlers.post_meetings_upload)
    app.router.add_get("/api/meetings", handlers.get_meetings)
    app.router.add_get("/api/meetings/{meeting_id}", handlers.get_meeting)
    app.router.add_patch("/api/meetings/{meeting_id}", handlers.patch_meeting)
    app.router.add_post(
        "/api/meetings/{meeting_id}/start", handlers.post_start
    )
    app.router.add_post(
        "/api/meetings/{meeting_id}/regenerate", handlers.post_regenerate
    )
    app.router.add_delete(
        "/api/meetings/{meeting_id}", handlers.delete_meeting
    )
    app.router.add_get(
        "/api/reference-templates", handlers.get_reference_templates
    )
    app.router.add_get("/healthz", handlers.get_healthz)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def main() -> None:
    load_dotenv()
    port = int(os.environ.get("CONSOLE_PORT", "8770"))
    logger.info("meeting console starting on :{}", port)
    web.run_app(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
