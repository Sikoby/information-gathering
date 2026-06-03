# CLAUDE.md — console container (`src/console/`)

> **Rule of the house:** any substantial change to the console's endpoints, [Dockerfile.console](../../Dockerfile.console), entry point, environment variables, dependencies, the Redis registry layout, or the background tasks MUST update this CLAUDE.md in the same commit. If you change the request/response shape or the meeting lifecycle, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

A long-running aiohttp **API service** — the orchestrator and state-owner for **templates** (reusable) and **meetings** (instances). It owns two Redis registries (`template:*` + `meeting:*`), drives template generation, launches meetings from a chosen template, and tracks the meeting **Scheduled → Running → Done** lifecycle.

A meeting is born `running` (start-now) or `scheduled` (a future start). A scheduled meeting carries `scheduled_at` + `invitees` and is **not** dispatched at create time; the reconcile loop dispatches it when its start time arrives (so the short-lived LiveKit voice-join token is minted at start, not ahead of time). There is no `planned` state — the "draft" concept lives on the template as `template_status: generating | ready | failed`.

It serves a JSON API only — no HTML. The console SPA is a separate [`console-frontend`](../../console-frontend/) nginx container that reverse-proxies `/api` here.

The console **never imports agent code** (`harness`, `briefing_plan`, `tools`, livekit, openai). It reads `state:<run_id>` as opaque JSON, exactly like the webapp. `src/templates` is imported only for the `Template` Pydantic schema (used to validate edited templates).

## Stateless and horizontally scalable

There are no in-process locks and no replica cap. Every record update is an **atomic Redis Lua compare-and-swap merge** ([registry.py](registry.py)); the reconcile loop runs under a `SET NX EX` leader lock so only one replica works per tick. `docker compose up --scale console=N` is safe.

## File map

```
src/console/
  __init__.py     module marker / doc only.
  __main__.py     build_app(), main(), on_startup/on_cleanup task wiring.
  auth.py         identity middleware: resolves the Cloudflare Access email
                  (with CONSOLE_DEV_USER_EMAIL fallback) onto request["user_email"].
  models.py       Pydantic: TemplateRecord, MeetingRecord, request bodies.
  registry.py     Redis template:* + meeting:* helpers + the atomic Lua merge.
  clients.py      async HTTP clients for dispatch + template-generator.
  generation.py   background template-generation task (operates on template:*).
  reconcile.py    background lifecycle-reconciliation task (leader-locked).
  ics.py          hand-rolled RFC 5545 VEVENT builder for the .ics invite.
  invites.py      invite delivery — a logged no-op placeholder until SMTP lands.
  handlers.py     /api/* + /healthz handlers.
```

## Identity & scoping

Every `/api/*` request runs through [`auth.py`](auth.py) middleware which reads `Cf-Access-Authenticated-User-Email` (Cloudflare Access in prod), falls back to `CONSOLE_DEV_USER_EMAIL` for local dev, lowercases + strips, and stuffs the result on `request["user_email"]`. Missing identity → `401`. `/healthz` skips the middleware.

Templates and meetings each carry an `owner_email`. List endpoints scope to the caller's per-user index; per-id endpoints return `404` on owner mismatch (not `403`, so we don't leak existence). The one-meeting-at-a-time guard is **per user**, locked on `console:start:lock:<email>`.

`auth.py` also builds the team-domain logout URL returned by `GET /api/me` from the `CONSOLE_CF_TEAM_DOMAIN` env var. The per-application logout (`<app-domain>/cdn-cgi/access/logout`) can fail with "Unable to find your Access organization!"; the team-domain URL is hosted on the org and always resolves.

Background tasks (`generation.py`, `reconcile.py`) do not pass through the middleware and operate on the global indexes (`templates:index`, `meetings:index`).

## Endpoints

**Templates** — the reusable thing:

