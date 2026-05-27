"""Background task: reconcile template generation + meeting lifecycle.

Runs every CONSOLE_RECONCILE_INTERVAL seconds under a Redis leader lock (so
only one replica does the work per tick). Two passes:

  1. Meeting Running -> Done. Reads the agent's `state:<run_id>` snapshot;
     when it carries an `end_reason`, the meeting is finished. If no
     snapshot ever appears, a grace window catches a crashed dispatch/agent
     and a 24h ceiling catches a SIGKILLed agent whose snapshot TTL'd out.
  2. Reap stale template generations. A template stuck `generating` long
     past the generation timeout means the replica that owned the job
     died — flip it to `failed`.

All transitions go through the atomic Lua merge, so the pass is idempotent
even if two replicas briefly race.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from loguru import logger

from . import registry
from .models import MeetingRecord, TemplateRecord


_LEADER_KEY = "console:reconcile:leader"
_GENERATION_STALE_MINUTES = 10
_STATE_CEILING_HOURS = 24


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def run_loop(stop: asyncio.Event) -> None:
    interval = int(os.environ.get("CONSOLE_RECONCILE_INTERVAL", "15"))
    while not stop.is_set():
        try:
            if await registry.try_acquire_leader(_LEADER_KEY, interval):
                await _reconcile_once()
        except Exception:  # noqa: BLE001 - never let the loop die
            logger.exception("reconcile pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def _reconcile_once() -> None:
    grace_min = int(os.environ.get("CONSOLE_STARTUP_GRACE_MIN", "5"))
    now = datetime.now(timezone.utc)
    for rec in await registry.list_all():
        if rec.status == "running":
            await _reconcile_running(rec, now, grace_min)
    for tmpl in await registry.list_templates():
        if tmpl.template_status == "generating":
            await _reap_stale_generation(tmpl, now)


async def _reconcile_running(
    rec: MeetingRecord, now: datetime, grace_min: int
) -> None:
    if not rec.run_id:
        return
    snapshot = await registry.get_run_state(rec.run_id)
    if snapshot is not None:
        end_reason = snapshot.get("end_reason")
        if end_reason:
            await registry.update(
                rec.meeting_id,
                status="done",
                end_reason=end_reason,
                ended_at=snapshot.get("ended_at") or now.isoformat(),
            )
        return

    # No snapshot in Redis yet.
    if not rec.dispatched_at:
        return
    dispatched = _parse_iso(rec.dispatched_at)
    if now - dispatched > timedelta(hours=_STATE_CEILING_HOURS):
        await registry.update(
            rec.meeting_id,
            status="done",
            end_reason="unknown_state_expired",
            ended_at=now.isoformat(),
        )
    elif now - dispatched > timedelta(minutes=grace_min):
        await registry.update(
            rec.meeting_id,
            status="done",
            end_reason="agent_never_started",
            ended_at=now.isoformat(),
        )


async def _reap_stale_generation(rec: TemplateRecord, now: datetime) -> None:
    updated = _parse_iso(rec.updated_at)
    if now - updated > timedelta(minutes=_GENERATION_STALE_MINUTES):
        logger.warning("reaping stale generation template_id={}", rec.template_id)
        await registry.update_template_if_seq(
            rec.template_id,
            rec.generation_seq,
            template_status="failed",
            template_error="generation did not complete (worker restarted?)",
        )
