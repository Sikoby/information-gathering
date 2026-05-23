# Briefing-driven voice meeting agent

A Python prototype that joins a LiveKit room as a senior consultant, runs a meeting based on a free-form markdown briefing, and writes a transcript plus structured findings to disk. A live read-only webapp shows what the agent has captured so far. The briefing is the only thing that changes between meetings.

The system runs as four containers — agent, webapp, dispatch, redis — brokered by a Redis pub/sub spine. See [CLAUDE.md](CLAUDE.md) for the architecture overview.

## Prerequisites

- Docker + Docker Compose (the recommended way to run everything)
- A LiveKit Cloud project and an OpenAI API key
- An OpenGL/EGL runtime for the agent's animated face (the avatar renders GLSL shaders via `moderngl`). On Debian/Ubuntu: `apt install libegl1 libegl-mesa0`. macOS works out of the box.
- For host-side tooling: Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (the `scripts/dispatch.py` CLI uses only the stdlib but `uv` makes installs painless if you also want to run scripts locally)

## One-time setup

```
cp .env.example .env       # fill in LIVEKIT_* and OPENAI_API_KEY
docker compose build
```

Fill in `.env`:

| Variable | Source |
| --- | --- |
| `LIVEKIT_URL` | LiveKit Cloud project settings (wss://your-project.livekit.cloud) |
| `LIVEKIT_API_KEY` | LiveKit Cloud API key |
| `LIVEKIT_API_SECRET` | LiveKit Cloud API secret |
| `OPENAI_API_KEY` | platform.openai.com |
| `WEBAPP_PUBLIC_URL` | optional — the URL the agent posts to the room chat (default `http://localhost:8765`). Override when tunneling. |

## Run a meeting

```
docker compose up -d
uv run python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
```

The dispatch CLI POSTs to the dispatch container at `http://localhost:8766/dispatch` and prints a `https://meet.livekit.io/custom?...` URL and a `http://localhost:8765/<run_id>/` URL.

1. Open the `meet.livekit.io` URL in a browser, allow the mic, and join. The agent speaks first within a second or two.
2. As soon as you join the room, the agent drops the webapp URL into the room's chat panel — click it (or open the localhost URL from your terminal) to watch the live cockpit: meeting title, tree-position breadcrumb, agenda timeline, recursive notebook (phases → topics → questions → answers), typed transition log, and follow-ups updating as you talk.
3. When the agent calls `end_meeting` (or you leave), the worker flushes the run to `out/<run_id>/`.

Logs from any service: `docker compose logs -f agent` (or `webapp`, `dispatch`, `redis`).

## Swap briefings

Point `--briefing` at any markdown file. No code changes per meeting.

```
uv run python scripts/dispatch.py --briefing briefings/02_q1_satisfaction.md --target-minutes 25
uv run python scripts/dispatch.py --briefing briefings/03_migration_walkthrough.md --target-minutes 20
```

Three briefings ship as examples: a data warehouse requirements interview, a Q1 satisfaction probe, and a migration timeline walkthrough.

## Preview the webapp without a real meeting

If you just want to see the UI with synthetic state (no LiveKit, no microphone):

```
docker compose up -d redis             # the preview also reads state from Redis now
uv run python scripts/preview_dev_server.py
```

Opens at `http://localhost:8767/dev/` with a fake mid-meeting state. Useful for iterating on the frontend — see [frontend/CLAUDE.md](frontend/CLAUDE.md) and [frontend/DESIGN.md](frontend/DESIGN.md).

## Briefings vs templates

These are two different things and the difference matters when you write your own meetings.

A **briefing** (in `briefings/`) is a free-form markdown file describing *this specific meeting* — its purpose, the topics to cover, any time-budget or tone hints. Briefings are what change between meetings; the agent reads exactly one per run. A briefing typically opens with `# Briefing: <Title>` — that title is what the webapp shows as the meeting title.

A **template** (in `src/templates/`) is a reusable, structured meeting *shape* defined in Python. A template is a tree of `Section` nodes with a `kind` discriminator:

- the root is the meeting itself (`kind=meeting`); at runtime the agent calls `frame_meeting` to fill in the BLUF (top-of-pyramid one-liner) and the SCQA framing;
- top-level children are the **phases** (`kind=phase`, each owning a `target_fraction` of the meeting time) — e.g. for `requirements`: Rapport → Define → Prioritise → Wrap;
- each phase owns **topics** (`kind=topic`) which own **questions** (`kind=question`) which collect **answers** (`kind=answer`, created at runtime by `record_finding`).

The phase timeline is just a filter over the tree; "have we covered what we need" is just "how many QUESTION descendants of the current phase still have zero ANSWER children". Four templates ship: `requirements`, `research`, `eval`, `generic`.

When a meeting starts, [src/briefing_plan.py](src/briefing_plan.py) selects a template — either from a YAML front-matter `template: <name>` block at the top of the briefing, or by asking `gpt-5-mini` which of the four templates best fits the briefing text.

Pin a template explicitly with front-matter:

```
---
template: requirements
---
# Briefing: Data Warehouse Requirements Interview
...
```

In plain English: **the briefing is the *what* (this conversation), the template is the *how* (the structure the agent runs it in).** Writing a new meeting almost always means writing a new briefing; writing a new *kind* of meeting (a new agenda shape) means adding a template under `src/templates/`.

## Output per run

`out/<run_id>/`:

| File | Contents |
| --- | --- |
| `briefing.md` | Copy of the briefing the agent used |
| `tree.json` | Canonical: the full `Section` tree (template + every ANSWER / CLOSING node created at runtime) |
| `transitions.json` | Chronological `navigate()` events (typed: open / drill_down / zoom_out / sibling / revisit) |
| `notebook.json` | Derived view: `{parent_id: [{header, body, ts}, ...]}` for back-compat tooling |
| `followups.json` | Whatever the agent noted via `note_followup` |
| `transcript.jsonl` | One JSON object per utterance (`ts`, `role`, `text`) |
| `meta.json` | run_id, briefing_path, target_minutes, started_at, ended_at, end_reason, current_section_id, visited_section_ids, turn count |

## Architecture

The system runs as four containers, brokered by Redis:

| Container | Role |
| --- | --- |
| `dispatch` | aiohttp service exposing `POST /dispatch`. Creates the LiveKit room, mints the stakeholder access token, and calls `AgentDispatchService.CreateDispatch` with JSON metadata `{briefing_path, run_id, target_minutes}`. |
| `agent` | LiveKit worker. Long-running; registers with LiveKit as `briefing-agent` and waits for job offers. On each job: reads metadata, runs `src/briefing_plan.py` (one offline `openai.responses.parse` call) to pick a template, builds a `MeetingState` (a deep copy of the template's section tree), runs the meeting on `gpt-realtime` with voice `cedar`, and writes `out/<run_id>/` at shutdown. |
| `webapp` | aiohttp + SSE. Reads `state:<run_id>` from Redis on `GET /<run_id>/state`; subscribes to `events:<run_id>` for `GET /<run_id>/events`. Stateless. |
| `redis` | Message bus between agent and webapp. Holds the latest snapshot at `state:<run_id>` (24h TTL) and broadcasts every change on `events:<run_id>`. |

Data flow inside a meeting:

1. `scripts/dispatch.py` (host) POSTs to the dispatch container; dispatch calls LiveKit Cloud and returns the join URLs.
2. LiveKit Cloud pushes the job offer to one of the agent worker replicas over its WebSocket.
3. The agent invokes `entrypoint(ctx)`, parses metadata, builds `MeetingState`, and calls `await webapp.register(state)` — that writes the initial snapshot to Redis.
4. The agent runs the meeting on `gpt-realtime`. `MeetingState` is attached to `AgentSession.userdata`, so every `function_tool` in `src/tools.py` receives it via `RunContext[MeetingState].userdata`. `input_audio_transcription` (`gpt-4o-mini-transcribe`) feeds the LiveKit `conversation_item_added` event handler that appends to `transcript.jsonl`.
5. Every four user turns, the system prompt is refreshed via `agent.update_instructions(...)` so the current tree position and navigation options stay in front of the model. Five minutes before the target end, a scheduled task injects a wrap-up nudge.
6. After every state mutation (turn count, new ANSWER node, navigation, closing summary, followup), the agent calls `await webapp.publish(state)` — that writes `state:<run_id>` and publishes on `events:<run_id>`. Any browser connected to the webapp via SSE receives the new snapshot.
7. On any close path (`end_meeting` tool, user leaves, error), `JobContext.add_shutdown_callback` flushes the full state to `out/<run_id>/` and removes the run from `runs:active`.

The agent has **no direct connection** to the webapp or dispatch — everything internal goes through Redis (state pub/sub) or LiveKit Cloud (room dispatch). See [CLAUDE.md](CLAUDE.md) for the diagram.

## Project layout

```
briefings/                three example briefings (markdown)
src/
  agent.py                LiveKit worker entrypoint (agent container)
  harness.py              MeetingState (Pydantic), Transition/TransitionKind, prompt builder
  briefing_plan.py        briefing -> template selection via Responses API
  persistence.py          out/<run_id>/ file IO
  tools.py                function_tools: navigate, record_finding, frame_meeting,
                          deliver_pyramid_summary, note_followup, end_meeting
  templates/              reusable meeting shapes (requirements, research, eval, generic)
                          — each is a tree of kinded Section nodes
  webapp/                 aiohttp + Redis-backed SSE server (webapp container)
  dispatch_service/       aiohttp service that creates rooms + dispatches agents (dispatch container)
frontend/                 React + Vite read-only live viewer (built into webapp image)
scripts/
  dispatch.py             thin CLI that POSTs to the dispatch container
  preview_dev_server.py   serves the webapp with synthetic state, for UI iteration
Dockerfile.python         agent + dispatch image (multi-stage uv install)
Dockerfile.webapp         slim webapp image (multi-stage npm build + Python runtime)
docker-compose.yml        four services: agent, webapp, dispatch, redis
CLAUDE.md                 system overview; each container directory has its own CLAUDE.md
```

## Notes

- The Silero VAD model is downloaded on first session inside the agent container. To pre-download: `docker compose run --rm agent python -m src.agent download-files`.
- Voices supported by `gpt-realtime`: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar. Change the `voice=` kwarg in [src/agent.py](src/agent.py) if you prefer another.
- The agent only accepts explicit dispatches (`agent_name="briefing-agent"`). The worker will not auto-join arbitrary rooms.
- Webapp port: `WEBAPP_PORT=8765` by default. If you tunnel the webapp (ngrok, Tailscale, etc.) set `WEBAPP_PUBLIC_URL=https://<your-host>` so both the dispatch response and the in-room chat message use the reachable URL.
- Scale concurrent meetings: `docker compose up -d --scale agent=N`. Each agent replica registers with LiveKit as `briefing-agent`; LiveKit distributes job offers across them.
- Scale the live viewer for high-fanout meetings: bump `webapp` replicas (production seam — needs a reverse proxy in front).
