"""Background task: reconcile template generation + meeting lifecycle.

Runs every CONSOLE_RECONCILE_INTERVAL seconds under a Redis leader lock (so
only one replica does the work per tick). Three passes:

  1. Scheduled -> Running. A meeting scheduled for a future time is dispatched
     here once its start time arrives — deferred so the short-lived LiveKit
     voice-join token is minted at start, not at schedule time. A due meeting
     is retired `schedule_missed` past a lateness ceiling.
  2. Meeting Running -> Done. Reads the agent's `state:<run_id>` snapshot;
     when it carries an `end_reason`, the meeting is finished. If no
     snapshot ever appears, a grace window catches a crashed dispatch/agent
     and a 24h ceiling catches a SIGKILLed agent whose snapshot TTL'd out.
  3. Reap stale template generations. A template stuck `generating` long
     past the generation timeout means the replica that owned the job
     died — flip it to `failed`.

All transitions go through the atomic Lua merge, so the pass is idempotent
even if two replicas briefly race.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import aiohttp
from loguru import logger

from . import clients, registry
from .models import MeetingRecord, TemplateRecord


_LEADER_KEY = "console:reconcile:leader"
_GENERATION_STALE_MINUTES = 10
_STATE_CEILING_HOURS = 24
_SCHEDULE_LATE_CEILING_HOURS = 6


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def run_loop(stop: asyncio.Event, session: aiohttp.ClientSession) -> None:
    interval = int(os.environ.get("CONSOLE_RECONCILE_INTERVAL", "15"))
    while not stop.is_set():
        try:
            if await registry.try_acquire_leader(_LEADER_KEY, interval):
                await _reconcile_once(session)
        except Exception:  # noqa: BLE001 - never let the loop die
            logger.exception("reconcile pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def _reconcile_once(session: aiohttp.ClientSession) -> None:
    grace_min = int(os.environ.get("CONSOLE_STARTUP_GRACE_MIN", "5"))
    ceiling_hours = int(
        os.environ.get(
            "CONSOLE_SCHEDULE_LATE_CEILING_HOURS", str(_SCHEDULE_LATE_CEILING_HOURS)
        )
    )
    now = datetime.now(timezone.utc)
    for rec in await registry.list_all():
        if rec.status == "running":
            await _reconcile_running(rec, now, grace_min)
        elif rec.status == "scheduled":
            await _reconcile_scheduled(session, rec, now, ceiling_hours)
    for tmpl in await registry.list_templates():
        if tmpl.template_status == "generating":
            await _reap_stale_generation(tmpl, now)


async def _reconcile_scheduled(
    session: aiohttp.ClientSession,
    rec: MeetingRecord,
    now: datetime,
    ceiling_hours: int,
) -> None:
    """Dispatch a scheduled meeting once its start time arrives.

    The LiveKit voice-join token is short-lived, so it is minted here (at
    start) rather than when the meeting was scheduled. A due meeting is
    retired `schedule_missed` if it stays overdue past the lateness ceiling
    (dispatch persistently failing).
    """
    if not rec.scheduled_at:
        return
    scheduled = _parse_iso(rec.scheduled_at)
    if scheduled > now:
        return  # not due yet

    if now - scheduled > timedelta(hours=ceiling_hours):
        logger.warning(
            "retiring overdue scheduled meeting_id={} ({}h+ late)",
            rec.meeting_id,
            ceiling_hours,
        )
        await registry.update(
            rec.meeting_id,
            status="done",
            end_reason="schedule_missed",
            ended_at=now.isoformat(),
        )
        return

    tmpl = await registry.get_template(rec.template_id)
    if tmpl is None or tmpl.template is None:
        # Template deleted or mid-regeneration — defer; the ceiling above
        # eventually retires the meeting if this never resolves.
        logger.warning(
            "scheduled meeting_id={} has no ready template (template_id={}); "
            "deferring",
            rec.meeting_id,
            rec.template_id,
        )
        return

    effective_title = rec.title_override or tmpl.title
    briefing = f"# {effective_title}\n\n{tmpl.source_prompt}"
    try:
        result = await clients.dispatch_meeting(
            session,
            run_id=rec.meeting_id,
            briefing_description=briefing,
            custom_template=tmpl.template,
            target_minutes=rec.target_minutes,
        )
    except Exception:  # noqa: BLE001 - retry next tick; ceiling bounds retries
        logger.exception(
            "deferred dispatch failed meeting_id={}; will retry", rec.meeting_id
        )
        return

    await registry.update(
        rec.meeting_id,
        status="running",
        run_id=result["run_id"],
        room=result.get("room"),
        join_url=result.get("join_url"),
        webapp_url=result.get("webapp_url"),
        dispatched_at=now.isoformat(),
    )
    logger.info(
        "deferred-dispatched scheduled meeting_id={} owner={} run_id={}",
        rec.meeting_id,
        rec.owner_email,
        result["run_id"],
    )


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
