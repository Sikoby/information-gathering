# CLAUDE.md — frontend/

> **Rule of the house:** any substantial change to this frontend (new section, restructured layout, new data field rendered, new convention) MUST update [DESIGN.md](DESIGN.md) in the same commit. If you change build/dev workflow or conventions described here, also update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

A read-only live viewer for one meeting run. The Python agent in `../src/` writes a `MeetingState` to Redis; the webapp container in `../src/webapp/` reads from Redis and publishes snapshots over SSE; this app subscribes and renders. URL is `/<run_id>/` on whichever host serves the webapp container (defaults to `http://localhost:8765/` for local `docker compose up`).

This bundle is baked into the webapp Docker image at build time (multi-stage `Dockerfile.webapp` runs `npm ci && npm run build` and copies `dist/` into the runtime image). Editing files here does not hot-reload the running container — rebuild with `docker compose build webapp` to see changes, or use the preview dev server (see below).

## Where things live

```
frontend/
  src/
    App.tsx                 layout + Sidebar + main column
    components/
      Header.tsx            title, current phase, elapsed, progress bar
      Agenda.tsx            vertical timeline of template.phases
      Sidebar.tsx           sticky scroll-nav (IntersectionObserver)
      Notebook.tsx          template.sections + entries
      Objectives.tsx        objectives + tracker
      Followups.tsx         actions / open questions
      Briefing.tsx          raw markdown (collapsible)
      ui/                   shadcn primitives (alert, badge, card, collapsible, progress, separator)
    lib/
      briefing.ts           extractMeetingTitle (first H1 → strip "Briefing:")
      time.ts               formatElapsed, elapsedFraction, relativeTime
      utils.ts              cn() — clsx + tailwind-merge
    hooks/
      useSnapshot.ts        fetch /state then subscribe to /events SSE
    types.ts                MeetingState and child types — keep in sync with src/harness.py
  DESIGN.md                 conventions, typography, state cues
  CLAUDE.md                 this file
```

## Build & dev

- `npm install` then `npm run build` for a production bundle. The aiohttp server in `../src/webapp/server.py` serves `frontend/dist/` (baked into the webapp image at build time).
- `npm run dev` for the Vite dev server. The container serves `dist/`, so for live UI iteration prefer either `npm run build -- --watch` against a real run, or `python scripts/preview_dev_server.py` against synthetic state.
- Type-check is part of `build` (`tsc -b && vite build`). There is no separate test runner yet.

### Preview with synthetic state

```
docker compose up -d redis                  # webapp now reads state from Redis
uv run python scripts/preview_dev_server.py # serves /dev/ on :8767
```

`preview_dev_server.py` writes a fake `MeetingState` to Redis under `run_id=dev` and starts the webapp on its own port — no LiveKit, no microphone needed.

## First things to read when adding a UI feature

1. [DESIGN.md](DESIGN.md) — layout, section convention (no `Card` around sections, `Separator` between them), typography, state cues.
2. [src/types.ts](src/types.ts) — the snapshot shape. The backend source of truth is `../src/harness.py` (MeetingState) and `../src/templates/schema.py` (Template/Phase/NotebookSection).
3. The existing component closest to what you're adding — patterns are intentionally consistent.

## Conventions worth not violating

- Sections are `<section id="...">` with `scroll-mt-24` and an `<h2>` heading. They are NOT wrapped in `Card`. Use `<Separator />` between sections.
- Item rows (single notebook entry, single objective) use `rounded-md border bg-card p-3`. That is where `Card`-like styling lives now.
- Anchor IDs (`agenda`, `notebook`, `section-<id>`, `objectives`, `followups`, `briefing`) are read by `Sidebar.tsx`. If you rename one, update the sidebar.
- Title comes from `state.briefing_markdown` via `extractMeetingTitle`. Don't add a `title` field to MeetingState unless you also update the Python side.
- Don't reintroduce `PhaseBar` — it was replaced by `Agenda`. The phase-history collapsible lives in `Agenda.tsx`.

## Data flow

`useSnapshot(runId)` is the single source. Each component receives `state: MeetingState` and renders pure functions of it. No client-side mutation of state.

## When you finish

- Run `pnpm build` to confirm a clean compile.
- Open a real run in the preview to sanity-check the change.
- Update [DESIGN.md](DESIGN.md) if the change introduced a new section, new state cue, new shadcn component, new convention, or changed the layout. Update this file if conventions or workflows changed.
