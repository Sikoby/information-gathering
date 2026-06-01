# Briefing-driven voice meeting agent

A Python prototype that joins a LiveKit room as a senior consultant, runs a meeting based on a free-form prompt or markdown briefing, and writes a transcript plus structured findings to disk. A live read-only webapp shows what the agent has captured so far. A separate **meeting console** lets a non-developer create a meeting from a prompt — generate and edit its template, start it, and track its lifecycle.

The system runs as seven containers — agent, webapp, dispatch, template-generator, console, console-frontend, redis — brokered by a Redis pub/sub spine. See [CLAUDE.md](CLAUDE.md) for the architecture overview.

## Prerequisites

- Docker + Docker Compose (the recommended way to run everything)
- A LiveKit Cloud project and an OpenAI API key
- For host-side tooling: Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (the CLI scripts under `scripts/` use only the stdlib, but `uv` makes installs painless if you also want to run things locally)
- For frontend iteration: Node 20+ and npm (the repo is an npm workspace — `npm install` at the root pulls in `shared`, `frontend`, and `console-frontend`)

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

## Run a meeting (console — recommended)

```
docker compose up -d
```

Open the **meeting console** at [http://localhost:8769](http://localhost:8769). From there:

1. Click **New meeting**, give it a title, write a free-form prompt describing the meeting (purpose, topics, tone), and pick a target length. Submit.
2. The console kicks off the template-generator (impl+critique loop, 1–4 minutes). The meeting sits in **Planned** while the template generates. You can edit the title, prompt, target length, or the generated template, and re-generate if you want a different shape.
3. When the template is **ready**, click **Start meeting**. The console calls dispatch, which creates the LiveKit room and dispatches the agent. The meeting moves to **Running** and the console shows the join URL plus the live-viewer URL.
4. Open the LiveKit join URL in a browser, allow the mic, and join. The agent speaks first within a second or two.
5. As soon as you join the room, the agent drops the live-viewer URL into the room's chat panel — click it to watch the cockpit: meeting title, breadcrumb of where the conversation is, agenda timeline, the live notebook tree (questions and the answers the agent has captured), the typed-transition log, and follow-ups — all updating as you talk.
6. When the agent calls `end_meeting` (or you leave), the worker flushes the run to `out/<meeting_id>/` and the console's reconcile loop moves the meeting to **Done**.

Ports: console SPA `8769`, console API `8770`, live viewer `8765`, dispatch `8766`, template-generator `8768`.

## Run a meeting (developer CLI)

For quick iteration against a pre-written markdown briefing — no template generation, no console record:

```
docker compose up -d
uv run python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
```

The dispatch CLI POSTs to the dispatch container at `http://localhost:8766/dispatch` and prints a `https://meet.livekit.io/custom?...` URL and a `http://localhost:8765/<run_id>/` URL. The rest of the meeting flow is identical to the console path; only the entry point differs.

Logs from any service: `docker compose logs -f agent` (or `webapp`, `dispatch`, `template-generator`, `console`, `console-frontend`, `redis`).

## Swap briefings (CLI path)

Point `--briefing` at any markdown file. No code changes per meeting.

```
uv run python scripts/dispatch.py --briefing briefings/02_q1_satisfaction.md --target-minutes 25
uv run python scripts/dispatch.py --briefing briefings/03_migration_walkthrough.md --target-minutes 20
```

Three briefings ship as examples: a data warehouse requirements interview, a Q1 satisfaction probe, and a migration timeline walkthrough.

## Preview the live viewer without a real meeting

If you just want to see the live-viewer UI with synthetic state (no LiveKit, no microphone):

```
docker compose up -d redis             # the preview also reads state from Redis
uv run python scripts/preview_dev_server.py
```

Opens at `http://localhost:8767/dev/` with a fake mid-meeting state. Useful for iterating on the viewer — see [frontend/CLAUDE.md](frontend/CLAUDE.md) and [frontend/DESIGN.md](frontend/DESIGN.md).

For console SPA iteration, run a Vite dev server that proxies `/api` to a local console API:

```
docker compose up -d console           # backend on :8770
npm run dev -w console-frontend        # SPA on the port Vite picks
```

## Briefings, prompts, and templates

The agent runs on **two inputs**: a free-form description of *this meeting* (a "briefing" / "prompt"), and a structured "template" describing the *shape* of meeting it is.

A **briefing/prompt** describes *this specific meeting* — its purpose, the topics to cover, any time-budget or tone hints. It's what changes between meetings.

- The **console** takes the prompt directly from the UI form.
- The **CLI** reads it from a markdown file in `briefings/`. A briefing typically opens with `# Briefing: <Title>` — that title is what the webapp shows as the meeting title.

A **template** is a reusable, structured meeting *shape*. It is one tree of `Section` nodes discriminated by `kind`:

- `meeting` — the root.
- `topic` — a thematic unit. A top-level topic with a `target_fraction` set is a "phase"; the set of those is the agenda and their fractions must sum to ~1.0.
- `question` — a specific thing the agent wants to find out. The agent navigates between questions and records ANSWERs under them as findings arrive.
- `answer` — runtime-only, written by `record_finding` during the meeting.

E.g. for `requirements` the agenda is `Rapport → Define → Prioritise → Wrap`. Under `Define` sit topics like `pain_points`, `constraints`, `dependencies`, each owning 2–3 questions. Under `pain_points` there's a deeper topic `severity` with its own questions — depth is capped at five.

Templates come from one of three places:

1. **Generated by the template-generator** from the console prompt — an LLM impl+critique loop (1–4 min) that proposes a `Template`, critiques it, revises, and repeats. The user can edit the generated result before starting. This is the console path.
2. **Inferred from the briefing** at meeting start by [src/briefing_plan.py](src/briefing_plan.py), which asks `gpt-5-mini` which of the four built-in templates best fits. This is the CLI path when no front-matter is set.
3. **Pinned by front-matter** in a CLI briefing:

   ```
   ---
   template: requirements
   ---
   # Briefing: Data Warehouse Requirements Interview
   ...
   ```

Four built-in templates ship in [src/templates/](src/templates/): `requirements`, `research`, `eval`, `generic`. The console's generated templates are passed to the agent **inline through dispatch metadata** — they are not registered into the built-in dict.

You can also drive the template-generator from the host:

```
uv run python scripts/generate_template.py \
    --description "Design review for the data ingestion pipeline rewrite" \
    --reference requirements --max-iterations 3
```

In plain English: **the prompt/briefing is the *what* (this conversation), the template is the *how* (the structure the agent runs it in).**

## Output per run

`out/<run_id>/`:

| File | Contents |
| --- | --- |
| `briefing.md` | Copy of the briefing/prompt the agent used |
| `transcript.jsonl` | One JSON object per utterance (`ts`, `role`, `text`) |
| `tree.json` | Canonical — the full Section tree at end of meeting (template structure + ANSWER nodes + closing TOPIC) |
| `transitions.json` | Chronological list of typed navigation moves (open/drill_down/zoom_out/sibling/revisit) |
| `notebook.json` | Derived view over `tree.json` — answers grouped by parent question id |
| `followups.json` | Whatever the agent noted via `note_followup` |
| `meta.json` | run_id, briefing_path, target_minutes, started_at, ended_at, end_reason, current section + visited sections, turn count |

When the meeting was started from the console, `run_id` equals the `meeting_id` registered in Redis under `meeting:<id>`. Generated templates are also archived to `templates_generated/` on the host.

## Architecture

Seven containers, brokered by Redis:

| Container | Role |
| --- | --- |
| `console-frontend` | nginx. Serves the meeting-console SPA on `:8769`; reverse-proxies `/api` to `console`. |
| `console` | aiohttp JSON API on `:8770`. Owns the `meeting:*` registry in Redis; drives template generation; starts meetings; tracks the Planned → Running → Done lifecycle. Stateless — safe to scale. |
| `template-generator` | aiohttp service on `:8768` exposing `POST /generate`. Runs an OpenAI impl+critique loop that proposes a `Template`, critiques it, revises, and returns the approved result (and a copy in `templates_generated/`). |
| `dispatch` | aiohttp service on `:8766` exposing `POST /dispatch`. Creates the LiveKit room, mints the stakeholder access token, and calls `AgentDispatchService.CreateDispatch` with JSON metadata `{briefing_description, run_id, target_minutes, custom_template?}`. |
| `agent` | LiveKit worker. Long-running; registers with LiveKit as `briefing-agent` and waits for job offers. On each job: reads metadata; if no `custom_template` is supplied, runs `src/briefing_plan.py` (one offline `openai.responses.parse` call) to pick one of the four built-in templates; builds a `MeetingState` over a deep-copied Section tree; runs the meeting on `gpt-realtime` with voice `cedar`; writes `out/<run_id>/` at shutdown. |
| `webapp` | aiohttp + SSE on `:8765`. Reads `state:<run_id>` from Redis on `GET /<run_id>/state`; subscribes to `events:<run_id>` for `GET /<run_id>/events`. Stateless live viewer. |
| `redis` | Message bus and registry. Holds `state:<run_id>` (24h TTL), broadcasts on `events:<run_id>`, persists the `meeting:*` registry via AOF on a named volume. |

Data flow for a console-created meeting:

1. Browser hits the console-frontend (nginx). The SPA `POST /api/meetings` is proxied to the console API. The console writes a `planned` record to `meeting:<id>`, spawns a background generation task, and returns `201` immediately.
2. The generation task calls template-generator `POST /generate`. The result is written back into the meeting record under a `generation_seq` guard so a concurrent edit is never clobbered. The record moves to `template_status: ready`.
3. The user clicks **Start**. The console `POST /dispatch` (with `meeting_id` reused as `run_id`) to the dispatch container; dispatch calls LiveKit Cloud and returns the join URLs.
4. LiveKit Cloud pushes the job offer to one of the agent worker replicas over its WebSocket.
5. The agent invokes `entrypoint(ctx)`, parses metadata, builds `MeetingState` over a deep-copied Section tree, and calls `await webapp.register(state)` — that writes the initial snapshot to Redis.
6. The agent runs the meeting on `gpt-realtime`. `MeetingState` is attached to `AgentSession.userdata`, so every `function_tool` in `src/tools.py` receives it via `RunContext[MeetingState].userdata`. `input_audio_transcription` (`gpt-4o-mini-transcribe`) feeds the LiveKit `conversation_item_added` event handler that appends to `transcript.jsonl`.
7. Every four user turns, the system prompt is refreshed via `agent.update_instructions(...)` so the current tree position, navigation options, and notebook stay in front of the model. Five minutes before the target end, a scheduled task injects a wrap-up nudge toward `deliver_pyramid_summary`.
8. After every state mutation (turn count, ANSWER appended, navigation, framing, followup), the agent calls `await webapp.publish(state)` — that writes `state:<run_id>` and publishes on `events:<run_id>`. Any browser connected to the live viewer via SSE receives the new snapshot.
9. On any close path (`end_meeting` tool, user leaves, error), `JobContext.add_shutdown_callback` flushes the full state to `out/<run_id>/` and removes the run from `runs:active`. The console's reconcile loop notices `end_reason` on the next tick and moves the meeting record to `done`.

The CLI path skips steps 1–2: `scripts/dispatch.py` reads a briefing file from disk and calls `POST /dispatch` directly. The console is bypassed entirely.

The agent has **no direct connection** to the webapp, console, dispatch, or template-generator — everything internal goes through Redis (state pub/sub + registry) or LiveKit Cloud (room dispatch). See [CLAUDE.md](CLAUDE.md) for the diagram.

## Project layout

```
briefings/                three example briefings (markdown), for the CLI path
src/
  agent.py                LiveKit worker entrypoint (agent container)
  harness.py              MeetingState (Pydantic), Transition, prompt builder
  briefing_plan.py        briefing -> Template via front-matter or Responses API
  persistence.py          out/<run_id>/ file IO (tree.json, transitions.json, ...)
  tools.py                function_tools: record_finding, navigate, frame_meeting,
                          deliver_pyramid_summary, note_followup, end_meeting
  templates/              built-in meeting shapes (requirements, research, eval, generic)
                          and the Section/SectionKind schema
  webapp/                 aiohttp + Redis-backed SSE server (webapp container)
  dispatch_service/       aiohttp service that creates rooms + dispatches agents (dispatch container)
  template_generator/     aiohttp service running the impl+critique template loop (template-generator container)
  console/                aiohttp meeting-console API + lifecycle (console container)
tests/                    pytest suite over the schema, transitions, and tools
frontend/                 React + Vite read-only live viewer (built into webapp image)
console-frontend/         React + Vite meeting-console SPA (built into console-frontend image)
shared/                   @ig/ui — shared component library + Section tree helpers
scripts/
  dispatch.py             thin CLI that POSTs to the dispatch container
  generate_template.py    thin CLI that POSTs to the template-generator container
  preview_dev_server.py   serves the live viewer with synthetic state, for UI iteration
templates_generated/      host volume — every generated template is archived here
out/                      host volume — per-run artifacts (one directory per meeting)
Dockerfile.python         agent + dispatch + template-generator image (multi-stage uv install)
Dockerfile.webapp         slim live-viewer image (multi-stage npm build + Python runtime)
Dockerfile.console        slim console API image (Python, no livekit/openai)
Dockerfile.console-frontend  nginx image serving the console SPA + proxying /api
docker-compose.yml        seven services: agent, webapp, dispatch, template-generator,
                          console, console-frontend, redis
package.json              npm workspace root (shared, frontend, console-frontend)
CLAUDE.md                 system overview; each container directory has its own CLAUDE.md
```

## Production deploy (Hetzner + Cloudflare Tunnel)

Single-VM deploy with Cloudflare in front for TLS and Access auth on the console. Outbound-only — no inbound ports on the VM beyond SSH. Cost ~€5/mo.

```
browser ─ TLS ─▶ Cloudflare edge ──(Access policy on console.*)──▶ Cloudflare Tunnel
                                                                       │ (outbound)
                                                                       ▼
                                                            cloudflared (on VM)
                                                              │ docker network
                                                              ├─▶ console-frontend → console
                                                              └─▶ webapp
```

Auth sits on `console.example.com` only. Anyone with a link can open `meeting.example.com` to watch a meeting they're a participant in — same posture as a Google Docs share link. The cost-risk surface (creating meetings, spending OpenAI + LiveKit budget) is on the console, and that's walled off.

The overlay [docker-compose.prod.yml](docker-compose.prod.yml) closes all host port mappings (only SSH stays open) and adds a `cloudflared` service that reaches `console-frontend:80` and `webapp:8765` over the internal docker network.

### What you need

- A domain you control
- A Cloudflare account (free plan is enough)
- A Hetzner Cloud account
- The LiveKit + OpenAI keys from `.env.example`

### Step 1 — Move your domain to Cloudflare

Cloudflare dashboard → **Add a site** → enter your domain → **Free** plan. Cloudflare gives you two NS records — update them at your current registrar. Wait for the activation email (usually under an hour, occasionally up to 24h). You can do Steps 2 and 3 in parallel.

### Step 2 — Provision the VM

Hetzner Cloud Console → **New server**:

- Location: `nbg1` or `fsn1` (EU latency to LiveKit Cloud)
- Image: Ubuntu 24.04
- Type: **CX22** (€4.51/mo, 2 vCPU, 4 GB RAM, 40 GB SSD)
- SSH key: paste your public key
- Name: `ig-prod-1`

### Step 3 — Bootstrap the VM

SSH in as `root` and run the bootstrap script (it creates a `deploy` user, hardens SSH, opens only port 22, installs Docker, and clones the repo to `/opt/ig/app`):

```bash
curl -fsSL https://raw.githubusercontent.com/<your-fork>/main/scripts/bootstrap_vm.sh \
  | bash -s -- https://github.com/<your-fork>.git
```

Or copy [scripts/bootstrap_vm.sh](scripts/bootstrap_vm.sh) over with `scp` and run it.

Reconnect as `deploy@<vm-ip>`, then:

```bash
cd /opt/ig/app
cp .env.example .env
```

Edit `.env`. Set the existing keys (`LIVEKIT_*`, `OPENAI_API_KEY`) and add three production-only ones:

```
WEBAPP_PUBLIC_URL=https://meeting.example.com
TUNNEL_TOKEN=              # filled in Step 4
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

`COMPOSE_FILE` lets you drop the `-f ... -f ...` flags from every `docker compose` command on this VM.

### Step 4 — Create the Cloudflare Tunnel

Cloudflare Zero Trust dashboard ([one.dash.cloudflare.com](https://one.dash.cloudflare.com)) → **Networks → Tunnels → Create a tunnel** → choose **Cloudflared** → name it `ig-prod`.

Cloudflare shows an install command containing `--token <long-string>`. Copy **just the token** into `.env` on the VM as `TUNNEL_TOKEN=...`.

Click **Next → Public Hostnames** and add two:

| Subdomain | Domain | Service | URL |
| --- | --- | --- | --- |
| `console` | `example.com` | HTTP | `console-frontend:80` |
| `meeting` | `example.com` | HTTP | `webapp:8765` |

Save. DNS records are created automatically.

### Step 5 — Cloudflare Access on the console

Zero Trust → **Access → Applications → Add an application → Self-hosted**:

- Name: `IG Console`
- Application domain: `console.example.com`
- Identity provider: **One-time PIN** (email magic link, zero setup) — or wire up Google/GitHub OAuth.
- Save.

Add a policy:

- Name: `Operators`
- Action: **Allow**
- Include: `Emails` → list every email that can create meetings.
- Save.

Do **not** add an Access application for `meeting.example.com` — meeting participants click the link from room chat and won't be in the policy.

### Step 6 — Bring up the stack

On the VM:

```bash
cd /opt/ig/app
docker compose up -d --build
docker compose logs -f cloudflared
```

Wait until cloudflared logs `Connection registered` for all four edge connections, then Ctrl-C.

### Step 7 — Verify

1. Open `https://console.example.com` → expect the Cloudflare Access PIN screen → sign in with an allow-listed email → the meeting console loads.
2. Create a test meeting end-to-end. Confirm:
   - The room-chat link the agent posts is `https://meeting.example.com/<id>/`.
   - Opening that link streams the live viewer (notebook, agenda, objectives update as you talk).

### Updating

Manual:

```bash
cd /opt/ig/app
git pull
docker compose up -d --build
```

Or set up continuous deployment (next section) so every push to `main` updates the VM automatically.

### Continuous deployment (GitHub Actions)

[.github/workflows/deploy.yml](.github/workflows/deploy.yml) SSHes into the VM on every push to `main` (and on manual trigger from the Actions tab) and runs the update commands above. ~2–3 min end to end.

**One-time setup:**

1. Generate a dedicated deploy key on your Mac (separate from your personal SSH key — no passphrase so the Action can use it):

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/ig_deploy -C "ig-deploy" -N ""
   ```

2. Authorize it on the VM as the `deploy` user:

   ```bash
   ssh deploy@<vm-ip> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys" < ~/.ssh/ig_deploy.pub
   ```

3. Add three secrets in the GitHub repo (**Settings → Secrets and variables → Actions → New repository secret**):

   | Name | Value |
   | --- | --- |
   | `DEPLOY_HOST` | the VM's IP or hostname |
   | `DEPLOY_USER` | `deploy` |
   | `DEPLOY_SSH_KEY` | the **private** key — `cat ~/.ssh/ig_deploy` (paste the entire `-----BEGIN ... END-----` block) |

4. Push to `main`. Watch the run under the **Actions** tab.

If the repo is private, the VM also needs to be able to `git pull` it — set up a separate **Deploy key** on the GitHub repo (**Settings → Deploy keys**) with the public key from the VM's `deploy` user (`ssh-keygen -t ed25519` on the VM, then add `~/.ssh/id_ed25519.pub` to GitHub).

### Backups

The meeting registry lives in the Redis AOF volume; per-run artifacts live in `out/` and `templates_generated/`. Nightly tar to a Hetzner Storage Box or external bucket. Find the Redis volume name with `docker volume ls`:

```bash
docker run --rm \
  -v app_redis-data:/data \
  -v /home/deploy/backup:/backup \
  alpine tar -czf /backup/redis-$(date +%F).tar.gz /data
```

### Budget cap reminder

Cloudflare Access protects the meeting console, but a compromised operator account can still burn budget. Set hard spend caps at OpenAI and LiveKit Cloud before going live.

## Notes

- The Silero VAD model is downloaded on first session inside the agent container. To pre-download: `docker compose run --rm agent python -m src.agent download-files`.
- Voices supported by `gpt-realtime`: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar. Change the `voice=` kwarg in [src/agent.py](src/agent.py) if you prefer another.
- The agent only accepts explicit dispatches (`agent_name="briefing-agent"`). The worker will not auto-join arbitrary rooms.
- Webapp port: `WEBAPP_PORT=8765` by default. If you tunnel the live viewer (ngrok, Tailscale, etc.) set `WEBAPP_PUBLIC_URL=https://<your-host>` so both the dispatch response and the in-room chat message use the reachable URL.
- Scale concurrent meetings: `docker compose up -d --scale agent=N`. Each agent replica registers with LiveKit as `briefing-agent`; LiveKit distributes job offers across them.
- Scale the live viewer for high-fanout meetings: bump `webapp` replicas (production seam — needs a reverse proxy in front).
- The console is stateless and horizontally scalable too: `docker compose up -d --scale console=N`. Atomic Redis Lua merges on every record update; the reconcile loop runs under a short-TTL leader lock so only one replica works per tick.
- No authentication. The console can create and start meetings (spending OpenAI + LiveKit budget) with no auth — same posture as the other public endpoints. Add a reverse proxy with auth before exposing this beyond a trusted network.
