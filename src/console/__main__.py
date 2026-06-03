"""Meeting console API service. Run with `python -m src.console`.

Serves the `/api/*` JSON API consumed by the console-frontend SPA (which is a
separate nginx container that reverse-proxies `/api` here). Owns the Redis
`template:*` and `meeting:*` registries and runs the reconcile background
loop.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from loguru import logger

from . import auth, handlers, reconcile


async def _on_startup(app: web.Application) -> None:
    app["http_session"] = aiohttp.ClientSession()
    app["reconcile_stop"] = asyncio.Event()
    app["reconcile_task"] = asyncio.create_task(
        reconcile.run_loop(app["reconcile_stop"], app["http_session"])
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
    # 50 MB ceiling — accommodates PPTX uploads on /api/templates/upload.
    app = web.Application(
        client_max_size=50 * 1024 * 1024,
        middlewares=[auth.auth_middleware],
    )
    app.router.add_get("/api/me", handlers.get_me)
    app.router.add_post("/api/templates", handlers.post_templates)
    app.router.add_post("/api/templates/upload", handlers.post_templates_upload)
    app.router.add_get("/api/templates", handlers.get_templates)
    app.router.add_get("/api/templates/{template_id}", handlers.get_template)
    app.router.add_patch(
        "/api/templates/{template_id}", handlers.patch_template
    )
    app.router.add_post(
        "/api/templates/{template_id}/regenerate",
        handlers.post_template_regenerate,
    )
    app.router.add_delete(
        "/api/templates/{template_id}", handlers.delete_template
    )
    app.router.add_post(
        "/api/templates/{template_id}/meetings",
        handlers.post_template_start_meeting,
    )
    app.router.add_post(
        "/api/templates/{template_id}/scheduled-meetings",
        handlers.post_template_schedule_meeting,
    )
    app.router.add_get("/api/meetings", handlers.get_meetings)
    app.router.add_get("/api/meetings/{meeting_id}", handlers.get_meeting)
    app.router.add_get(
        "/api/meetings/{meeting_id}/invite.ics",
        handlers.get_meeting_invite_ics,
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