| Route | Behavior |
| --- | --- |
| `POST /api/templates` | Body `TemplateCreate` (`title`, `source_prompt`, `reference_template?`, `default_target_minutes?`). Stamps `owner_email` from the request, creates a record with `template_status="generating"`, spawns the generation task, returns `201` immediately. |
| `POST /api/templates/upload` | Multipart: `file` (.pptx/.pdf) + `title`, `source_prompt`, `reference_template?`, `default_target_minutes?`. Stamps `owner_email`, forwards the file to template-generator's `/extract`, stores the resulting `DocumentOutline` on the template record, then spawns generation in presentation mode. `201`. `502` if extraction fails. |
| `GET /api/templates` | `{templates: [...]}`, newest first — only the caller's templates. |
| `GET /api/templates/{id}` | The poll endpoint. `200` / `404` (also `404` on owner mismatch). |
| `PATCH /api/templates/{id}` | Edit `title` / `source_prompt` / `template` / `default_target_minutes`. `404` on owner mismatch. Always editable when owned; `400` on an invalid template. Edits do not affect in-flight meetings (the agent already holds the template in-process from dispatch metadata). |
| `POST /api/templates/{id}/regenerate` | `404` on owner mismatch. Bumps `generation_seq`, resets `template_status` to `generating`, re-runs generation (the stored `document_outline` is passed through, so document-driven regenerations don't need re-upload). `202`. |
| `DELETE /api/templates/{id}` | `204` if no meetings reference it; otherwise `409` with `{total_count, running_count}`. `404` on owner mismatch. The referencing-meetings check looks at the caller's meetings only. |
| `POST /api/templates/{id}/meetings` | Body `MeetingStartFromTemplate` (`title_override?`, `target_minutes?`). `404` on owner mismatch. Stamps the new meeting with the caller's `owner_email`. `424` if template is not `ready`; `409` if the caller already has a running meeting (per-user guard, leader-locked on `console:start:lock:<email>`); `502` if dispatch fails. `201` with the new meeting on success. |
| `POST /api/templates/{id}/scheduled-meetings` | Body `MeetingScheduleFromTemplate` (`scheduled_at` required, `title_override?`, `target_minutes?`, `invitees?`). Schedules a future meeting. `404` on owner mismatch; `424` if template is not `ready`; `400` if `scheduled_at` is not in the future. Does **not** dispatch and does **not** apply the one-at-a-time guard (future meetings don't conflict yet). Creates a `status="scheduled"` record with a deterministic `webapp_url` (so the invite has a stable link before dispatch) and calls the `invites.send_invites` placeholder. `201`. The reconcile loop dispatches it when `scheduled_at` arrives. |

**Meetings** — instances + audit log:

| Route | Behavior |
| --- | --- |
| `GET /api/meetings` | `{meetings: [...]}`, newest first — only the caller's meetings. |
| `GET /api/meetings/{id}` | The poll endpoint. `200` / `404` (also `404` on owner mismatch). |
| `GET /api/meetings/{id}/invite.ics` | Downloads the `.ics` calendar invite for a scheduled meeting (`Content-Type: text/calendar`, `Content-Disposition: attachment`). `404` on owner mismatch; `409` if the meeting has no `scheduled_at`. Built by `ics.build_event`; this is what the **Add to calendar** button hits and what the future email step will attach. |
| `DELETE /api/meetings/{id}` | `204`. `404` on owner mismatch. `409` if `running`. |

**Helpers:**

| Route | Behavior |
| --- | --- |
| `GET /api/me` | `{email, logout_url}` — the resolved Cloudflare Access / dev-fallback email plus the team-domain logout URL (`https://<team>.cloudflareaccess.com/cdn-cgi/access/logout`, from `CONSOLE_CF_TEAM_DOMAIN`; `null` when unset, e.g. local dev). SPA uses this for the signed-in indicator, 401 detection, and the Sign out link. |
| `GET /api/reference-templates` | The four built-in templates, for the create form (a generation hint, not promoted into the `template:*` keyspace). |
| `GET /healthz` | `200` iff Redis ping succeeds. Bypasses the auth middleware. |

`client_max_size` is **50 MB** so PPTX uploads pass through.

## Redis keys

| Key | Type | Notes |
| --- | --- | --- |
| `template:<template_id>` | string (JSON) | the `TemplateRecord` — carries `owner_email`. `template` (the body) and `document_outline` are stored as embedded JSON *strings* so the Lua merge never round-trips their nested arrays through cjson (which would collapse empty arrays to `{}`). The record also carries `document_filename` + `document_kind` (`pptx`\|`pdf`) when the template was created via `/upload`. |
| `templates:index` | sorted set | member=`template_id`, score=created epoch. **Global** — backs the reconcile loop's stale-generation sweep. |
| `templates:owner:<email>` | sorted set | same shape; **per-user** — backs `GET /api/templates`. Written alongside the global index on create, removed on delete. |
| `meeting:<meeting_id>` | string (JSON) | the `MeetingRecord` — carries `owner_email` plus `status` (`scheduled`\|`running`\|`done`), `title_override?`, `target_minutes`, LiveKit run info, and lifecycle timestamps. A `scheduled` meeting also carries `scheduled_at`, `invitees`, and `invite_sent_at?`. `invitees` is stored as an embedded JSON *string* (like the template's nested fields) so the Lua merge never round-trips the list through cjson — which would collapse an empty list to `{}` and corrupt the record. No template body lives here. |
| `meetings:index` | sorted set | member=`meeting_id`, score=created epoch. **Global** — backs the reconcile loop's running-meeting sweep. |
| `meetings:owner:<email>` | sorted set | same shape; **per-user** — backs `GET /api/meetings` and the per-user start-meeting concurrency check. |
| `console:reconcile:leader` | string | short-TTL leader lock for the reconcile loop. |
| `console:start:lock:<email>` | string | short-TTL lock around the per-user start-meeting handler so concurrent replicas can't both see "nothing running for this user" and both start. |

`template_id = "template-" + uuid4().hex`; `meeting_id = "meeting-" + uuid4().hex` and is reused as the dispatch `run_id`.

## Background tasks

- **Generation** ([generation.py](generation.py)) — spawned per template create/regenerate. Calls template-generator `POST /generate` (1-4 min), writes the result back into `template:<id>` guarded by `generation_seq` (so an edit mid-generation is never clobbered).
- **Reconcile** ([reconcile.py](reconcile.py)) — every `CONSOLE_RECONCILE_INTERVAL`s, under a leader lock, three passes: (1) **dispatches `scheduled` meetings** whose `scheduled_at` has arrived (deferred dispatch — mints the LiveKit token at start, flips them to `running`); a due meeting yields to the per-user one-at-a-time guard, deferred a tick if the owner already has a running meeting, and is retired `done`/`schedule_missed` past `CONSOLE_SCHEDULE_LATE_CEILING_HOURS`. (2) moves `running` meetings to `done` by reading `state:<run_id>.end_reason` (grace window + 24h ceiling for crashed/SIGKILLed agents). (3) reaps template generations stuck past ~10 min.

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `REDIS_URL` | yes (default `redis://localhost:6379/0`) | registry + reading `state:*`. |
| `DISPATCH_URL` | optional (default `http://dispatch:8766`) | start a meeting. |
| `TEMPLATE_GEN_URL` | optional (default `http://template-generator:8768`) | generation. |
| `WEBAPP_PUBLIC_URL` | optional (default `http://localhost:8765`) | base of the meeting's public live-view page. Used to stamp a **deterministic** `webapp_url` (`<base>/<meeting_id>/`) on a scheduled meeting so its `.ics` has a stable link before dispatch. For start-now meetings, dispatch builds the same URL. |
| `CONSOLE_PORT` | optional (default 8770) | aiohttp listen port. |
| `CONSOLE_DEV_USER_EMAIL` | optional (unset → 401) | Local-dev identity fallback when `Cf-Access-Authenticated-User-Email` is absent. Compose default is `dev@local`; left empty in `docker-compose.prod.yml`. |
| `CONSOLE_CF_TEAM_DOMAIN` | optional (unset → `logout_url` is `null`) | Cloudflare Zero Trust team name (`myteam`) or full host (`myteam.cloudflareaccess.com`); backs the `GET /api/me` `logout_url`. Set it in `.env` (the console loads it via `env_file`). |
| `CONSOLE_GEN_MAX_ITERATIONS` | optional (default 3) | passed to template-generator. |
| `CONSOLE_RECONCILE_INTERVAL` | optional (default 15) | reconcile period, seconds. |
| `CONSOLE_STARTUP_GRACE_MIN` | optional (default 5) | agent-never-started grace window. |
| `CONSOLE_SCHEDULE_LATE_CEILING_HOURS` | optional (default 6) | a `scheduled` meeting overdue past this (owner perpetually busy, or dispatch failing) is retired `done`/`schedule_missed`. |

## Entry point and command

```
python -m src.console
```

[Dockerfile.console](../../Dockerfile.console) is a single-stage Python image (`aiohttp redis loguru pydantic python-dotenv`) — no livekit/openai.

## Verify changes

```
docker compose build console && docker compose up -d console
curl http://localhost:8770/healthz                                   # → ok
# /api/* requires identity — supply Cf-Access-Authenticated-User-Email or
# rely on CONSOLE_DEV_USER_EMAIL from the compose file (defaults to dev@local).
curl -s -H 'Cf-Access-Authenticated-User-Email: alice@x.test' \
     http://localhost:8770/api/me                                    # → {"email":"alice@x.test"}
curl -s -H 'Cf-Access-Authenticated-User-Email: alice@x.test' \
     -X POST http://localhost:8770/api/templates \
     -H 'Content-Type: application/json' \
     -d '{"title":"Test","source_prompt":"A short test meeting.","default_target_minutes":5}'
# poll GET /api/templates/<id> (with the same header) until template_status=ready
curl -s -H 'Cf-Access-Authenticated-User-Email: alice@x.test' \
     -X POST http://localhost:8770/api/templates/<id>/meetings -d '{}'
# Switch the header to bob@x.test and confirm GET /api/templates returns
# bob's list (empty until bob creates one) and GET /api/templates/<alice-id>
# returns 404.

# Schedule a future meeting (note the deterministic webapp_url in the reply):
curl -s -H 'Cf-Access-Authenticated-User-Email: alice@x.test' \
     -X POST http://localhost:8770/api/templates/<id>/scheduled-meetings \
     -H 'Content-Type: application/json' \
     -d '{"scheduled_at":"2099-01-01T10:00:00Z","invitees":["bob@x.test"]}'
# Download the .ics (imports cleanly into Google/Apple/Outlook):
curl -s -H 'Cf-Access-Authenticated-User-Email: alice@x.test' \
     http://localhost:8770/api/meetings/<meeting-id>/invite.ics
# Cross-user: the SAME path as bob@x.test returns 404 (owner-scoped).
# To watch deferred dispatch, schedule ~2 min out, lower
# CONSOLE_RECONCILE_INTERVAL, and poll GET /api/meetings/<id> until it
# flips scheduled -> running and gains a join_url.
```
