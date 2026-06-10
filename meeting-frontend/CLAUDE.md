# CLAUDE.md — meeting-frontend/

> **Rule of the house:** any substantial change to this frontend (new route, new section, restructured layout, new data field rendered, new convention) MUST update [DESIGN.md](DESIGN.md) in the same commit. If you change build/dev workflow or conventions described here, also update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

The **participant-facing SPA** — a single React app with two routes (a `react-router` shell):

- **Live View** (`/:runId`) — read-only live viewer for one meeting run. The Python agent writes `MeetingState` to Redis; the `meeting` API (`../src/meeting/`) reads it and streams snapshots over SSE; this view subscribes and renders. Keeps its own dashboard-style visual language.
- **Join** (`/join/:meetingId`) — PIN-gated entry page for an invited meeting. Styled with the **console light theme** via `@ig/ui` (`Card`/`Button`/`Input`/`Alert`) so it matches the console.

This is the nginx half of a console-style pair: `meeting-frontend` (nginx, :8765) serves this bundle and reverse-proxies `/api` to the `meeting` backend (:8771). It is an **npm-workspace member** (alongside [`../shared/`](../shared/) and [`../console-frontend/`](../console-frontend/)). Its shadcn primitives and `cn()` come from `@ig/ui`; only viewer/join-specific components live here.

The bundle is built into the `Dockerfile.meeting-frontend` nginx image (`npm ci` within the workspace → `npm run build -w meeting-frontend` → `dist/` served by nginx). Editing files here does not hot-reload the running container — rebuild with `docker compose build meeting-frontend`, or use the Vite dev server (see below).

## Where things live

```
meeting-frontend/
  nginx.conf                serve static + proxy /api (SSE: proxy_buffering off) + /healthz to meeting:8771
  src/
    main.tsx                createRoot + <BrowserRouter>
    App.tsx                 router shell: /join/:meetingId → JoinPage, /:runId (+ /*) → LiveView, fallback NotFound
    components/
      LiveView.tsx          the live-viewer page (runId from useParams) — layout + Sidebar + main column
      Header.tsx            title, current-phase pill (derived), elapsed, progress bar
      Breadcrumb.tsx        root → current-section path, kind-glyph chips
      Agenda.tsx            scheduled top-level TOPICs as a vertical timeline
      Sidebar.tsx           sticky scroll-nav (IntersectionObserver)
      Notebook.tsx          recursive kind-aware tree renderer
      Followups.tsx         actions / open questions
      Briefing.tsx          raw markdown (collapsible)
    join/
      JoinPage.tsx          PIN-gated join — fetches GET /api/join/:id, renders the status
                            machine (loading / not-started / ended / not-found / PIN form),
                            submits POST /api/join/:id/token → redirect to join_url
    lib/
      briefing.ts           extractMeetingTitle (first H1 → strip "Briefing:")
      time.ts               formatElapsed, elapsedFraction, relativeTime
    hooks/
      useSnapshot.ts        fetch /api/runs/:id/state then subscribe to /api/runs/:id/events SSE
    types.ts                MeetingState + Transition — keep in sync with src/harness.py.
                            Section/SectionKind/Template + tree helpers come from @ig/ui.
  DESIGN.md                 conventions, typography, state cues
  CLAUDE.md                 this file
```

## Build & dev

- `npm install` **at the repo root** installs the whole workspace. `npm run build -w meeting-frontend` produces the production bundle; nginx serves `dist/` (baked into the `meeting-frontend` image at build time).
- `npm run dev -w meeting-frontend` for the Vite dev server (`:5173`). It proxies `/api` + `/healthz` to `http://localhost:8771` (run a local `meeting` backend, or `docker compose up -d meeting`).
- Type-check is part of `build` (`tsc -b && vite build`). There is no separate test runner yet.

### Preview with synthetic state

```
docker compose up -d redis                  # the meeting API reads state from Redis
uv run python scripts/preview_dev_server.py # seeds run_id=dev + runs the meeting API on :8771
npm run dev -w meeting-frontend             # Vite on :5173, proxies /api → :8771
# open http://localhost:5173/dev/
```

`preview_dev_server.py` writes a fake `MeetingState` to Redis under `run_id=dev` and runs the meeting API — no LiveKit, no microphone needed. The Vite dev server serves this SPA.

## First things to read when adding a UI feature

1. [DESIGN.md](DESIGN.md) — layout, section convention (no `Card` around viewer sections, `Separator` between them), typography, state cues.
2. [src/types.ts](src/types.ts) — the snapshot shape. The backend source of truth is `../src/harness.py` (MeetingState + Transition) and `../src/templates/schema.py` (Section / SectionKind / Template + tree helpers).
3. The existing component closest to what you're adding — patterns are intentionally consistent.

## Conventions worth not violating

- **Two visual languages, on purpose.** The Live View keeps the dashboard aesthetic (its own look). The Join page uses the **console light theme** through `@ig/ui` `Card`/`Button`/`Input`/`Alert` — keep them matching the console. The shared shadcn tokens in `index.css` are the console's light palette (light `:root`, opt-in `.dark`), so the Join surface matches with no extra theming.
- **Routing is `BrowserRouter`.** Deep links (`/<run_id>/`, `/join/<id>`) work because nginx falls back to `index.html` (`try_files`). `runId`/`meetingId` come from `useParams`, never `window.location`.
- **Data paths are under `/api`.** `useSnapshot` fetches `/api/runs/:id/state` and subscribes to `/api/runs/:id/events`; the join page hits `/api/join/:id` and `/api/join/:id/token`. nginx proxies `/api` to the backend.
- Live-view sections are `<section id="...">` with `scroll-mt-24` and an `<h2>` heading. They are NOT wrapped in `Card`. Use `<Separator />` between sections.
- Item rows (single answer, single question) use `rounded-md border bg-card p-3`.
- Anchor IDs (`breadcrumb`, `agenda`, `notebook`, `section-<id>` per tree node, `followups`, `briefing`) are read by `Sidebar.tsx`. If you rename one, update the sidebar.
- Title comes from `state.briefing_markdown` via `extractMeetingTitle`. Don't add a `title` field to MeetingState unless you also update the Python side.
- The active phase is **derived** from `state.current_section_id` via `enclosingPhase(...)`. There is no `current_phase` field. Do not reintroduce one.
- Tree-walk helpers (`sectionById`, `childrenOf`, `pathTo`, `scheduledNodes`, …) live in `@ig/ui` and are re-exported from `src/types.ts`. Use them — do not write ad-hoc walks.

## Data flow

`useSnapshot(runId)` is the single source for the Live View. Each component receives `state: MeetingState` and renders pure functions of it. No client-side mutation of state. The Join page is self-contained — it fetches its own status and posts the PIN.

## When you finish

- Run `npm run build -w meeting-frontend` to confirm a clean compile.
- Open a real run in the preview (Live View) and seed a `meeting:*` record for each join status (Join) to sanity-check.
- Update [DESIGN.md](DESIGN.md) if the change introduced a new route/section, new state cue, new shadcn component, new convention, or changed the layout. Update this file if conventions or workflows changed.
