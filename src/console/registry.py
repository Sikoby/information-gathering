"""Redis-backed registries for templates and meetings.

Stateless across console replicas: every record update goes through an atomic
Lua compare-and-swap merge, so concurrent writers (the PATCH handler, the
generation task, the reconcile loop, any replica) never clobber each other.

Storage layout:
  template:<template_id>      string (JSON) — the TemplateRecord, no TTL
  templates:index             sorted set — global, members=template_id, score=created epoch
  templates:owner:<email>     sorted set — per-user, same shape as templates:index
  meeting:<meeting_id>        string (JSON) — the MeetingRecord, no TTL
  meetings:index              sorted set — global, members=meeting_id, score=created epoch
  meetings:owner:<email>      sorted set — per-user, same shape as meetings:index
  console:reconcile:leader    short-TTL string — reconcile-loop leader lock

The global indexes back the reconcile loop (which sweeps every running
meeting / generating template). The per-user indexes back the user-facing
list endpoints. Both are written on create and cleaned on delete; the merge
script only mutates the record string.

Templates store `template` (the Template body) and `document_outline` as
embedded JSON *strings* — the Lua merge decodes and re-encodes the whole
record on every write, and cjson collapses empty nested arrays to `{}`,
which would corrupt the section tree and the slide list.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from loguru import logger
from pydantic import BaseModel

from .models import MeetingRecord, TemplateRecord


_MEETING_PREFIX = "meeting:"
_MEETINGS_INDEX_KEY = "meetings:index"
_MEETINGS_OWNER_PREFIX = "meetings:owner:"
_TEMPLATE_PREFIX = "template:"
_TEMPLATES_INDEX_KEY = "templates:index"
_TEMPLATES_OWNER_PREFIX = "templates:owner:"

_MEETING_JSON_STRING_FIELDS: tuple[str, ...] = ()
_TEMPLATE_JSON_STRING_FIELDS: tuple[str, ...] = ("template", "document_outline")

_redis: aioredis.Redis | None = None
_merge_script: aioredis.client.AsyncScript | None = None


# Atomic field merge. KEYS[1]=record key. ARGV[1]=JSON of fields to merge,
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


def template_key(template_id: str) -> str:
    return f"{_TEMPLATE_PREFIX}{template_id}"


def _meetings_owner_key(owner_email: str) -> str:
    return f"{_MEETINGS_OWNER_PREFIX}{owner_email}"


def _templates_owner_key(owner_email: str) -> str:
    return f"{_TEMPLATES_OWNER_PREFIX}{owner_email}"


def new_meeting_id() -> str:
    return "meeting-" + uuid.uuid4().hex


def new_template_id() -> str:
    return "template-" + uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_for_storage(rec: BaseModel, json_string_fields: tuple[str, ...]) -> str:
    data = rec.model_dump(mode="json")
    for f in json_string_fields:
        if data.get(f) is not None:
            data[f] = json.dumps(data[f])
    return json.dumps(data)


def _load_from_storage(
    raw: str,
    model: type[BaseModel],
    json_string_fields: tuple[str, ...],
):
    data = json.loads(raw)
    for f in json_string_fields:
        if isinstance(data.get(f), str):
            data[f] = json.loads(data[f])
    return model.model_validate(data)


async def _merge(
    key: str,
    fields: dict,
    expected_seq: int | None,
    *,
    json_string_fields: tuple[str, ...] = (),
) -> bool:
    fields = dict(fields)
    for f in json_string_fields:
        v = fields.get(f)
        if v is not None and not isinstance(v, str):
            fields[f] = json.dumps(v)
    result = await _get_merge_script()(
        keys=[key],
        args=[
            json.dumps(fields),
            now_iso(),
            "" if expected_seq is None else str(expected_seq),
        ],
    )
    return result == 1


# ---------------------------------------------------------------- meetings


async def create(rec: MeetingRecord) -> None:
    client = get_client()
    score = time.time()
    async with client.pipeline(transaction=True) as pipe:
        pipe.set(
            meeting_key(rec.meeting_id),
            _dump_for_storage(rec, _MEETING_JSON_STRING_FIELDS),
        )
        pipe.zadd(_MEETINGS_INDEX_KEY, {rec.meeting_id: score})
        pipe.zadd(_meetings_owner_key(rec.owner_email), {rec.meeting_id: score})
        await pipe.execute()


async def get(meeting_id: str) -> MeetingRecord | None:
    raw = await get_client().get(meeting_key(meeting_id))
    if raw is None:
        return None
    return _load_from_storage(raw, MeetingRecord, _MEETING_JSON_STRING_FIELDS)


async def _load_meetings_by_ids(ids: list[str]) -> list[MeetingRecord]:
    if not ids:
        return []
    raws = await get_client().mget([meeting_key(mid) for mid in ids])
    out: list[MeetingRecord] = []
    for raw in raws:
        if raw is None:
            continue
        try:
            out.append(
                _load_from_storage(raw, MeetingRecord, _MEETING_JSON_STRING_FIELDS)
            )
        except Exception as e:  # noqa: BLE001 - skip a single bad record
            logger.warning("skipping unparseable meeting record: {}", e)
    return out


async def list_all(limit: int = 200) -> list[MeetingRecord]:
    """Global newest-first listing. Used by the reconcile loop."""
    ids = await get_client().zrevrange(_MEETINGS_INDEX_KEY, 0, limit - 1)
    return await _load_meetings_by_ids(ids)


async def list_meetings_by_owner(
    owner_email: str, limit: int = 200
) -> list[MeetingRecord]:
    ids = await get_client().zrevrange(
        _meetings_owner_key(owner_email), 0, limit - 1
    )
    return await _load_meetings_by_ids(ids)


async def delete(meeting_id: str) -> None:
    rec = await get(meeting_id)
    client = get_client()
    async with client.pipeline(transaction=True) as pipe:
        pipe.delete(meeting_key(meeting_id))
        pipe.zrem(_MEETINGS_INDEX_KEY, meeting_id)
        if rec is not None:
            pipe.zrem(_meetings_owner_key(rec.owner_email), meeting_id)
        await pipe.execute()


async def update(meeting_id: str, **fields) -> bool:
    """Atomic field merge. Returns False if the meeting does not exist."""
    return await _merge(
        meeting_key(meeting_id),
        fields,
        expected_seq=None,
        json_string_fields=_MEETING_JSON_STRING_FIELDS,
    )


# ---------------------------------------------------------------- templates


async def create_template(rec: TemplateRecord) -> None:
    client = get_client()
    score = time.time()
    async with client.pipeline(transaction=True) as pipe:
        pipe.set(
            template_key(rec.template_id),
            _dump_for_storage(rec, _TEMPLATE_JSON_STRING_FIELDS),
        )
        pipe.zadd(_TEMPLATES_INDEX_KEY, {rec.template_id: score})
        pipe.zadd(_templates_owner_key(rec.owner_email), {rec.template_id: score})
        await pipe.execute()


async def get_template(template_id: str) -> TemplateRecord | None:
    raw = await get_client().get(template_key(template_id))
    if raw is None:
        return None
    return _load_from_storage(raw, TemplateRecord, _TEMPLATE_JSON_STRING_FIELDS)


async def _load_templates_by_ids(ids: list[str]) -> list[TemplateRecord]:
    if not ids:
        return []
    raws = await get_client().mget([template_key(tid) for tid in ids])
    out: list[TemplateRecord] = []
    for raw in raws:
        if raw is None:
            continue
        try:
            out.append(
                _load_from_storage(raw, TemplateRecord, _TEMPLATE_JSON_STRING_FIELDS)
            )
        except Exception as e:  # noqa: BLE001 - skip a single bad record
            logger.warning("skipping unparseable template record: {}", e)
    return out


async def list_templates(limit: int = 200) -> list[TemplateRecord]:
    """Global newest-first listing. Used by the reconcile loop."""
    ids = await get_client().zrevrange(_TEMPLATES_INDEX_KEY, 0, limit - 1)
    return await _load_templates_by_ids(ids)


async def list_templates_by_owner(
    owner_email: str, limit: int = 200
) -> list[TemplateRecord]:
    ids = await get_client().zrevrange(
        _templates_owner_key(owner_email), 0, limit - 1
    )
    return await _load_templates_by_ids(ids)


async def delete_template(template_id: str) -> None:
    rec = await get_template(template_id)
    client = get_client()
    async with client.pipeline(transaction=True) as pipe:
        pipe.delete(template_key(template_id))
        pipe.zrem(_TEMPLATES_INDEX_KEY, template_id)
        if rec is not None:
            pipe.zrem(_templates_owner_key(rec.owner_email), template_id)
        await pipe.execute()


async def update_template(template_id: str, **fields) -> bool:
    return await _merge(
        template_key(template_id),
        fields,
        expected_seq=None,
        json_string_fields=_TEMPLATE_JSON_STRING_FIELDS,
    )


async def update_template_if_seq(
    template_id: str, expected_seq: int, **fields
) -> bool:
    """Atomic field merge guarded by generation_seq. True iff applied."""
    return await _merge(
        template_key(template_id),
        fields,
        expected_seq=expected_seq,
        json_string_fields=_TEMPLATE_JSON_STRING_FIELDS,
    )


# ---------------------------------------------------------------- shared


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
