"""Background task: generate a meeting template via the template-generator.

Spawned by the template create and regenerate handlers. The handler returns
immediately; this task runs the 1-4 minute impl+critique loop and writes the
result back into the template record under a generation_seq guard.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp
from loguru import logger

from . import clients, registry


# Keep references so tasks are not garbage-collected mid-flight.
_tasks: set[asyncio.Task] = set()


def spawn(session: aiohttp.ClientSession, template_id: str, seq: int) -> None:
    task = asyncio.create_task(_run(session, template_id, seq))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run(session: aiohttp.ClientSession, template_id: str, seq: int) -> None:
    rec = await registry.get_template(template_id)
    if rec is None or rec.generation_seq != seq:
        return
    logger.info("generation start template_id={} seq={}", template_id, seq)
    try:
        max_iter = int(os.environ.get("CONSOLE_GEN_MAX_ITERATIONS", "3"))
        result = await clients.generate_template(
            session,
            description=f"{rec.title}\n\n{rec.source_prompt}",
            reference_template=rec.reference_template,
            max_iterations=max_iter,
            document_outline=rec.document_outline,
        )
    except Exception as e:  # noqa: BLE001 - any failure marks the record failed
        logger.exception("generation failed template_id={}", template_id)
        await registry.update_template_if_seq(
            template_id,
            seq,
            template_status="failed",
            template_error=str(e),
        )
        return

    applied = await registry.update_template_if_seq(
        template_id,
        seq,
        template=result["template"],
        template_status="ready",
        template_error=None,
        template_approved=result.get("approved"),
        template_iterations_used=result.get("iterations_used"),
    )
    if applied:
        logger.info("generation done template_id={} seq={}", template_id, seq)
    else:
        logger.info(
            "generation result discarded — stale seq template_id={}", template_id
        )
