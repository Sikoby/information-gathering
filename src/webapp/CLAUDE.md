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
                  get_state_json, get_client, events_channel, ping (webapp-side).
  server.py       aiohttp routes — /healthz, /{run_id}/, /{run_id}/state,
                  /{run_id}/events, /assets/*.
```

The agent imports `from . import webapp` and calls `webapp.publish(state)` etc. The webapp container only runs `__main__.py` → `server.py`, which uses the read-only helpers in `publisher.py`. The class-based `StatePublisher` of earlier revisions is gone.

## What it depends on

- **Redis** — read-only on the hot path. Reads `state:<run_id>` for `/state`, subscribes to `events:<run_id>` for `/events`. Calls `PING` for `/healthz`.
- **Frontend bundle** — `frontend/dist/` baked into the image at build time. The aiohttp server serves `index.html` for the SPA root and static assets from `/assets/*`.

No LiveKit, no OpenAI, no pydantic in the slim image. If you find yourself needing to import `harness.MeetingState` here, stop — the data is JSON and should stay that way for this service.

## Routes

| Route | Behavior |
| --- | --- |
| `GET /healthz` | 200 if Redis ping succeeds; 503 otherwise. |
| `GET /{run_id}/` | Serves `frontend/dist/index.html` (404 if no `state:<run_id>` in Redis). |
| `GET /{run_id}/state` | Returns the current snapshot JSON (404 if unknown). |
| `GET /{run_id}/events` | SSE stream. Sends the current snapshot immediately, then forwards every `events:<run_id>` message. Keepalive every 15s. |
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
