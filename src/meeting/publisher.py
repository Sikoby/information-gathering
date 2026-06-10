"""Redis-backed state pub/sub for the per-meeting API.

The agent process writes `MeetingState` snapshots; the meeting API process reads
them. They never share Python objects — Redis is the only thing they share.

Public surface
==============
Agent-side writers (need MeetingState):
    publish(state)        — write latest snapshot + broadcast
    register(state)       — first publish + mark run active
    unregister(run_id)    — mark run inactive

API-side readers (no MeetingState import needed):
    get_state_json(run_id)  — latest snapshot, or None if unknown
    get_client()            — shared async Redis client
    events_channel(run_id)  — channel name for pub/sub
    state_key(run_id)       — key name for the snapshot
    ping()                  — connectivity check for /healthz

`MeetingState` is referenced only via TYPE_CHECKING so the meeting API container
can import this module without pulling pydantic/livekit/openai transitively.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from loguru import logger

if TYPE_CHECKING:
    from ..harness import MeetingState


_STATE_KEY_TTL_SECONDS = 24 * 3600
_RUNS_ACTIVE_KEY = "runs:active"


def state_key(run_id: str) -> str:
    return f"state:{run_id}"


def events_channel(run_id: str) -> str:
    return f"events:{run_id}"


_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _client = aioredis.from_url(url, decode_responses=True)
    return _client


def _snapshot_json(state: "MeetingState") -> str:
    snapshot = state.model_dump(mode="json")
    # Speaker notes are private cues for the agent. Redact them before the
    # viewer (or anyone with browser dev tools) sees the snapshot. Two copies
    # exist on MeetingState: the working `sections` list and the embedded
    # `template.sections` it was seeded from.
    for s in snapshot.get("sections", []):
        s["private_notes"] = None
    template = snapshot.get("template") or {}
    for s in template.get("sections", []):
        s["private_notes"] = None
    return json.dumps(snapshot)


async def publish(state: "MeetingState") -> None:
    """Broadcast the latest snapshot for `state.run_id`.

    Sets `state:<run_id>` (24h TTL) and publishes on `events:<run_id>`. Any
    Redis error is logged and swallowed — losing one publish must not crash
    the realtime agent.
    """
    snapshot = _snapshot_json(state)
    client = get_client()
    try:
        await client.set(state_key(state.run_id), snapshot, ex=_STATE_KEY_TTL_SECONDS)
        await client.publish(events_channel(state.run_id), snapshot)
    except Exception as e:
        logger.warning("publish failed for run_id={}: {}", state.run_id, e)


async def register(state: "MeetingState") -> None:
    """Mark a new run as active and publish its initial snapshot."""
    client = get_client()
    try:
        await client.sadd(_RUNS_ACTIVE_KEY, state.run_id)
    except Exception as e:
        logger.warning("sadd runs:active failed for run_id={}: {}", state.run_id, e)
    await publish(state)
    logger.info("registered run_id={}", state.run_id)


async def unregister(run_id: str) -> None:
    """Remove a run from `runs:active`. The snapshot key lives until its TTL."""
    try:
        await get_client().srem(_RUNS_ACTIVE_KEY, run_id)
    except Exception as e:
        logger.warning("srem runs:active failed for run_id={}: {}", run_id, e)


async def get_state_json(run_id: str) -> str | None:
    """Return the latest snapshot JSON, or None if no such run."""
    try:
        return await get_client().get(state_key(run_id))
    except Exception as e:
        logger.warning("get state failed for run_id={}: {}", run_id, e)
        return None


async def get_meeting_json(meeting_id: str) -> dict | None:
    """Return the console-owned `meeting:<id>` record as a dict, or None.

    The console is the writer/owner of `meeting:*`; the meeting API reads it
    (only) to drive the public join flow — analogous to the console reading the
    agent-owned `state:*`. Only plain scalar fields are consumed (status, room,
    join_pin, scheduled_at, title_override), so the embedded-JSON `invitees`
    string is left untouched.
    """
    try:
        raw = await get_client().get(f"meeting:{meeting_id}")
    except Exception as e:
        logger.warning("get meeting failed for meeting_id={}: {}", meeting_id, e)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def ping() -> bool:
    try:
        return bool(await get_client().ping())
    except Exception:
        return False
