# CLAUDE.md — system overview

> **Rule of the house:** any substantial change to the system architecture, the set of services, how they communicate, or the `docker compose` topology MUST update this file in the same commit. If the diagram below stops matching reality, fix it. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

A briefing-driven voice meeting agent. The agent joins a LiveKit room, runs an interview-style meeting against a free-form markdown briefing, and writes a structured `MeetingState` (transcript, a kinded `Section` tree with the agent's findings, a typed transition log, follow-ups) to disk. A read-only React live view (served by the participant-facing **meeting** tier) streams the same state live to anyone with the meeting link, and the same tier hosts the PIN-gated **join** page for invited participants. A separate **meeting console** lets a non-developer create a **reusable template** from a prompt — or from an uploaded `.pptx`/`.pdf` (slides become topics, speaker notes become the agent's script) — edit it, and then launch meetings from the same template — one at a time, or a **batch** that interviews many people in parallel, each in their own room.

## Services

Eight containers. The **meeting console** (`console` + `console-frontend`) is the front door for creating meetings; `agent`, the participant-facing **meeting** pair (`meeting` + `meeting-frontend`), and `dispatch` are the meeting-runtime path; `template-generator` synthesises templates. The agent has **no direct connection** to the other services; every cross-service interaction goes through Redis (state pub/sub + the meeting registry), LiveKit Cloud (room dispatch), or HTTP (console → dispatch / template-generator) — plus one shared bind mount: the agent's flushed `out/<run_id>/` artifacts, which the console reads **read-only** to serve a finished meeting's results and `.xlsx` export.

The participant tier mirrors the console's two-container shape: a Python JSON API (`meeting`) behind an nginx SPA host (`meeting-frontend`) that serves the bundle and reverse-proxies `/api`. The console is the **organiser**-facing app; the meeting tier is the **participant**-facing app (live view + join).

| Service | Container | Code | Responsibility |
| --- | --- | --- | --- |
| agent | `agent` | [src/](src/) (excluding `meeting/`, `dispatch_service/`, `template_generator/`, `console/`) | LiveKit worker. One process per active meeting. Owns `MeetingState`. |
| meeting | `meeting` | [src/meeting/](src/meeting/) | aiohttp JSON API under `/api/*` + SSE. Serves live-view state and the join flow. Reads state from Redis; calls dispatch to mint join tokens. |
| meeting-frontend | `meeting-frontend` | [meeting-frontend/](meeting-frontend/) | nginx. Serves the participant SPA (live view + join); reverse-proxies `/api` to `meeting`. |
| dispatch | `dispatch` | [src/dispatch_service/](src/dispatch_service/) | HTTP service. `POST /dispatch` creates a LiveKit room + agent dispatch from an inline briefing. |
| template-generator | `template-generator` | [src/template_generator/](src/template_generator/) | HTTP service. `POST /generate` runs an impl+critique LLM loop to synthesise a meeting `Template`. |
| console | `console` | [src/console/](src/console/) | HTTP API. Owns the `template:*` + `meeting:*` registries; drives template generation; launches meetings from templates; tracks the meeting Running → Done lifecycle. Serves a finished meeting's results (section tree + transcript) and the answers `.xlsx` export from the agent's flushed artifacts via a read-only `./out` mount. Stateless, scalable. |
| console-frontend | `console-frontend` | [console-frontend/](console-frontend/) | nginx. Serves the console SPA; reverse-proxies `/api` to `console`. |
| redis | `redis` | (Redis 7 image) | State pub/sub, last-snapshot cache, and the meeting registry (AOF-persisted). |

The three React apps share a component library, [`shared/`](shared/) (`@ig/ui`); the repo is an npm workspace (`shared`, `meeting-frontend`, `console-frontend`).

Each container / workspace directory has its own CLAUDE.md:
- [src/CLAUDE.md](src/CLAUDE.md) — agent
- [src/meeting/CLAUDE.md](src/meeting/CLAUDE.md) — meeting API
- [src/dispatch_service/CLAUDE.md](src/dispatch_service/CLAUDE.md) — dispatch
- [src/template_generator/CLAUDE.md](src/template_generator/CLAUDE.md) — template generator
- [src/console/CLAUDE.md](src/console/CLAUDE.md) — console API
- [console-frontend/CLAUDE.md](console-frontend/CLAUDE.md) — console SPA
- [meeting-frontend/CLAUDE.md](meeting-frontend/CLAUDE.md) — participant SPA (live view + join)
- [shared/CLAUDE.md](shared/CLAUDE.md) — shared component library

## How a meeting is created and run

Two entry points create a meeting; both converge on the same dispatch → agent → meeting runtime path.

**Via the console:**

