# CLAUDE.md — meeting API container (`src/meeting/`)

> **Rule of the house:** any substantial change to the meeting API's routes, [Dockerfile.meeting](../../Dockerfile.meeting), entry point, environment variables, dependencies, or the Redis schema this service reads MUST update this CLAUDE.md in the same commit. If you change how the API is built, run, scaled, or talks to Redis / dispatch, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

The `meeting` container is the **JSON API** for the participant-facing tier. It is the API half of a console-style pair: the nginx `meeting-frontend` container serves the SPA (live view + join) and reverse-proxies `/api` here. This service serves **no static files and no HTML** — only data under `/api/*` plus `/healthz`.

It is **stateless**: every request is satisfied by Redis (`GET state:<run_id>` or `SUBSCRIBE events:<run_id>`), a read of the console-owned `meeting:<id>` record (for the join flow), or one outbound call to dispatch (to mint a voice-join token).

It deliberately knows nothing about `MeetingState`, LiveKit, or OpenAI — the snapshot is opaque JSON. This is what allows multiple replicas to serve the same meeting with no sticky sessions.

## File map

```
src/meeting/
  __init__.py     re-exports publish/register/unregister for the agent.
  __main__.py     `python -m src.meeting` entry point — starts aiohttp on $MEETING_PORT.
  publisher.py    Redis client. publish/register/unregister (agent-side);
                  get_state_json, get_meeting_json, get_client, events_channel,
                  ping (API-side).
  server.py       aiohttp routes — /healthz + /api/* (state, events, join).
```

The agent imports `from . import meeting` and calls `meeting.publish(state)` etc. The container only runs `__main__.py` → `server.py`, which uses the read-only helpers in `publisher.py`.

## What it depends on

- **Redis** — read-only. Reads `state:<run_id>` for state, subscribes to `events:<run_id>` for the SSE stream, calls `PING` for `/healthz`. The join routes additionally read the **console-owned** `meeting:<id>` (status, room, `join_pin`, `scheduled_at`) — a read-only cross-read, the mirror image of the console reading the agent-owned `state:*`. This service never writes `meeting:*`.
- **Dispatch** — `POST /api/join/{id}/token` `POST`s to dispatch `/join-token` (server-to-server over the internal network, `DISPATCH_URL`) to mint a fresh voice-join token. This is the service's only outbound HTTP call.

No LiveKit, no OpenAI, no pydantic in the slim image — the join flow reads `meeting:<id>` as a plain dict (only scalar fields) and delegates token-minting to dispatch, so LiveKit creds stay out of this service. If you find yourself needing to import `harness.MeetingState` here, stop — the data is JSON and should stay that way.

## Routes

All data routes are under `/api/*` (nginx proxies that prefix here). `/healthz` is unprefixed.

| Route | Behavior |
| --- | --- |
| `GET /healthz` | 200 if Redis ping succeeds; 503 otherwise. |
| `GET /api/runs/{run_id}/state` | Returns the current snapshot JSON (404 if unknown). |
| `GET /api/runs/{run_id}/events` | SSE stream. Sends the current snapshot immediately, then forwards every `events:<run_id>` message. Keepalive every 15s. Sets `X-Accel-Buffering: no` so nginx streams it. |
| `GET /api/join/{meeting_id}` | Public join **status**: `{status, scheduled_at, ready}` where `ready = status=="running" and bool(room)`. **Never** leaks `join_pin` or `room`. 404 `{status:"not_found"}` on unknown id. |
| `POST /api/join/{meeting_id}/token` | Body `{pin}`. Re-checks `ready`, compares the PIN to the record's `join_pin`; on match calls dispatch `/join-token` and returns `{join_url}`. Wrong PIN → `{error}` 403; not joinable → 409; dispatch failure → `{error}` 502. |

## Entry point and command

```
python -m src.meeting
```

Defined in [__main__.py](__main__.py). Reads `MEETING_PORT` (default 8771) and `REDIS_URL` (default `redis://localhost:6379/0`).

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `REDIS_URL` | yes (default `redis://localhost:6379/0`) | message bus. |
| `MEETING_PORT` | optional (default 8771) | aiohttp listen port. |
| `DISPATCH_URL` | optional (default `http://dispatch:8766`) | internal dispatch base; `/api/join/{id}/token` `POST`s `/join-token` here to mint a voice-join token. |

## Verify changes

After editing anything here:

1. `docker compose build meeting && docker compose up -d`
2. `curl http://localhost:8771/healthz` → `ok` (direct), and `curl http://localhost:8765/healthz` (through the nginx `meeting-frontend`) → `ok`.
3. Start a meeting via `scripts/dispatch.py`. Open the printed live-view URL (`:8765/<run_id>/`).
4. Confirm the viewer renders, updates as you speak, and reconnects cleanly after `docker compose restart meeting` mid-meeting. Confirm the SSE stream isn't buffered by nginx (tokens appear live).

Slim-image check (no domain deps leaked in):

```
docker compose exec meeting python -c "import pydantic"   # should fail
docker compose exec meeting python -c "import aiohttp, redis"  # should succeed
```

## Scaling

Stateless. Run N replicas with a load balancer in front. Every replica reads the same `state:<run_id>` and subscribes to the same `events:<run_id>` — no sticky sessions, no leader election.

Production seam: add `deploy.replicas: N` in compose, or a k8s `Deployment` with HPA tied to SSE connection count.
