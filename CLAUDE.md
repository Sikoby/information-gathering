# CLAUDE.md — system overview

> **Rule of the house:** any substantial change to the system architecture, the set of services, how they communicate, or the `docker compose` topology MUST update this file in the same commit. If the diagram below stops matching reality, fix it. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

A briefing-driven voice meeting agent. The agent joins a LiveKit room, runs an interview-style meeting against a free-form markdown briefing, and writes a structured `MeetingState` (transcript, a kinded `Section` tree with the agent's findings, a typed transition log, follow-ups) to disk. A read-only React webapp streams the same state live to anyone with the meeting link. A separate **meeting console** lets a non-developer create a **reusable template** from a prompt — or from an uploaded `.pptx`/`.pdf` (slides become topics, speaker notes become the agent's script) — edit it, and then launch one meeting after another from the same template (one meeting at a time).

## Services

Seven containers. The **meeting console** (`console` + `console-frontend`) is the front door for creating meetings; `agent`, `webapp`, and `dispatch` are the meeting-runtime path; `template-generator` synthesises templates. The agent has **no direct connection** to the other services; every cross-service interaction goes through Redis (state pub/sub + the meeting registry), LiveKit Cloud (room dispatch), or HTTP (console → dispatch / template-generator).

| Service | Container | Code | Responsibility |
| --- | --- | --- | --- |
| agent | `agent` | [src/](src/) (excluding `webapp/`, `dispatch_service/`, `template_generator/`, `console/`) | LiveKit worker. One process per active meeting. Owns `MeetingState`. |
| webapp | `webapp` | [src/webapp/](src/webapp/) + [frontend/](frontend/) | aiohttp HTTP + SSE. Read-only live meeting viewer. Reads state from Redis. |
| dispatch | `dispatch` | [src/dispatch_service/](src/dispatch_service/) | HTTP service. `POST /dispatch` creates a LiveKit room + agent dispatch from an inline briefing. |
| template-generator | `template-generator` | [src/template_generator/](src/template_generator/) | HTTP service. `POST /generate` runs an impl+critique LLM loop to synthesise a meeting `Template`. |
| console | `console` | [src/console/](src/console/) | HTTP API. Owns the `template:*` + `meeting:*` registries; drives template generation; launches meetings from templates; tracks the meeting Running → Done lifecycle. Stateless, scalable. |
| console-frontend | `console-frontend` | [console-frontend/](console-frontend/) | nginx. Serves the console SPA; reverse-proxies `/api` to `console`. |
| redis | `redis` | (Redis 7 image) | State pub/sub, last-snapshot cache, and the meeting registry (AOF-persisted). |

The two React apps share a component library, [`shared/`](shared/) (`@ig/ui`); the repo is an npm workspace (`shared`, `frontend`, `console-frontend`).

Each container / workspace directory has its own CLAUDE.md:
- [src/CLAUDE.md](src/CLAUDE.md) — agent
- [src/webapp/CLAUDE.md](src/webapp/CLAUDE.md) — webapp
- [src/dispatch_service/CLAUDE.md](src/dispatch_service/CLAUDE.md) — dispatch
- [src/template_generator/CLAUDE.md](src/template_generator/CLAUDE.md) — template generator
- [src/console/CLAUDE.md](src/console/CLAUDE.md) — console API
- [console-frontend/CLAUDE.md](console-frontend/CLAUDE.md) — console SPA
- [frontend/CLAUDE.md](frontend/CLAUDE.md) — meeting viewer (built into the webapp image)
- [shared/CLAUDE.md](shared/CLAUDE.md) — shared component library

## How a meeting is created and run

Two entry points create a meeting; both converge on the same dispatch → agent → webapp runtime path.

**Via the console (the webapp):**

```
browser ─▶ console-frontend (nginx) ─▶ console API
                                          │ POST /api/templates ─▶ writes template:<id> (Generating → Ready)
                                          │   └ generation calls template-generator /generate (impl+critique loop)
                                          │ user edits the template + prompt
                                          │ POST /api/templates/<id>/meetings
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
                                                        │ await webapp.register(state)
                                                        ▼
                                                  Redis (state:<run_id>, events:<run_id>)
                                                        ▲
                                                        │ SUBSCRIBE
                                                  webapp container ── SSE ──▶ browser
```

The agent is long-running and registered with LiveKit as `briefing-agent`. The console uses each `meeting_id` as the dispatch `run_id`, so a single meeting has one id across the registry, the LiveKit room, and the webapp viewer URL. The console's reconcile loop reads `state:<run_id>` to move the meeting Running → Done. A meeting is born `running`; there is no `planned` state on the meeting side (the equivalent lives on the template as `template_status: generating | ready | failed`).

## Redis schema

| Key / channel | Type | Writer | Reader | Notes |
| --- | --- | --- | --- | --- |
| `state:<run_id>` | string (JSON) | agent | webapp, console | TTL 24h |
| `events:<run_id>` | pub/sub | agent | webapp | snapshot JSON per message |
| `runs:active` | set | agent | dispatch | optional, served by `GET /runs` |
| `template:<template_id>` | string (JSON) | console | console | the reusable template + its generation metadata + the source document_outline; no TTL, AOF-persisted |
| `templates:index` | sorted set | console | console | template_ids scored by created-at, for listing |
| `meeting:<meeting_id>` | string (JSON) | console | console | a thin meeting instance referencing a template_id; no TTL, AOF-persisted |
| `meetings:index` | sorted set | console | console | meeting_ids scored by created-at, for listing |
| `console:reconcile:leader` | string | console | console | short-TTL leader lock for the reconcile loop |
| `console:start:lock` | string | console | console | short-TTL lock around the start-meeting handler |

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

Ports: console SPA `8769`, console API `8770`, webapp (live viewer) `8765`, dispatch `8766`, template-generator `8768`.

The frontends are an npm workspace — `npm install` at the repo root installs all three (`shared`, `frontend`, `console-frontend`). For UI iteration: `npm run dev -w console-frontend` (console UI, proxies `/api` to a local console API), or the LiveKit-free meeting-viewer preview:

```
docker compose up -d redis
uv run python scripts/preview_dev_server.py    # http://localhost:8767/dev/
```

For a production deploy (single Hetzner VM, Cloudflare Tunnel for ingress + TLS, Cloudflare Access on the console), see [README.md](README.md) "Production deploy". The overlay [docker-compose.prod.yml](docker-compose.prod.yml) adds a `cloudflared` service and closes the host port mappings; the base seven-service architecture is unchanged.

## What's intentionally out of scope here

- Authentication. The console can create and start meetings (spending OpenAI + LiveKit budget) with no auth — same posture as the other public endpoints.
- Auto-registering templates into the agent's hardcoded `TEMPLATES` dict. Custom templates reach the agent inline via dispatch metadata; the dict still holds only the four built-ins.
- The supervisor (silent gpt-5 reviewer) — removed; will return as another container that subscribes to `events:*`. The Redis spine absorbs it without changing the rest.
- Off-host artifact storage (S3). `out/<run_id>/` and `templates_generated/` live in bind-mounted volumes; the template and meeting registries are AOF-persisted Redis.
- k8s manifests. The compose layout maps 1:1 to Deployments / Services.
