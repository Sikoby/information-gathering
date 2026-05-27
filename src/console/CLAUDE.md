# CLAUDE.md — console container (`src/console/`)

> **Rule of the house:** any substantial change to the console's endpoints, [Dockerfile.console](../../Dockerfile.console), entry point, environment variables, dependencies, the Redis registry layout, or the background tasks MUST update this CLAUDE.md in the same commit. If you change the request/response shape or the meeting lifecycle, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

A long-running aiohttp **API service** — the orchestrator and state-owner for **templates** (reusable) and **meetings** (instances). It owns two Redis registries (`template:*` + `meeting:*`), drives template generation, launches meetings from a chosen template, and tracks the meeting **Running → Done** lifecycle.

A meeting is born `running`; there is no `planned` state on the meeting side. The "planned" / "draft" concept lives on the template as `template_status: generating | ready | failed`.

It serves a JSON API only — no HTML. The console SPA is a separate [`console-frontend`](../../console-frontend/) nginx container that reverse-proxies `/api` here.

The console **never imports agent code** (`harness`, `briefing_plan`, `tools`, livekit, openai). It reads `state:<run_id>` as opaque JSON, exactly like the webapp. `src/templates` is imported only for the `Template` Pydantic schema (used to validate edited templates).

## Stateless and horizontally scalable

There are no in-process locks and no replica cap. Every record update is an **atomic Redis Lua compare-and-swap merge** ([registry.py](registry.py)); the reconcile loop runs under a `SET NX EX` leader lock so only one replica works per tick. `docker compose up --scale console=N` is safe.

## File map

```
src/console/
  __init__.py     module marker / doc only.
  __main__.py     build_app(), main(), on_startup/on_cleanup task wiring.
  models.py       Pydantic: TemplateRecord, MeetingRecord, request bodies.
  registry.py     Redis template:* + meeting:* helpers + the atomic Lua merge.
  clients.py      async HTTP clients for dispatch + template-generator.
  generation.py   background template-generation task (operates on template:*).
  reconcile.py    background lifecycle-reconciliation task (leader-locked).
  handlers.py     /api/* + /healthz handlers.
```

## Endpoints

**Templates** — the reusable thing:

| Route | Behavior |
| --- | --- |
| `POST /api/templates` | Body `TemplateCreate` (`title`, `source_prompt`, `reference_template?`, `default_target_minutes?`). Creates a record with `template_status="generating"`, spawns the generation task, returns `201` immediately. |
| `POST /api/templates/upload` | Multipart: `file` (.pptx/.pdf) + `title`, `source_prompt`, `reference_template?`, `default_target_minutes?`. Forwards the file to template-generator's `/extract`, stores the resulting `DocumentOutline` on the template record, then spawns generation in presentation mode. `201`. `502` if extraction fails. |
| `GET /api/templates` | `{templates: [...]}`, newest first. |
| `GET /api/templates/{id}` | The poll endpoint. `200` / `404`. |
| `PATCH /api/templates/{id}` | Edit `title` / `source_prompt` / `template` / `default_target_minutes`. Always editable; `400` on an invalid template. Edits do not affect in-flight meetings (the agent already holds the template in-process from dispatch metadata). |
| `POST /api/templates/{id}/regenerate` | Bumps `generation_seq`, resets `template_status` to `generating`, re-runs generation (the stored `document_outline` is passed through, so document-driven regenerations don't need re-upload). `202`. |
| `DELETE /api/templates/{id}` | `204` if no meetings reference it; otherwise `409` with `{total_count, running_count}`. |
| `POST /api/templates/{id}/meetings` | Body `MeetingStartFromTemplate` (`title_override?`, `target_minutes?`). Calls dispatch and creates a meeting with `status="running"`. `424` if template is not `ready`; `409` if another meeting is already running (one-at-a-time guard, leader-locked); `502` if dispatch fails. `201` with the new meeting on success. |

**Meetings** — instances + audit log:

| Route | Behavior |
| --- | --- |
| `GET /api/meetings` | `{meetings: [...]}`, newest first. |
| `GET /api/meetings/{id}` | The poll endpoint. `200` / `404`. |
| `DELETE /api/meetings/{id}` | `204`. `409` if `running`. |

**Helpers:**

| Route | Behavior |
| --- | --- |
| `GET /api/reference-templates` | The four built-in templates, for the create form (a generation hint, not promoted into the `template:*` keyspace). |
| `GET /healthz` | `200` iff Redis ping succeeds. |

`client_max_size` is **50 MB** so PPTX uploads pass through.

## Redis keys

| Key | Type | Notes |
| --- | --- | --- |
| `template:<template_id>` | string (JSON) | the `TemplateRecord`. `template` (the body) and `document_outline` are stored as embedded JSON *strings* so the Lua merge never round-trips their nested arrays through cjson (which would collapse empty arrays to `{}`). The record also carries `document_filename` + `document_kind` (`pptx`\|`pdf`) when the template was created via `/upload`. |
| `templates:index` | sorted set | member=`template_id`, score=created epoch. |
| `meeting:<meeting_id>` | string (JSON) | the `MeetingRecord` — a thin instance pointing at a `template_id`. Carries `status` (`running`\|`done`), `title_override?`, `target_minutes`, LiveKit run info, and lifecycle timestamps. No template body lives here. |
| `meetings:index` | sorted set | member=`meeting_id`, score=created epoch. |
| `console:reconcile:leader` | string | short-TTL leader lock for the reconcile loop. |
| `console:start:lock` | string | short-TTL lock around the start-meeting handler so concurrent replicas can't both see "nothing running" and both start. |

`template_id = "template-" + uuid4().hex`; `meeting_id = "meeting-" + uuid4().hex` and is reused as the dispatch `run_id`.

## Background tasks

- **Generation** ([generation.py](generation.py)) — spawned per template create/regenerate. Calls template-generator `POST /generate` (1-4 min), writes the result back into `template:<id>` guarded by `generation_seq` (so an edit mid-generation is never clobbered).
- **Reconcile** ([reconcile.py](reconcile.py)) — every `CONSOLE_RECONCILE_INTERVAL`s, under a leader lock: moves `running` meetings to `done` by reading `state:<run_id>.end_reason` (grace window + 24h ceiling for crashed/SIGKILLed agents), and reaps template generations stuck past ~10 min.

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
curl -s -X POST http://localhost:8770/api/templates \
     -H 'Content-Type: application/json' \
     -d '{"title":"Test","source_prompt":"A short test meeting.","default_target_minutes":5}'
# poll GET /api/templates/<id> until template_status=ready
curl -s -X POST http://localhost:8770/api/templates/<id>/meetings -d '{}'
```
