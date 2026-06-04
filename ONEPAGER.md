# Briefing-Driven Voice Meeting Agent

**An AI consultant that joins voice meetings, runs an interview-style conversation against a briefing or template, and produces structured findings — live.**

Discovery interviews, requirements gatherings, walkthroughs, and structured Q&A sessions produce hours of audio but rarely a structured artifact you can act on afterwards. Note-takers miss things; transcripts dump everything in chronological soup. This system runs the meeting on a script you can edit, captures findings against that script as the conversation happens, and hands you a tree of answers instead of a wall of text.

---

## What it does

- **Joins meetings as a voice participant.** Connects to a LiveKit room, speaks first, listens, transcribes, and drives the conversation against an explicit agenda. Powered by OpenAI `gpt-realtime`.
- **Captures findings into a typed tree.** A `Section` tree of topics → questions → answers, with a typed transition log (open / drill_down / zoom_out / sibling / revisit). Not a transcript dump — a structured notebook.
- **Streams a live cockpit.** A shareable read-only URL renders the agenda timeline, where the agent currently is, the growing notebook, typed transitions, and follow-ups — all updating over SSE as the conversation unfolds. Multiple viewers per meeting; nothing to install.
- **Writes one structured artifact per run.** Transcript, canonical tree, derived notebook view, transitions, follow-ups, run metadata. All on disk, all diffable.

## Capabilities

| | |
|---|---|
| **Prompt → meeting** | Non-developer writes a paragraph describing the meeting; the template-generator synthesises an editable agenda (topics, questions, phases) in 1–4 minutes via an LLM impl+critique loop. |
| **Document → meeting** | Upload a `.pptx` or `.pdf`. Slides become topics in order, speaker notes become the agent's verbatim script. The agent walks the deck with the participant. |
| **Reusable templates** | Each generated template is persistent and reusable. One template, many meetings. Editable shape, prompt, and target length. |
| **Four built-in shapes** | `requirements`, `research`, `eval`, `generic` — selectable from the developer CLI or auto-picked from a markdown briefing. |
| **Live viewer link** | Drop into the LiveKit room's chat panel when participants join. Anyone with the link can watch — same posture as a shared Google Doc. |
| **Concurrent meetings** | The agent worker scales horizontally (`--scale agent=N`); LiveKit distributes job offers across replicas. Console and webapp are stateless. |

## Two entry points

```
Console (recommended)        |   Developer CLI
-----------------------------|---------------------------
Browser → console-frontend   |   scripts/dispatch.py --briefing X.md
       → console API         |          ↓
       → template-generator  |   HTTP POST /dispatch
       → dispatch → LiveKit  |          ↓
       → agent worker        |   agent worker
```

Both paths converge on the same dispatch → agent → webapp runtime.

## Architecture

Seven containers, brokered by Redis. The agent has no direct connection to peripheral services — everything internal flows through Redis (state pub/sub + registry) or LiveKit Cloud (room dispatch).

| Container | Role |
|---|---|
| `console-frontend` + `console` | SPA + API: create templates, edit, launch meetings, track lifecycle. Stateless. |
| `template-generator` | OpenAI impl+critique loop that synthesises a `Template` from prompts or uploaded documents. |
| `dispatch` | Creates the LiveKit room and dispatches the agent worker via `AgentDispatchService`. |
| `agent` | LiveKit worker. One process per active meeting. Owns the live `MeetingState`. |
| `webapp` | aiohttp + SSE live viewer. Reads snapshots from Redis. |
| `redis` | State pub/sub, last-snapshot cache, AOF-persisted template + meeting registries. |

## Run it

```
cp .env.example .env       # LIVEKIT_* and OPENAI_API_KEY
docker compose up -d
# Console at http://localhost:8769
```

**Production deploy:** single Hetzner CX22 (~€5/mo) + Cloudflare Tunnel for TLS, Cloudflare Access on the console only. No inbound ports beyond SSH. Continuous deployment via GitHub Actions, ~2–3 min push-to-live.

## Built on

LiveKit Cloud · OpenAI (`gpt-realtime`, `gpt-5`, `gpt-4o-mini-transcribe`) · Python 3.11 (aiohttp + Pydantic) · React + Vite · Redis 7 · Docker Compose
