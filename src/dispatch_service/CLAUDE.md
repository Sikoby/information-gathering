# CLAUDE.md — dispatch container (`src/dispatch_service/`)

> **Rule of the house:** any substantial change to the dispatch service's endpoints, [Dockerfile.python](../../Dockerfile.python), entry point, environment variables, dependencies, or how it talks to LiveKit / Redis MUST update this CLAUDE.md in the same commit. If you change the request/response shape or the dispatch flow, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

Long-running aiohttp service that creates LiveKit rooms, mints stakeholder access tokens, and dispatches the agent worker for each new meeting. Replaces what used to be a one-shot CLI ([scripts/dispatch.py](../../scripts/dispatch.py)).

The dispatch service **never connects to the agent directly**. It calls LiveKit's HTTP API; LiveKit Cloud routes the job to one of the agent worker replicas over the persistent WebSocket the agent opened on startup.

## File map

```
src/dispatch_service/
  __init__.py     module marker, doc only.
  __main__.py     all of it — aiohttp app + handlers + LiveKit calls.
```

[scripts/dispatch.py](../../scripts/dispatch.py) is now a thin CLI that POSTs to this service. The compose service shares the agent's [Dockerfile.python](../../Dockerfile.python) (different command, same image).

## Endpoints

| Route | Behavior |
| --- | --- |
| `POST /dispatch` | Body `{briefing_description, target_minutes, custom_template?, run_id?}`. Creates the room + token, calls `AgentDispatchService.create_dispatch`, returns `{run_id, room, target_minutes, join_url, webapp_url}`. |
| `POST /join-token` | Body `{room, name?}`. Mints a fresh voice-join URL for an **existing** `room` under a **unique guest identity** (`guest-<hex>`) — no room creation, no agent dispatch. Returns `{join_url}`. Internal-only (no public ingress); called by the webapp join page after it gates on meeting status + PIN. |
| `GET /runs` | Returns `{active: [run_id...]}` from Redis `SMEMBERS runs:active`. Best-effort; returns 503 if Redis is unreachable. |
| `GET /healthz` | 200 if `LIVEKIT_URL/KEY/SECRET` are present; 503 otherwise. |

### `POST /dispatch` semantics

- `briefing_description` is the briefing as a raw inline markdown string. There is no file-path input — the host `scripts/dispatch.py` reads the file and sends its contents.
- `custom_template` (optional) is a `Template` JSON object; when present it is passed through to the agent and used directly instead of template inference.
- `run_id` may be supplied by the caller (the console reuses its `meeting_id`); if omitted, dispatch generates a UTC ISO timestamp (`%Y-%m-%dT%H-%M-%SZ`).
- The agent worker is dispatched with metadata `{briefing_description, run_id, target_minutes, custom_template?}` as JSON.

## What it depends on

- **LiveKit Cloud** — `RoomService.create_room`, `AgentDispatchService.create_dispatch`. One HTTPS round-trip per dispatch.
- **Redis** — only for `GET /runs`. Dispatch does not depend on Redis being healthy to dispatch a meeting.
- **Volumes** — none. The briefing arrives inline in the request body.

## Entry point and command

```
python -m src.dispatch_service
```

Reads `DISPATCH_PORT` (default 8766), `LIVEKIT_*`, `REDIS_URL`, `WEBAPP_PUBLIC_URL` from env.

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `LIVEKIT_URL` | yes | Used to build the meet.livekit.io join URL and to call the LiveKit API. |
| `LIVEKIT_API_KEY` | yes | |
| `LIVEKIT_API_SECRET` | yes | |
| `WEBAPP_PUBLIC_URL` | optional (default `http://localhost:8765`) | Used to build the webapp URL returned to the caller. Override when tunneling. |
| `REDIS_URL` | optional (default `redis://localhost:6379/0`) | Only needed for `GET /runs`. |
| `DISPATCH_PORT` | optional (default 8766) | aiohttp listen port. |

## Verify changes

```
docker compose build dispatch
docker compose up -d
curl http://localhost:8766/healthz                                        # → ok
curl -s -X POST http://localhost:8766/dispatch \
     -H 'Content-Type: application/json' \
     -d '{"briefing_description":"# Test\n\nDiscuss the rollout plan.","target_minutes":5}'
```

Or use the CLI: `uv run python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 5`.

## Scaling

Stateless — any replica can serve any request. Production seam is identical to webapp: bump `deploy.replicas` and put a load balancer in front.
