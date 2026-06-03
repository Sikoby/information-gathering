# CLAUDE.md — console-frontend/

> **Rule of the house:** any substantial change to this app (new route/page, new data field, new convention, build/dev workflow) MUST update this file in the same commit. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

The **meeting console** SPA — where a user writes a prompt, gets a generated **template**, edits it, and starts one meeting after another from it (one running at a time). Templates and meetings are two separate entities here; the dashboard lists both. It is a different app from the in-meeting viewer in [`../frontend/`](../frontend/): this one is interactive and has a **router**; the viewer is read-only and single-page.

React 18 + TypeScript + Vite + Tailwind, an npm-workspace member. It depends on the shared component library [`@ig/ui`](../shared/) and on `react-router-dom`. It is built into its own container ([Dockerfile.console-frontend](../Dockerfile.console-frontend)): an **nginx** image that serves the static bundle and reverse-proxies `/api` to the `console` backend (so the browser is always same-origin — no CORS).

## Where things live

```
console-frontend/
  index.html, vite.config.ts, tailwind.config.js, postcss.config.js, tsconfig.json
  nginx.conf                serve static + proxy /api + /healthz to console:8770
  src/
    main.tsx                createRoot + <BrowserRouter>
    App.tsx                 <AuthGate> (global Header/Footer chrome + account menu) + <Routes>: / , /welcome , /templates/new , /templates/:id , /meetings/new , /meetings/:id
    types.ts                TemplateRecord + MeetingRecord — keep in sync with src/console/models.py
    lib/
      api.ts                fetch wrappers for /api/* + ApiError (carries status code for 401 branching)
      format.ts             relativeTime, slugify
    hooks/
      useAuth.ts            calls GET /api/me once on mount → {loading|signed-in|unauthenticated|error}
      usePolling.ts         setInterval helper
      useTemplates.ts       dashboard template list, polls every 5s
      useTemplate.ts        one template, polls 3s only while generating
      useMeetings.ts        dashboard meeting list, polls every 5s
      useMeeting.ts         one meeting, polls 3s only while running
    pages/
      Dashboard.tsx         two stacked sections: Templates (top) + Meetings (Scheduled/Running/Done); each section heading carries a concept InfoTooltip + a New … button
      Welcome.tsx             one-screen onboarding shown on first visit per tab
      NewTemplate.tsx       the prompt form + optional .pptx/.pdf upload
      NewMeeting.tsx        the single meeting-creation surface: template picker + Start now / Schedule (time + invitees → .ics)
      TemplateDetail.tsx    generating spinner / failed / editor + "Start meeting" (routes to /meetings/new?template=<id>); Prompt/Template headings carry concept InfoTooltips
      MeetingDetail.tsx     slim scheduled/live/done view with "open source template" link + copy-link / add-to-calendar buttons
    components/
      Page.tsx              Page (max-w-6xl px-6 py-8 outer container) + PageHeader (back-link + title + badge + info) + BackLink + CenteredMessage (loading/error box)
      IconButton.tsx        the icon-only Button wrapper every button uses — required `label` → aria-label + title tooltip; sizes "default" (h-9 w-9) / "sm" (h-8 w-8, smaller glyph)
      Field.tsx             labelled form field: label + optional info tooltip + control + optional hint
      LinkField.tsx         read-only URL Input + Copy + Open-in-new-tab, built on Field
      InviteesList.tsx      the <ul> of invitee emails (renders nothing when the list is empty)
      TemplateCard.tsx, MeetingCard.tsx, StatusBadge.tsx, CopyButton.tsx
      TemplateEditor.tsx    section-tree editor — edits the "_root" node's children directly (the structural root is hidden); rows start collapsed, with Expand all / Collapse all; the topic/question kind toggle and the delete button sit inline in each row header; concept InfoTooltips on the Sections heading and field labels
```

When `NewTemplate` includes a file, the form submits multipart to `/api/templates/upload`; otherwise it stays on the JSON path. `TemplateDetail` shows a small chip with the document filename + slide count when one was attached, and its "Start meeting" button (disabled, with a hint, while any other meeting is running) saves any pending edits then navigates to `/meetings/new?template=<id>` — there is no start-meeting modal. `NewMeeting` is the one place meetings are created: pick a ready template (preselected from the `?template=` deep link), set a title + duration, then choose a mode. **Start now** calls `POST /api/templates/:id/meetings` and shows a result panel with copyable join + live-view links (`CopyButton`). **Schedule** adds a `datetime-local` start time + an invitees field (comma/newline emails → `string[]`) and calls `POST /api/templates/:id/scheduled-meetings`; its result panel offers **Add to calendar (.ics)** (a download `<a>` to `meetingInviteIcsUrl(id)`), a copyable stable live-view link, and the invited list. It is reachable from the dashboard **New meeting** button and from any template's Start meeting button.