```
browser ─▶ console-frontend (nginx) ─▶ console API
                                          │ POST /api/templates ─▶ writes template:<id> (Generating → Ready)
                                          │   └ generation calls template-generator /generate (impl+critique loop)
                                          │ user edits the template + prompt
                                          │ POST /api/templates/<id>/meetings        (or /batch-meetings — N people, parallel rooms)
                                          │   ├ POST /dispatch ─▶ dispatch
                                          │   └ writes meeting:<id> to Redis (Running → Done)
                                          (template stays; user can start more meetings from it)
```

**Via the CLI (developer path):**

```
host: scripts/dispatch.py --briefing X.md --target-minutes 30
        │ reads the file, HTTP POST /dispatch (briefing sent inline)
        ▼
  dispatch container
```

Either way, dispatch then:

```
  dispatch container
        │ HTTPS: LiveKit RoomService.create_room + AgentDispatchService.create_dispatch
        ▼
  LiveKit Cloud  ── job offer over WebSocket ──▶  agent container (one of N replicas)
                                                        │ await ctx.connect()
                                                        │ await meeting.register(state)
                                                        ▼
                                                  Redis (state:<run_id>, events:<run_id>)
                                                        ▲
                                                        │ SUBSCRIBE
              meeting (API) ── SSE ──▶ meeting-frontend (nginx) ──▶ browser
```

The agent is long-running and registered with LiveKit as `briefing-agent`. The console uses each `meeting_id` as the dispatch `run_id`, so a single meeting has one id across the registry, the LiveKit room, and the live-view URL. The console's reconcile loop reads `state:<run_id>` to move the meeting Running → Done. Meetings run concurrently — there is no per-user limit — and a **batch** create (`POST /api/templates/<id>/batch-meetings`, or `…/scheduled-batch-meetings` for a future start) launches N meetings at once from one template, one per interviewee (the person's name becomes the meeting title, their email its single invitee). A meeting is born `running` (start-now) or `scheduled` (a future start); a scheduled meeting carries `scheduled_at` + `invitees` and is **dispatched later by the reconcile loop** when its start time arrives, so the short-lived LiveKit voice-join token is minted then, not at schedule time. When a meeting is scheduled with invitees, the console **emails each invitee** (SMTP — [src/console/invites.py](src/console/invites.py), a logged no-op when `SMTP_HOST` is unset) an `.ics` plus a **permanent, PIN-gated join link** (`<meeting>/join/<meeting_id>`) and a generated `join_pin`; the same `.ics` is still downloadable at `GET /api/meetings/<id>/invite.ics`. The join link routes through the **meeting** tier (the public participant app — `meeting-frontend` serves the SPA, the `meeting` API gates on status + PIN), which then asks **dispatch** (`POST /join-token`) to mint a fresh voice-join token at click time — so the email never carries an expiring token, and the room is reachable only once the meeting is `running` (blocked until start). There is no `planned` state on the meeting side (the equivalent lives on the template as `template_status: generating | ready | failed`).

## Redis schema

| Key / channel | Type | Writer | Reader | Notes |
| --- | --- | --- | --- | --- |
| `state:<run_id>` | string (JSON) | agent | meeting, console | TTL 24h |
| `events:<run_id>` | pub/sub | agent | meeting | snapshot JSON per message |
| `runs:active` | set | agent | dispatch | optional, served by `GET /runs` |
| `template:<template_id>` | string (JSON) | console | console | the reusable template + its generation metadata + the source document_outline + `owner_email`; no TTL, AOF-persisted |
| `templates:index` | sorted set | console | console | template_ids scored by created-at; global, used by the reconcile loop |
| `templates:owner:<email>` | sorted set | console | console | the user's templates, scored by created-at; backs `GET /api/templates` |
| `meeting:<meeting_id>` | string (JSON) | console | console, **meeting** (read-only, for the join page) | a thin meeting instance referencing a template_id, plus `owner_email`; `status` is `scheduled`\|`running`\|`done`, with `scheduled_at`+`invitees`+`join_pin` on a scheduled meeting (`invitees` embedded as a JSON *string* to survive the Lua merge); no TTL, AOF-persisted |
| `meetings:index` | sorted set | console | console | meeting_ids scored by created-at; global, used by the reconcile loop |
| `meetings:owner:<email>` | sorted set | console | console | the user's meetings, scored by created-at; backs `GET /api/meetings` |
| `console:reconcile:leader` | string | console | console | short-TTL leader lock for the reconcile loop |

Redis runs with AOF persistence (`--appendonly yes`) and a named volume so the template + meeting registries survive restarts.

## Generating a meeting template

The `template-generator` service runs an LLM **implementation + critique loop** to synthesise a `Template` from a free-form description:

