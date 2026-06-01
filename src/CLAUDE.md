# CLAUDE.md — agent container (`src/`)

> **Rule of the house:** any substantial change to the agent's code, [Dockerfile.python](../Dockerfile.python), entry point, environment variables, dependencies, or responsibilities MUST update this CLAUDE.md in the same commit. If you change how the agent is built, run, or talks to Redis / LiveKit / OpenAI, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

This directory holds the agent service's Python code, **except**:
- [webapp/](webapp/) — webapp container, see [webapp/CLAUDE.md](webapp/CLAUDE.md)
- [dispatch_service/](dispatch_service/) — dispatch container, see [dispatch_service/CLAUDE.md](dispatch_service/CLAUDE.md)
- [template_generator/](template_generator/) — template-generator container, see [template_generator/CLAUDE.md](template_generator/CLAUDE.md)
- [console/](console/) — console API container, see [console/CLAUDE.md](console/CLAUDE.md)

The agent is a LiveKit worker. One process per active meeting. The agent process holds `MeetingState` in memory and publishes snapshots to Redis after every mutation.

## File map

```
src/
  agent.py            entry point: parses dispatch metadata, starts AgentSession,
                      wires event handlers, registers shutdown callback.
  harness.py          MeetingState (Pydantic), Transition, prompt builder, schedulers.
  briefing_plan.py    briefing → Template via front-matter or LLM template selection.
  persistence.py      out/<run_id>/ file IO (tree.json, transitions.json, notebook.json, ...).
  tools.py            function_tools the agent calls: record_finding, navigate,
                      frame_meeting, deliver_pyramid_summary, note_followup, end_meeting.
  templates/          Section + SectionKind schema and four shipped meeting trees
                      (requirements, research, eval, generic).
```

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
| `REDIS_URL` | yes (default redis://localhost:6379/0) | message bus to the webapp. |
| `WEBAPP_PUBLIC_URL` | optional (default `http://localhost:8765`) | URL the agent posts to the room chat. Override when tunneling. |

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
