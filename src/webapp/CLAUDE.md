# CLAUDE.md — webapp container (`src/webapp/`)

> **Rule of the house:** any substantial change to the webapp's routes, [Dockerfile.webapp](../../Dockerfile.webapp), entry point, environment variables, dependencies, or the Redis schema this service reads MUST update this CLAUDE.md in the same commit. If you change how the webapp is built, run, scaled, or talks to Redis, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

The webapp container serves the live meeting viewer over HTTP + SSE. It is **stateless**: every request is satisfied by Redis (`GET state:<run_id>` or `SUBSCRIBE events:<run_id>`) or by a static file from the bundled frontend.

It deliberately knows nothing about `MeetingState`, LiveKit, or OpenAI — the snapshot is opaque JSON. This is what allows multiple webapp replicas to serve the same meeting with no sticky sessions.

## File map

```
src/webapp/
  __init__.py     re-exports publish/register/unregister for the agent.
  __main__.py     `python -m src.webapp` entry point — starts aiohttp on $WEBAPP_PORT.
  publisher.py    Redis client. publish/register/unregister (agent-side);
                  get_state_json, get_meeting_json, get_client, events_channel,
                  ping (webapp-side).
  server.py       aiohttp routes — /healthz, /{run_id}/, /{run_id}/state,
                  /{run_id}/events, /join/{meeting_id}, /assets/*.
```

The agent imports `from . import webapp` and calls `webapp.publish(state)` etc. The webapp container only runs `__main__.py` → `server.py`, which uses the read-only helpers in `publisher.py`. The class-based `StatePublisher` of earlier revisions is gone.

## What it depends on

- **Redis** — read-only. Reads `state:<run_id>` for `/state`, subscribes to `events:<run_id>` for `/events`, calls `PING` for `/healthz`. The join page additionally reads the **console-owned** `meeting:<id>` (status, room, `join_pin`, `scheduled_at`) — a read-only cross-read, the mirror image of the console reading the agent-owned `state:*`. The webapp never writes `meeting:*`.
- **Dispatch** — the join page `POST`s `/join-token` (server-to-server over the internal network, `DISPATCH_URL`) to mint a voice-join token. This is the webapp's only outbound HTTP call.
- **Frontend bundle** — `frontend/dist/` baked into the image at build time. The aiohttp server serves `index.html` for the SPA root and static assets from `/assets/*`.

No LiveKit, no OpenAI, no pydantic in the slim image — the join page reads `meeting:<id>` as a plain dict (only scalar fields) and delegates token-minting to dispatch, so LiveKit creds stay out of this service. If you find yourself needing to import `harness.MeetingState` here, stop — the data is JSON and should stay that way for this service.

## Routes

| Route | Behavior |
| --- | --- |
| `GET /healthz` | 200 if Redis ping succeeds; 503 otherwise. |
| `GET /{run_id}/` | Serves `frontend/dist/index.html` (404 if no `state:<run_id>` in Redis). |
| `GET /{run_id}/state` | Returns the current snapshot JSON (404 if unknown). |
| `GET /{run_id}/events` | SSE stream. Sends the current snapshot immediately, then forwards every `events:<run_id>` message. Keepalive every 15s. |
| `GET /join/{meeting_id}` | Public, server-rendered HTML join page for an invited meeting. Reads the console-owned `meeting:<id>`. Before the meeting is `running` it shows a "starts at …" / "ended" page (blocked); once `running` it shows a PIN form. |
| `POST /join/{meeting_id}` | Verifies the submitted PIN against the record's `join_pin`; on match, calls dispatch `POST /join-token` (internal, `DISPATCH_URL`) to mint a fresh voice-join token and `302`-redirects into the LiveKit room. Wrong PIN re-renders the form. |
| `GET /assets/*` | Vite-built static bundles. |
| `GET /favicon.ico` | 404. |

## Entry point and command

```
python -m src.webapp
```

Defined in [__main__.py](__main__.py). Reads `WEBAPP_PORT` (default 8765) and `REDIS_URL` (default `redis://localhost:6379/0`).

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `REDIS_URL` | yes (default `redis://localhost:6379/0`) | message bus. |
| `WEBAPP_PORT` | optional (default 8765) | aiohttp listen port. |
| `DISPATCH_URL` | optional (default `http://dispatch:8766`) | internal dispatch base; the join page `POST`s `/join-token` here to mint a voice-join token. |

## Verify changes

After editing anything here:

1. `docker compose build webapp`
2. `docker compose up -d`
3. `curl http://localhost:8765/healthz` → `ok`.
4. Start a meeting via `scripts/dispatch.py`. Open the printed webapp URL.
5. Confirm the viewer renders, updates as you speak, and reconnects cleanly after `docker compose restart webapp` mid-meeting.

Slim-image check (no domain deps leaked in):

```
docker compose exec webapp python -c "import pydantic"   # should fail
docker compose exec webapp python -c "import aiohttp, redis"  # should succeed
```

## Scaling

Stateless. Run N replicas with a load balancer in front. Every replica reads the same `state:<run_id>` and subscribes to the same `events:<run_id>` — no sticky sessions, no leader election.

Production seam: add `deploy.replicas: N` in compose, or a k8s `Deployment` with HPA tied to SSE connection count.