```
console  (or scripts/generate_template.py)
        │ HTTP POST /generate          (+ optional document_outline)
        ▼
  template-generator container
        │ OpenAI Responses API: propose Template → critique → revise → ...
        ▼
  returns the Template (+ iteration history); also written to ./templates_generated/
```

The console calls this when a user creates a template, then lets the user edit the result. When the user later starts a meeting from that template, the agent receives the (possibly edited) template **inline** through the dispatch metadata — it is **not** registered in the agent's hardcoded `TEMPLATES` dict (that dict still holds only the four built-in templates, used for CLI briefings that carry no custom template).

### Document-driven creation (presentation mode)

When the user uploads a `.pptx` or `.pdf` via the console, the flow is:

```
browser ─▶ console-frontend ─▶ console POST /api/templates/upload  (multipart)
                                  │ forwards the file to template-generator POST /extract
                                  ◀ DocumentOutline {kind, slides[{title, content, speaker_notes}]}
                                  │ persists outline on template:<id>
                                  └ spawns generation, passing document_outline through to POST /generate
```

In "presentation mode" the implementation/critique loop emits **one TOPIC per slide** (slide order preserved), copies each slide's `speaker_notes` **verbatim** into `private_notes`, and wraps the walkthrough in framing phases (rapport, Q&A, wrap). A "polluted" slide may be split into a parent + 2-3 child TOPICs. The stored outline lives on the template, so `regenerate` works without re-uploading.

## Running locally

```
cp .env.example .env       # fill in LIVEKIT_* and OPENAI_API_KEY
docker compose up -d
```

Open the **meeting console** at `http://localhost:8769` to create a template from a prompt, then start a meeting from it. Or use the developer CLI:

```
uv run python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
```

Ports: console SPA `8769`, console API `8770`, meeting-frontend (live viewer + join) `8765`, meeting API `8771`, dispatch `8766`, template-generator `8768`.

### Invite email — work in progress

Real outbound email **delivery is not done yet** (the Gmail/Workspace path is blocked by provider auth policy). To test the invite path locally, the repo ships a dev-only [docker-compose.override.yml](docker-compose.override.yml) that `docker compose up` auto-merges (the prod deploy passes explicit `-f` files, so it's excluded there). It adds **Mailpit** — an open-source SMTP sink (web inbox at `http://localhost:8025`, SMTP on `1025`) — and repoints the console's `SMTP_*` at it. Schedule a meeting with an invitee and the email lands in the Mailpit inbox instead of a real mailbox. This proves the **app-side send path** ([src/console/invites.py](src/console/invites.py) — message build, `.ics` attachment, join link + PIN), **not** deliverability. Delete the override file to fall back to the real SMTP in `.env`.

The frontends are an npm workspace — `npm install` at the repo root installs all three (`shared`, `frontend`, `console-frontend`). For UI iteration: `npm run dev -w console-frontend` (console UI, proxies `/api` to a local console API), or the LiveKit-free meeting-viewer preview:

```
docker compose up -d redis
uv run python scripts/preview_dev_server.py    # http://localhost:8767/dev/
```

For a production deploy (single Hetzner VM, Cloudflare Tunnel for ingress + TLS, Cloudflare Access on the console), see [README.md](README.md) "Production deploy". The overlay [docker-compose.prod.yml](docker-compose.prod.yml) adds a `cloudflared` service and closes the host port mappings; the base eight-service architecture is unchanged.

## Console identity

The console is **per-user**: every template and every meeting carries an `owner_email`, and the list endpoints (`GET /api/templates`, `GET /api/meetings`) only return records owned by the caller.

Identity comes from the `Cf-Access-Authenticated-User-Email` request header that Cloudflare Access stamps onto every prod request once the user has signed in. In local dev there is no Cloudflare in front, so the console falls back to the `CONSOLE_DEV_USER_EMAIL` env var (defaults to `dev@local` in the compose file). Override it to simulate different users. In production the var is left empty, so a request without the Cloudflare header gets a `401`.

The dispatch and meeting (participant-facing) services remain unauthenticated — the live meeting viewer is a public link and the CLI dispatch path is for developers. Only the console is scoped.

## What's intentionally out of scope here

- Authentication beyond the Cloudflare-Access email above. No login UI, no roles, no per-record sharing, no session store. The meeting (participant-facing) and dispatch services remain open.
- Auto-registering templates into the agent's hardcoded `TEMPLATES` dict. Custom templates reach the agent inline via dispatch metadata; the dict still holds only the four built-ins.
- The supervisor (silent gpt-5 reviewer) — removed; will return as another container that subscribes to `events:*`. The Redis spine absorbs it without changing the rest.
- Off-host artifact storage (S3). `out/<run_id>/` and `templates_generated/` live in bind-mounted volumes; the template and meeting registries are AOF-persisted Redis.
- k8s manifests. The compose layout maps 1:1 to Deployments / Services.
