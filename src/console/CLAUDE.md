# CLAUDE.md — console container (`src/console/`)

> **Rule of the house:** any substantial change to the console's endpoints, [Dockerfile.console](../../Dockerfile.console), entry point, environment variables, dependencies, the Redis registry layout, or the background tasks MUST update this CLAUDE.md in the same commit. If you change the request/response shape or the meeting lifecycle, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

A long-running aiohttp **API service** — the orchestrator and state-owner for meetings. It owns the Redis `meeting:*` registry, drives template generation, starts meetings, and tracks the **Planned → Running → Done** lifecycle.

It serves a JSON API only — no HTML. The console SPA is a separate [`console-frontend`](../../console-frontend/) nginx container that reverse-proxies `/api` here.

The console **never imports agent code** (`harness`, `briefing_plan`, `tools`, livekit, openai). It reads `state:<run_id>` as opaque JSON, exactly like the webapp. `src/templates` is imported only for the `Template` Pydantic schema (used to validate edited templates).

## Stateless and horizontally scalable

There are no in-process locks and no replica cap. Every record update is an **atomic Redis Lua compare-and-swap merge** ([registry.py](registry.py)); the reconcile loop runs under a `SET NX EX` leader lock so only one replica works per tick. `docker compose up --scale console=N` is safe.

## File map

```
src/console/
  __init__.py     module marker / doc only.
  __main__.py     build_app(), main(), on_startup/on_cleanup task wiring.
  models.py       Pydantic: MeetingRecord, MeetingCreate, MeetingPatch, ...
  registry.py     Redis meeting:* helpers + the atomic Lua merge.
  clients.py      async HTTP clients for dispatch + template-generator.
  generation.py   background template-generation task.
  reconcile.py    background lifecycle-reconciliation task (leader-locked).
  handlers.py     /api/* + /healthz handlers.
```

## Endpoints

| Route | Behavior |
| --- | --- |
| `POST /api/meetings` | Body `MeetingCreate`. Creates a `planned` record, spawns the generation task, returns `201` immediately. |
| `POST /api/meetings/upload` | Multipart: `file` (.pptx/.pdf) + `title`, `prompt`, `reference_template?`, `target_minutes?`. Forwards the file to template-generator's `/extract`, stores the resulting `DocumentOutline` on the record (`document_outline`/`document_filename`/`document_kind`), then spawns generation in presentation mode. `201`. `502` if extraction fails. |
| `GET /api/meetings` | `{meetings: [...]}`, newest first. |
| `GET /api/meetings/{id}` | The poll endpoint. `200` / `404`. |
| `PATCH /api/meetings/{id}` | Edit title / prompt / template / target_minutes. `409` unless `planned`; `400` on an invalid template. |
| `POST /api/meetings/{id}/start` | Calls dispatch; `200` running. `409` unless `planned`; `424` if the template is not `ready`; `502` if dispatch fails. |
| `POST /api/meetings/{id}/regenerate` | Bumps `generation_seq`, re-runs generation (the stored `document_outline` is passed through, so document-driven regenerations don't need re-upload). `202`. |
| `DELETE /api/meetings/{id}` | `204`. `409` if `running`. |
| `GET /api/reference-templates` | The four built-in templates, for the create form. |
| `GET /healthz` | `200` iff Redis ping succeeds. |

`client_max_size` is **50 MB** so PPTX uploads pass through.

## Redis keys

| Key | Type | Notes |
| --- | --- | --- |
| `meeting:<meeting_id>` | string (JSON) | the `MeetingRecord`. `template` is stored as an embedded JSON *string* so the Lua merge never round-trips its nested arrays through cjson. When the meeting was created via `/upload`, the record also carries `document_filename`, `document_kind` (`pptx`\|`pdf`) and `document_outline` (the extracted slides). |
| `meetings:index` | sorted set | member=`meeting_id`, score=created epoch. |
| `console:reconcile:leader` | string | short-TTL leader lock. |

`meeting_id = "meeting-" + uuid4().hex` and is reused as the dispatch `run_id`.

## Background tasks

- **Generation** ([generation.py](generation.py)) — spawned per create/regenerate. Calls template-generator `POST /generate` (1-4 min), writes the result back guarded by `generation_seq` (so an edit mid-generation is never clobbered).
- **Reconcile** ([reconcile.py](reconcile.py)) — every `CONSOLE_RECONCILE_INTERVAL`s, under a leader lock: moves `running` meetings to `done` by reading `state:<run_id>.end_reason` (grace window + 24h ceiling for crashed/SIGKILLed agents), and reaps generations stuck past ~10 min.

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `REDIS_URL` | yes (default `redis://localhost:6379/0`) | registry + reading `state:*`. |
| `DISPATCH_URL` | optional (default `http://dispatch:8766`) | start a meeting. |
| `TEMPLATE_GEN_URL` | optional (default `http://template-generator:8768`) | generation. |
| `WEBAPP_PUBLIC_URL` | optional (default `http://localhost:8765`) | not used directly; dispatch builds the webapp URL. |
| `CONSOLE_PORT` | optional (default 8770) | aiohttp listen port. |
| `CONSOLE_GEN_MAX_ITERATIONS` | optional (default 3) | passed to template-generator. |
| `CONSOLE_RECONCILE_INTERVAL` | optional (default 15) | reconcile period, seconds. |
| `CONSOLE_STARTUP_GRACE_MIN` | optional (default 5) | agent-never-started grace window. |

## Entry point and command

```
python -m src.console
```

[Dockerfile.console](../../Dockerfile.console) is a single-stage Python image (`aiohttp redis loguru pydantic python-dotenv`) — no livekit/openai.

## Verify changes

```
docker compose build console && docker compose up -d console
curl http://localhost:8770/healthz                                   # → ok
curl -s -X POST http://localhost:8770/api/meetings \
     -H 'Content-Type: application/json' \
     -d '{"title":"Test","prompt":"A short test meeting.","target_minutes":5}'
# poll GET /api/meetings/<id> until template_status=ready, then POST .../start
```
