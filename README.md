# Briefing-driven voice meeting agent

A Python prototype that joins a LiveKit room as a senior consultant, runs a meeting based on a free-form markdown briefing, and writes a transcript plus structured findings to disk. The briefing is the only thing that changes between meetings.

## Setup

Requires Python 3.11+, a LiveKit Cloud project, and an OpenAI API key.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Fill in `.env`:

| Variable | Source |
| --- | --- |
| `LIVEKIT_URL` | LiveKit Cloud project settings (wss://your-project.livekit.cloud) |
| `LIVEKIT_API_KEY` | LiveKit Cloud API key |
| `LIVEKIT_API_SECRET` | LiveKit Cloud API secret |
| `OPENAI_API_KEY` | platform.openai.com |

## Run a meeting

Two terminals.

Terminal 1 (worker, leave running):

```
python -m src.agent dev
```

The first run downloads the Silero VAD weights (a few seconds).

Terminal 2 (dispatch):

```
python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
```

The dispatch script prints a `https://meet.livekit.io/custom?...` URL. Open it in a browser, allow the mic, and join. The agent will speak first within a couple of seconds. When the agent calls `end_meeting`, the worker flushes the run to `out/<run_id>/`.

## Swap briefings

Point `--briefing` at any markdown file. No code changes per meeting.

```
python scripts/dispatch.py --briefing briefings/02_q1_satisfaction.md --target-minutes 25
python scripts/dispatch.py --briefing briefings/03_migration_walkthrough.md --target-minutes 20
```

Three briefings ship in this repo as examples: a data warehouse requirements interview, a Q1 satisfaction probe, and a migration timeline walkthrough.

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
2. `src/agent.py` is the worker entrypoint. It reads the metadata, copies the briefing into the run directory, runs `src/objectives.py` (one offline `openai.responses.parse` call) to turn the briefing into a typed `list[Objective]`, and constructs a `MeetingState` (Pydantic model in `src/harness.py`).
3. The `MeetingState` is attached to `AgentSession.userdata`, so every `function_tool` in `src/tools.py` receives it via `RunContext[MeetingState].userdata`. This is the LangGraph-style state object for this project; the OpenAI Realtime API itself has no server-held state.
4. The agent runs on `gpt-realtime` with voice `cedar`. `input_audio_transcription` is enabled with `gpt-4o-mini-transcribe`, and the LiveKit `conversation_item_added` event handler appends both user and agent utterances to `transcript.jsonl`.
5. Every four user turns, the agent's system prompt is refreshed via `agent.update_instructions(...)` so the objective tracker stays in front of the model. Five minutes before the target end, a scheduled task injects a wrap-up nudge.
6. On any close path (`end_meeting` tool, user leaves, error), `JobContext.add_shutdown_callback` flushes the full state to disk.

## Project layout

```
briefings/                three example briefings
src/
  agent.py                worker entrypoint, event wiring, time warning
  harness.py              MeetingState (Pydantic) and the prompt builder
  objectives.py           briefing -> list[Objective] via Responses API
  persistence.py          out/<run_id>/ file IO
  tools.py                four function_tools
scripts/
  dispatch.py             create room + token + dispatch
  extract_objectives.py   offline test of the extraction step
```

## Notes

- The Silero VAD model is downloaded on first session. To pre-download: `python -m src.agent download-files`.
- Voices supported by `gpt-realtime`: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar. Change the `voice=` kwarg in `src/agent.py` if you prefer another.
- The agent only accepts explicit dispatches (`agent_name="briefing-agent"`). The worker will not auto-join arbitrary rooms.
