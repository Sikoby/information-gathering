# CLAUDE.md — agent container (`src/`)

> **Rule of the house:** any substantial change to the agent's code, [Dockerfile.python](../Dockerfile.python), entry point, environment variables, dependencies, or responsibilities MUST update this CLAUDE.md in the same commit. If you change how the agent is built, run, or talks to Redis / LiveKit / OpenAI, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

This directory holds the agent service's Python code, **except**:
- [meeting/](meeting/) — meeting API container, see [meeting/CLAUDE.md](meeting/CLAUDE.md)
- [dispatch_service/](dispatch_service/) — dispatch container, see [dispatch_service/CLAUDE.md](dispatch_service/CLAUDE.md)
- [template_generator/](template_generator/) — template-generator container, see [template_generator/CLAUDE.md](template_generator/CLAUDE.md)
- [console/](console/) — console API container, see [console/CLAUDE.md](console/CLAUDE.md)

The agent is a LiveKit worker. One process per active meeting. The agent process holds `MeetingState` in memory and publishes snapshots to Redis after every mutation.

## File map

```
src/
  agent.py            entry point: parses dispatch metadata, starts AgentSession,
                      wires event handlers, starts the note extractor, registers
                      shutdown callback.
  harness.py          MeetingState (Pydantic), Transition, prompt builder, schedulers.
  briefing_plan.py    briefing → Template via front-matter or LLM template selection.
  extraction.py       background finding extractor: drains the record_finding note queue,
                      calls gpt-5-mini (off the event loop) to turn each raw one-line note
                      into a structured, terse finding, inserts it into the tree.
  persistence.py      out/<run_id>/ file IO (tree.json, transitions.json, notebook.json, ...).
  tools.py            function_tools the agent calls: record_finding, navigate,
                      deliver_pyramid_summary, note_followup, end_meeting.
  templates/          Section + SectionKind schema and four shipped meeting trees
                      (requirements, research, eval, generic).
```

## record_finding is fire-and-forget; findings are filed in the background

`record_finding` takes a **single free-text `note`** and returns instantly — it only drops a
`RawNote` on an in-memory `asyncio.Queue` (held on `MeetingState._note_queue`, a `PrivateAttr`
excluded from Redis snapshots). This keeps the realtime voice model from streaming long
multi-field JSON (which truncated/malformed in practice) and from blocking the audio loop on a
tool round trip. A **single background worker** (`extraction.run_extractor`, started in
`agent.entrypoint` after `session.start`) drains the queue and calls **gpt-5-mini** via
`asyncio.to_thread(client.responses.parse, text_format=ExtractedFinding)` to pick the right
QUESTION id and write a **terse** header/body, then inserts the ANSWER and publishes. So
**gpt-5-mini now runs in the live meeting loop**, not only at startup for template selection.
On any API/parse error the worker files the raw note verbatim under `other/q` — findings are
never lost. `_flush_on_shutdown` drains the queue (`queue.join()`, 20s cap) before the final
state snapshot.

## Instructions refresh on transition; history is windowed to the last section

The system prompt is rebuilt **only when the agent navigates** between sections (in the
`navigate` tool, via `MeetingState._agent.update_instructions`), not on a turn counter — the
blocks that change (TREE POSITION, NAVIGATION OPTIONS) only move on a transition, and recent
findings are already visible in the live conversation history. `schedule_time_warning` still
does its own out-of-band refresh + wrap-up nudge at T-5.

On each transition `navigate` also **windows the realtime conversation history to the last
section**: it keeps every item from where the just-ended section began (marker
`MeetingState._section_start_item_id`) and drops older sections via `update_chat_ctx`. Those
older findings already live in the NOTEBOOK snapshot, so this shrinks live context without
losing distilled content. The just-ended section's turns are retained, so a note spoken right
before a move is never orphaned by the prune.

## What it depends on

- **LiveKit Cloud** — persistent WebSocket registers this worker as `briefing-agent`. Job offers arrive over that socket with JSON metadata `{briefing_description, run_id, target_minutes, custom_template?}`. The briefing is always an inline string (no file path); `custom_template`, when present, is used directly instead of template inference.
- **OpenAI** — `gpt-realtime` for voice, `gpt-4o-mini-transcribe` for input transcription, `gpt-5-mini` for offline template selection at meeting start (only when no `custom_template` is supplied and no front-matter is set). The realtime model is configured with explicit `server_vad` turn detection (600ms silence); the plugin default `semantic_vad` was model-based and stalled 30-50s on short utterances. The `AgentSession` defers to this server-side detection, so the local `silero` VAD only drives interruptions.
- **Redis** — writes to `state:<run_id>` and `events:<run_id>` after every state mutation; adds run_id to `runs:active` on start, removes on shutdown.
- **Volumes** — `./out:/app/out` — read-write, per-run artifacts written at shutdown.

## Entry point and command

`Dockerfile.python` builds this image. The compose service runs:

```
python -m src.agent start
```

For local non-container dev, use `uv run python -m src.agent dev` (dev mode is more verbose; `start` is for production).

The agent publishes audio only — its TTS output is sent to the room via LiveKit's default `RoomIO`. No video track, no in-process renderer.

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `LIVEKIT_URL` | yes | wss://... — read by the LiveKit worker framework. |
| `LIVEKIT_API_KEY` | yes | |
| `LIVEKIT_API_SECRET` | yes | |
| `OPENAI_API_KEY` | yes | gpt-realtime + gpt-5-mini. |
| `REDIS_URL` | yes (default redis://localhost:6379/0) | message bus to the meeting API. |
| `MEETING_PUBLIC_URL` | optional (default `http://localhost:8765`) | live-view base URL the agent posts to the room chat. Override when tunneling. |

## Shutdown behavior

`JobContext.add_shutdown_callback(_flush_on_shutdown)` ([agent.py](agent.py)) flushes the final state to `out/<run_id>/` and unregisters the run from Redis. The Dockerfile sets `tini` as PID 1 and the compose service uses `stop_grace_period: 30s` so SIGTERM reaches the Python process and the callback completes.

## Verify changes

After editing anything here:

1. `docker compose build agent`
2. `docker compose up -d`
3. `uv run python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 5`
4. Join the meeting, speak for ~30 seconds, end it.
5. Confirm `out/<run_id>/` is populated with `briefing.md`, `transcript.jsonl`, `tree.json`, `transitions.json`, `notebook.json`, `followups.json`, `meta.json`.
6. Check `docker compose logs agent` for any unhandled exceptions.

## Scaling

The agent container is per-meeting. `docker compose up --scale agent=N` runs N replicas; each registers with LiveKit as `briefing-agent` and LiveKit distributes job offers across them. No coordination among replicas is needed.
