# Briefing-driven voice meeting agent

A Python prototype that joins a LiveKit room as a senior consultant, runs a meeting based on a free-form markdown briefing, and writes a transcript plus structured findings to disk. A live read-only webapp shows what the agent has captured so far. The briefing is the only thing that changes between meetings.

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node 18+ with `npm` (for the webapp bundle)
- A LiveKit Cloud project and an OpenAI API key

## One-time setup

```
uv sync                                   # installs Python deps into .venv
cp .env.example .env                      # then edit .env (see table below)
(cd frontend && npm install && npm run build)
```

Fill in `.env`:

| Variable | Source |
| --- | --- |
| `LIVEKIT_URL` | LiveKit Cloud project settings (wss://your-project.livekit.cloud) |
| `LIVEKIT_API_KEY` | LiveKit Cloud API key |
| `LIVEKIT_API_SECRET` | LiveKit Cloud API secret |
| `OPENAI_API_KEY` | platform.openai.com |

> No `uv`? Fallback: `python3 -m venv .venv && source .venv/bin/activate && pip install -e .` then run the commands below without the `uv run` prefix.

## Run a meeting

Two terminals.

**Terminal 1** — worker (leave running, also serves the webapp on :8765):

```
uv run python -m src.agent dev
```

The first run downloads the Silero VAD weights (a few seconds).

**Terminal 2** — dispatch one meeting:

```
uv run python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
```

The dispatch terminal prints a `https://meet.livekit.io/custom?...` URL and a `http://localhost:8765/<run_id>/` URL.

1. Open the `meet.livekit.io` URL in a browser, allow the mic, and join. The agent speaks first within a second or two.
2. As soon as you join the room, the agent drops the webapp URL into the room's chat panel — click it (or open the localhost URL from terminal 2) to watch the live cockpit: meeting title, agenda timeline, notebook entries, objectives tracker, and follow-ups updating as you talk.
3. When the agent calls `end_meeting` (or you leave), the worker flushes the run to `out/<run_id>/`.

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
uv run python scripts/preview_dev_server.py
```

Opens at `http://localhost:8767/dev/` with a fake mid-meeting state. Useful for iterating on the frontend — see [frontend/CLAUDE.md](frontend/CLAUDE.md) and [frontend/DESIGN.md](frontend/DESIGN.md).

## Briefings vs templates

These are two different things and the difference matters when you write your own meetings.

A **briefing** (in `briefings/`) is a free-form markdown file describing *this specific meeting* — its purpose, the topics to cover, any time-budget or tone hints. Briefings are what change between meetings; the agent reads exactly one per run. A briefing typically opens with `# Briefing: <Title>` — that title is what the webapp shows as the meeting title.

A **template** (in `src/templates/`) is a reusable, structured meeting *shape* defined in Python. It declares:

- the **notebook sections** the agent files findings into — e.g. for `requirements`: pain points, must-haves, nice-to-haves, constraints, success metrics, stakeholders, dependencies;
- the **phases** the meeting moves through over time — e.g. for `requirements`: Rapport → Define → Prioritise → Wrap, each with a goal sentence and a target fraction of the meeting.

Four templates ship: `requirements`, `research`, `eval`, `generic`.

When a meeting starts, [src/objectives.py](src/objectives.py) reads the briefing and:

1. picks a template — either from a YAML front-matter `template: <name>` block at the top of the briefing, or by asking `gpt-5-mini` which of the four templates best fits the briefing text;
2. extracts three to six substantive objectives the consultant must cover.

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
| `objectives.json` | Structured objectives extracted from the briefing (gpt-5-mini) |
| `transcript.jsonl` | One JSON object per utterance (`ts`, `role`, `text`) |
| `findings.json` | Whatever the agent recorded via `record_finding` |
| `followups.json` | Whatever the agent noted via `note_followup` |
| `meta.json` | run_id, briefing_path, target_minutes, started_at, ended_at, end_reason, final tracker, turn count |

## Architecture

1. `scripts/dispatch.py` creates a LiveKit room, mints a stakeholder access token, prints the join URL, and calls `AgentDispatchService.CreateDispatch` with JSON metadata `{briefing_path, run_id, target_minutes}`.
2. `src/agent.py` is the worker entrypoint. It reads the metadata, copies the briefing into the run directory, runs `src/objectives.py` (one offline `openai.responses.parse` call) to pick a template and extract a typed `list[Objective]`, and constructs a `MeetingState` (Pydantic model in `src/harness.py`). The same process also starts the read-only webapp ([src/webapp/](src/webapp/)) on `WEBAPP_PORT` and posts a clickable link to the room's chat (`lk.chat`) when a participant joins.
3. The `MeetingState` is attached to `AgentSession.userdata`, so every `function_tool` in `src/tools.py` receives it via `RunContext[MeetingState].userdata`. This is the LangGraph-style state object for this project; the OpenAI Realtime API itself has no server-held state.
4. The agent runs on `gpt-realtime` with voice `cedar`. `input_audio_transcription` is enabled with `gpt-4o-mini-transcribe`, and the LiveKit `conversation_item_added` event handler appends both user and agent utterances to `transcript.jsonl`.
5. Every four user turns, the agent's system prompt is refreshed via `agent.update_instructions(...)` so the objective tracker stays in front of the model. Five minutes before the target end, a scheduled task injects a wrap-up nudge.
6. After every state mutation (turn count, notebook entry, objective status, phase change, followup), `webapp.publish(...)` pushes the new `MeetingState` snapshot to any SSE subscribers — that's how the live viewer updates without polling.
7. On any close path (`end_meeting` tool, user leaves, error), `JobContext.add_shutdown_callback` flushes the full state to disk.

## Project layout

```
briefings/                three example briefings (markdown)
src/
  agent.py                worker entrypoint, event wiring, time warning
  harness.py              MeetingState (Pydantic) and the prompt builder
  objectives.py           briefing -> (template, objectives) via Responses API
  persistence.py          out/<run_id>/ file IO
  tools.py                function_tools the agent calls during the meeting
  templates/              reusable meeting shapes (requirements, research, eval, generic)
  webapp/                 aiohttp server that streams MeetingState over SSE
frontend/                 React + Vite read-only live viewer (DESIGN.md, CLAUDE.md)
scripts/
  dispatch.py             create room + token + dispatch
  preview_dev_server.py   webapp with a synthetic state, for UI iteration
  extract_objectives.py   offline test of the extraction step
```

## Notes

- The Silero VAD model is downloaded on first session. To pre-download: `uv run python -m src.agent download-files`.
- Voices supported by `gpt-realtime`: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar. Change the `voice=` kwarg in [src/agent.py](src/agent.py) if you prefer another.
- The agent only accepts explicit dispatches (`agent_name="briefing-agent"`). The worker will not auto-join arbitrary rooms.
- Webapp port: `WEBAPP_PORT=8765` by default. If you tunnel the webapp (ngrok, Tailscale, etc.) set `WEBAPP_PUBLIC_URL=https://<your-host>` so both the dispatch terminal and the in-room chat message use the reachable URL.
