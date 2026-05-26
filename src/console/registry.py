"""Redis-backed meeting registry.

Stateless across console replicas: every record update goes through an atomic
Lua compare-and-swap merge, so concurrent writers (the PATCH handler, the
generation task, the reconcile loop, any replica) never clobber each other.

Storage layout:
  meeting:<meeting_id>   string (JSON) — the MeetingRecord, no TTL
  meetings:index         sorted set — member=meeting_id, score=created epoch
  console:reconcile:leader  short-TTL string — reconcile-loop leader lock

The stored JSON keeps `template` as an embedded JSON *string* (not a nested
object) so the Lua merge — which decodes and re-encodes the whole record —
never round-trips template's nested arrays through cjson (which would corrupt
any empty arrays in the nested Section tree into `{}`).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from loguru import logger

from .models import MeetingRecord


_MEETING_PREFIX = "meeting:"
_INDEX_KEY = "meetings:index"

_redis: aioredis.Redis | None = None
_merge_script: aioredis.client.AsyncScript | None = None


# Atomic field merge. KEYS[1]=meeting key. ARGV[1]=JSON of fields to merge,
# ARGV[2]=updated_at, ARGV[3]=expected generation_seq ("" to skip the check).
# Returns 1 applied, 0 seq-mismatch, -1 missing.
_MERGE_LUA = """
local cur = redis.call('GET', KEYS[1])
if not cur then return -1 end
local rec = cjson.decode(cur)
if ARGV[3] ~= '' and tostring(rec['generation_seq']) ~= ARGV[3] then
    return 0
end
local patch = cjson.decode(ARGV[1])
for k, v in pairs(patch) do rec[k] = v end
rec['updated_at'] = ARGV[2]
redis.call('SET', KEYS[1], cjson.encode(rec))
return 1
"""


def get_client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis = aioredis.from_url(url, decode_responses=True)
    return _redis


def _get_merge_script() -> aioredis.client.AsyncScript:
    global _merge_script
    if _merge_script is None:
        _merge_script = get_client().register_script(_MERGE_LUA)
    return _merge_script


def meeting_key(meeting_id: str) -> str:
    return f"{_MEETING_PREFIX}{meeting_id}"


def new_meeting_id() -> str:
    return "meeting-" + uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_for_storage(rec: MeetingRecord) -> str:
    data = json.loads(rec.model_dump_json())
    if data.get("template") is not None:
        data["template"] = json.dumps(data["template"])
    return json.dumps(data)


def _load_from_storage(raw: str) -> MeetingRecord:
    data = json.loads(raw)
    if isinstance(data.get("template"), str):
        data["template"] = json.loads(data["template"])
    return MeetingRecord.model_validate(data)


async def create(rec: MeetingRecord) -> None:
    client = get_client()
    async with client.pipeline(transaction=True) as pipe:
        pipe.set(meeting_key(rec.meeting_id), _dump_for_storage(rec))
        pipe.zadd(_INDEX_KEY, {rec.meeting_id: time.time()})
        await pipe.execute()


async def get(meeting_id: str) -> MeetingRecord | None:
    raw = await get_client().get(meeting_key(meeting_id))
    if raw is None:
        return None
    return _load_from_storage(raw)


async def list_all(limit: int = 200) -> list[MeetingRecord]:
    client = get_client()
    ids = await client.zrevrange(_INDEX_KEY, 0, limit - 1)
    if not ids:
        return []
    raws = await client.mget([meeting_key(mid) for mid in ids])
    out: list[MeetingRecord] = []
    for raw in raws:
        if raw is None:
            continue
        try:
            out.append(_load_from_storage(raw))
        except Exception as e:  # noqa: BLE001 - skip a single bad record
            logger.warning("skipping unparseable meeting record: {}", e)
    return out


async def delete(meeting_id: str) -> None:
    client = get_client()
    async with client.pipeline(transaction=True) as pipe:
        pipe.delete(meeting_key(meeting_id))
        pipe.zrem(_INDEX_KEY, meeting_id)
        await pipe.execute()


async def update(meeting_id: str, **fields) -> bool:
    """Atomic field merge. Returns False if the meeting does not exist."""
    return await _merge(meeting_id, fields, expected_seq=None)


async def update_if_seq(meeting_id: str, expected_seq: int, **fields) -> bool:
    """Atomic field merge guarded by generation_seq. True iff applied."""
    return await _merge(meeting_id, fields, expected_seq=expected_seq)


async def _merge(meeting_id: str, fields: dict, expected_seq: int | None) -> bool:
    fields = dict(fields)
    tmpl = fields.get("template")
    if tmpl is not None and not isinstance(tmpl, str):
        fields["template"] = json.dumps(tmpl)
    result = await _get_merge_script()(
        keys=[meeting_key(meeting_id)],
        args=[
            json.dumps(fields),
            now_iso(),
            "" if expected_seq is None else str(expected_seq),
        ],
    )
    return result == 1


async def get_run_state(run_id: str) -> dict | None:
    """Read the agent's live MeetingState snapshot at `state:<run_id>`."""
    raw = await get_client().get(f"state:{run_id}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def try_acquire_leader(key: str, ttl_seconds: int) -> bool:
    """Best-effort leader lock for periodic work (SET NX EX)."""
    return bool(await get_client().set(key, "1", nx=True, ex=ttl_seconds))
