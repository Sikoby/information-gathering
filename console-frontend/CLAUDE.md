# CLAUDE.md — console-frontend/

> **Rule of the house:** any substantial change to this app (new route/page, new data field, new convention, build/dev workflow) MUST update this file in the same commit. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

The **meeting console** SPA — where a user writes a prompt, gets a generated meeting template, edits it, starts the meeting, and watches every meeting's Planned → Running → Done lifecycle. It is a different app from the in-meeting viewer in [`../frontend/`](../frontend/): this one is interactive and has a **router**; the viewer is read-only and single-page.

React 18 + TypeScript + Vite + Tailwind, an npm-workspace member. It depends on the shared component library [`@ig/ui`](../shared/) and on `react-router-dom`. It is built into its own container ([Dockerfile.console-frontend](../Dockerfile.console-frontend)): an **nginx** image that serves the static bundle and reverse-proxies `/api` to the `console` backend (so the browser is always same-origin — no CORS).

## Where things live

```
console-frontend/
  index.html, vite.config.ts, tailwind.config.js, postcss.config.js, tsconfig.json
  nginx.conf                serve static + proxy /api + /healthz to console:8770
  src/
    main.tsx                createRoot + <BrowserRouter>
    App.tsx                 <Routes>: / , /new , /meetings/:id
    types.ts                MeetingRecord etc. — keep in sync with src/console/models.py
    lib/
      api.ts                fetch wrappers for /api/*
      format.ts             relativeTime, slugify
    hooks/
      usePolling.ts         setInterval helper
      useMeetings.ts        dashboard list, polls every 5s
      useMeeting.ts         one meeting, polls 3s only while generating/running
    pages/
      Dashboard.tsx         meetings grouped Planned / Running / Done
      NewMeeting.tsx        the prompt form + optional .pptx/.pdf upload
      MeetingDetail.tsx     generating spinner / failed / editor / running / done
    components/
      MeetingCard.tsx, StatusBadge.tsx, TemplateEditor.tsx
```

When `NewMeeting` includes a file, the form submits multipart to `/api/meetings/upload`; otherwise it stays on the JSON path. `MeetingDetail` shows a small chip with the document filename + slide count when one was attached.

Shared UI primitives (`Button`, `Card`, `Input`, `Textarea`, `Badge`, ...) come from `@ig/ui` — do not copy shadcn components in here; add them to [`../shared/`](../shared/).

## Build & dev

- The workspace installs from the **repo root**: `npm install` there, not here.
- `npm run build -w console-frontend` → `tsc -b && vite build` → `dist/`.
- `npm run dev -w console-frontend` → Vite dev server on `:5174`, proxying `/api` → `http://localhost:8770` (run a local `console` backend, or `docker compose up -d console`).
- `tailwind.config.js` uses the `@ig/ui` preset and **must** keep `../shared/src/**` in `content` so shared-component classes survive the purge.

## Conventions

- Routing is `BrowserRouter`; deep links work because nginx falls back to `index.html` (`try_files`).
- Polling, not SSE. `useMeeting` polls only while `template_status === "generating"` or `status === "running"` — so it never clobbers in-progress edits on a `planned` + `ready` meeting.
- `MeetingDetail` holds a local `draft` re-initialised when `meeting_id`/`generation_seq`/`template_status` changes (see the `draftKey` effect).
- `types.ts` mirrors `src/console/models.py` — keep them in sync.

## Design conventions

The user dislikes visually noisy editor UI. Follow these rules everywhere in this app:

- **No per-item boxes for nested / repeated structures.** Don't wrap each row of a list or tree in a bordered card. Show hierarchy with indentation and a single left tree-line, not with stacked borders. (See `TemplateEditor` for the canonical example.)
- **One font family across the UI.** Do not use `font-mono`. No "tech" / monospace styling for ids, run ids, elapsed timers, or anything else. Use `tabular-nums` if you need digits to not jitter.
- **Never render internal ids in the UI.** Section ids, meeting ids, run ids, etc. are for the network, not the user. If you need to display one for debugging, gate it behind a debug toggle.
- **No ALL CAPS.** Don't use `uppercase` (with or without `tracking-wide`) for labels, badges, headings, or status text. Sentence case for headings, lowercase for chips.
- **Header first, true collapse.** For any expandable item, the row's title is the first thing visible and is the *only* thing visible when collapsed. Body, notes, metadata, and children all live below the title and disappear together when the row is collapsed.
- **Don't editorialise field labels.** Keep them short ("Speaker notes", not "Speaker notes · hidden from participants"). Explain hidden-from-participants / similar context in the placeholder or helper text instead.

## Verify changes

`npm run build -w console-frontend` for a clean compile, then `docker compose build console-frontend && docker compose up -d` and open `http://localhost:8769`.
