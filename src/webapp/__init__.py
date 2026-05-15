"""Per-meeting read-only webapp.

Public surface used by agent.py and tools.py:
- start_server(port) → idempotently start the aiohttp server task
- register(state)     → register a meeting state for broadcast
- publish(state)      → broadcast the latest state to SSE subscribers
- unregister(run_id)  → drop a meeting (optional)
"""

from __future__ import annotations

import asyncio

from aiohttp import web
from loguru import logger

from .publisher import StatePublisher, get_publisher, publish, register, unregister
from .server import build_app

__all__ = [
    "StatePublisher",
    "get_publisher",
    "publish",
    "register",
    "start_server",
    "unregister",
]


_server_started = False


def start_server(port: int) -> asyncio.Task | None:
    """Start the aiohttp server once per process.

    Idempotent: subsequent calls return None. Safe to call from `entrypoint()`
    which runs once per meeting.
    """
    global _server_started
    if _server_started:
        return None
    _server_started = True

    app = build_app()

    async def _runner() -> None:
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("webapp server listening on :{}", port)
        # Park forever; runner stays alive with the event loop.
        while True:
            await asyncio.sleep(3600)

    return asyncio.create_task(_runner())