Shared UI primitives (`Button`, `Card`, `Input`, `Textarea`, `Badge`, ...) come from `@ig/ui` — do not copy shadcn components in here; add them to [`../shared/`](../shared/).

## Build & dev

- The workspace installs from the **repo root**: `npm install` there, not here.
- `npm run build -w console-frontend` → `tsc -b && vite build` → `dist/`.
- `npm run dev -w console-frontend` → Vite dev server on `:5174`, proxying `/api` → `http://localhost:8770` (run a local `console` backend, or `docker compose up -d console`).
- `tailwind.config.js` uses the `@ig/ui` preset and **must** keep `../shared/src/**` in `content` so shared-component classes survive the purge.

## Conventions

- Routing is `BrowserRouter`; deep links work because nginx falls back to `index.html` (`try_files`).
- Polling, not SSE. `useTemplate` polls only while `template_status === "generating"`, `useMeeting` only while `status === "running"` or `"scheduled"` (so a scheduled meeting's detail page flips to running the moment deferred dispatch fires) — so polling never clobbers in-progress template edits in `TemplateDetail`.
- `TemplateDetail` holds a local `draft` re-initialised when `template_id`/`generation_seq`/`template_status` changes (see the `draftKey` effect).
- `types.ts` mirrors `src/console/models.py` — keep them in sync. Both `TemplateRecord` and `MeetingRecord` carry `owner_email`.
- First visit per tab is redirected from `/` to `/welcome`; `sessionStorage['welcome:dismissed']` clears the redirect for the rest of that tab session.

## Auth

`AuthGate` (in `App.tsx`) wraps every route. It calls `GET /api/me` once on mount; on `401` it shows a "Sign in via Cloudflare Access" card (mentioning the `CONSOLE_DEV_USER_EMAIL` env var for local dev), otherwise it renders the routes inside the global chrome: the shared `Header` (the "Information Gathering" brand on the left; on the right an account-icon `DropdownMenu` holding the signed-in email and a **Sign out** item) and the shared `Footer`. Sign out redirects the browser to the team-domain Cloudflare Access logout (`https://<team>.cloudflareaccess.com/cdn-cgi/access/logout`) returned by `GET /api/me` as `logout_url` (built from the console's `CONSOLE_CF_TEAM_DOMAIN` env var); it falls back to the app-domain `/cdn-cgi/access/logout` when that field is `null` (local dev, where it's a no-op SPA reload). The app-domain logout was replaced because it can fail with "Unable to find your Access organization!". The backend already filters lists per user, so the existing hooks (`useTemplates`, `useMeetings`) don't need a tenant param.

## Design conventions

The user dislikes visually noisy editor UI. Follow these rules everywhere in this app:

- **No per-item boxes for nested / repeated structures.** Don't wrap each row of a list or tree in a bordered card. Show hierarchy with indentation and a single left tree-line, not with stacked borders. (See `TemplateEditor` for the canonical example.)
- **One font family across the UI.** Do not use `font-mono`. No "tech" / monospace styling for ids, run ids, elapsed timers, or anything else. Use `tabular-nums` if you need digits to not jitter.
- **Never render internal ids in the UI.** Section ids, meeting ids, run ids, etc. are for the network, not the user. If you need to display one for debugging, gate it behind a debug toggle.
- **No ALL CAPS.** Don't use `uppercase` (with or without `tracking-wide`) for labels, badges, headings, or status text. Sentence case for headings, lowercase for chips.
- **Consistent heading scale.** Keep heading sizes uniform across pages: page titles `text-2xl font-semibold tracking-tight`; section headers `text-lg font-semibold tracking-tight`; minor / overline group labels `text-sm font-semibold text-muted-foreground`; field labels `text-sm font-medium`. An `InfoTooltip` next to a heading takes the matching `size` so the icon scales with the text: `lg` ↔ page title, `md` ↔ section, `sm` ↔ label. The dashboard has no separate page title, so its two top-level section headings (Templates, Meetings) sit at the page-title tier and carry `lg` tooltips.
- **Header first, true collapse.** For any expandable item, the row's title is the first thing visible and is the *only* thing visible when collapsed. Body, notes, metadata, and children all live below the title and disappear together when the row is collapsed.
- **Don't editorialise field labels.** Keep them short ("Speaker notes", not "Speaker notes · hidden from participants"). Explain hidden-from-participants / similar context in the placeholder or helper text instead.

### Page layout

- **Every page is wrapped in `<Page>`** (`mx-auto max-w-6xl px-6 py-8`) so its left/right gutters line up with the shared `Header`/`Footer` (also `max-w-6xl px-6`). Never hand-roll the outer container width — drift here is exactly what made the old pages stop aligning with the header brand.
- **Page chrome goes through `<PageHeader back title badge info>`.** It renders the optional back-link, the `h1` page title, an optional status `Badge`, and an optional `InfoTooltip`. It is the only place a page title is styled, so the heading scale can't drift.
- **Forms sit in a left-aligned readable column.** Wrap the form body in `max-w-2xl` *inside* `<Page>` (don't narrow the whole page) so the title and back-link still align to the header's left edge while inputs stay a comfortable width. Card-grid pages (Dashboard) keep the full `max-w-6xl`.
- Loading / error states use `<CenteredMessage>`, never a bespoke centered box.

### Buttons are strict icon-only

Every button in this app is a **square icon button** rendered through `IconButton`. No visible button text. The required `label` prop becomes both the `aria-label` and the native `title` (hover tooltip) — that is how an icon-only action stays discoverable. Children are exactly one lucide icon.

Colour encodes the button's *role*, and is the same for that role on every page:

| Role | `variant` | Example actions |
| --- | --- | --- |
| Primary / commit | `default` (filled) | New, Create, Start meeting, Schedule, Retry generation, Go to meeting, Add to calendar |
| Secondary | `outline` | Save, Regenerate, Copy, Open in new tab |
| Navigation / dismiss | `ghost` | Back, Cancel, Back to dashboard |
| Danger | `ghost` + `text-destructive` | every Delete (subtle — never a filled red button) |

One icon per action, used the same way everywhere:

| Action | Icon | Action | Icon |
| --- | --- | --- | --- |
| New | `Plus` | Back | `ArrowLeft` |
| Create from document | `Upload` | Go / next | `ArrowRight` |
| Start (now) | `Play` | Back to dashboard | `LayoutDashboard` |
| Schedule | `CalendarClock` | Cancel / remove file | `X` |
| Save | `Save` → `Check` when saved | Add topic | `ListPlus` |
| Regenerate | `RefreshCw` | Add question | `MessageSquarePlus` |
| Retry | `RotateCw` | Kind = Topic | `ListTree` |
| Delete | `Trash2` | Kind = Question | `CircleHelp` |
| Copy | `Copy` → `Check` when copied | Add to calendar | `CalendarPlus` |
| Open / live view | `ExternalLink` | Join (voice) | `Video` |
| Busy / in-flight | `Loader2` (`animate-spin`) | | |

When two buttons share an icon (the two Copy buttons, the `Plus` on both dashboard cards), the `label`/tooltip disambiguates them. A busy action swaps its icon for a spinning `Loader2` and updates its `label` ("Saving…", "Starting…").

**The only text exception** is the two onboarding CTAs on `Welcome` ("Skip", "Got it, take me to the dashboard") — a first-run screen where a bare icon would be cryptic. Everything that is *not* a button keeps its text: `DropdownMenuItem` rows (the Sign out item), the file-upload `<label>` dropzone, `<select>` menus, and inline text links inside `Alert`s or status lines (e.g. "another meeting is running →").

### Use the shared console components — don't re-implement

Reach for these before writing new markup; they exist so structure, spacing, and button styling can't drift:

`Page`, `PageHeader`, `BackLink`, `CenteredMessage` (layout) · `Field`, `LinkField`, `InviteesList` (forms) · `IconButton`, `CopyButton` (buttons). If a third or fourth page needs the same block, promote it into `components/` rather than copy-pasting.

> These design rules are **console-scoped**. The in-meeting viewer (`../frontend/`) intentionally uses a different visual language (dashboard aesthetic, mono timers, visible run ids) — don't apply these rules there, and don't pull these components across.

## Verify changes

`npm run build -w console-frontend` (`tsc -b && vite build`) is the gate — it catches every missing import/prop from a refactor. Then `docker compose build console-frontend && docker compose up -d` and open `http://localhost:8769`. Spot-check: every button is an icon whose hover tooltip names the action, and each page's title / back-link left edge lines up with the header brand.
