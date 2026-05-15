# Frontend design

Live read-only viewer for a single meeting run. React 18 + TypeScript + Vite, styled with Tailwind, components from shadcn/ui.

## Page layout

```
┌──────────────────────────────────────────────────────────┐
│  Header (full width)                                     │
│   - meeting title                                        │
│   - briefing filename · template badge                   │
│   - elapsed / target · turns · run_id                    │
│   - current phase pill · Progress bar                    │
├──────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────────────────────────────────┐  │
│  │ Sidebar  │  │ Agenda                               │  │
│  │ (sticky) │  │ ─── Separator ───                    │  │
│  │          │  │ Notebook                             │  │
│  │ Agenda   │  │ ─── Separator ───                    │  │
│  │ Notebook │  │ Objectives                           │  │
│  │  - ...   │  │ ─── Separator ───                    │  │
│  │ Object.. │  │ Follow-ups                           │  │
│  │ Followup │  │ ─── Separator ───                    │  │
│  │ Briefing │  │ Briefing (collapsible)               │  │
│  └──────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

Container `max-w-7xl mx-auto px-6`. Body grid `md:grid-cols-[12rem_1fr] gap-8`. Header is outside the container so its bottom border spans the viewport. The sidebar is hidden below `md`.

## Section convention

Top-level page sections are rendered as

```tsx
<section id="<id>" className="scroll-mt-24">
  <h2 className="text-lg font-semibold tracking-tight">Label</h2>
  ...
</section>
```

Rules:

- **Sections are not wrapped in `Card`.** Between sections, use a shadcn `<Separator />` (placed in `App.tsx` between siblings). Inside Notebook, sections are separated with `<Separator />` too.
- Anchor `id`s are stable: `agenda`, `notebook`, `section-<sectionId>`, `objectives`, `followups`, `briefing`. The Sidebar reads these. Don't rename without updating `Sidebar.tsx`.
- `scroll-mt-24` keeps headings clear of the fixed header on smooth-scroll.

`Card` is reserved for **items** — a single notebook entry, a single objective. Items use `rounded-md border bg-card p-3`. Lists of items use `<ul className="space-y-2 | space-y-3">`.

## Typography

| Role | Tailwind |
| --- | --- |
| Meeting title | `text-2xl font-semibold tracking-tight` |
| Section `<h2>` | `text-lg font-semibold tracking-tight` |
| Sub-section `<h3>` (e.g. Notebook inner sections) | `text-base font-semibold` |
| Body | `text-sm` |
| Muted detail | `text-xs text-muted-foreground` |
| Micro tag (timestamps, percentages) | `text-[10px] uppercase tracking-wide text-muted-foreground` |
| Monospace numbers (elapsed) | `font-mono tabular-nums` |

## State cues

| State | Style |
| --- | --- |
| Current phase / focused section | `text-primary` heading, `ring-1 ring-primary/30` on the Agenda row, small `bg-primary` dot next to Notebook section heading |
| Visited phase | Filled `bg-primary` marker, `Check` icon |
| Upcoming phase | Outline marker, `text-muted-foreground` |
| Objective status: covered / partial / open | Badge variants `success` / `warning` / `outline` |
| Over-filled single-entry section | `text-warning` with `AlertTriangle` icon |

## shadcn components in use

| Component | Used by | Purpose |
| --- | --- | --- |
| `Badge` | Header, Agenda, Notebook, Objectives | Pills (phase, template, status, focus tags) |
| `Progress` | Header | Linear elapsed-vs-target indicator |
| `Separator` | App, Notebook | Divide sections |
| `Collapsible` | Briefing, Agenda (phase history) | Expand/collapse |
| `Alert` | Header (end-of-meeting) | Terminal state banner |
| `Card` | Item rows only — never wraps a section |

## Data flow

1. `App.tsx` reads `runId` from the URL pathname.
2. `useSnapshot(runId)` fetches `/state` then opens an SSE stream at `/<runId>/events`. Every message replaces the local `MeetingState`.
3. Each component takes `{ state }: { state: MeetingState }` and renders pure functions of state.
4. The meeting title is derived client-side from `state.briefing_markdown` via `extractMeetingTitle` (`lib/briefing.ts`). The agent backend does not send a title field.

## Title extraction

`extractMeetingTitle` strips YAML front-matter, finds the first H1, and removes a leading `Briefing:` prefix. Falls back to the template name. Briefings in this repo already follow `# Briefing: <Title>`.

## Sidebar / scroll

- `Sidebar.tsx` uses an `IntersectionObserver` (`rootMargin: -20% 0px -60% 0px`) to highlight the section nearest the top of the viewport.
- Click handlers call `scrollIntoView({ behavior: "smooth" })` and update the URL hash via `history.replaceState`.
- Anchors must exist in the DOM by the time the observer mounts; that is handled by mounting `Sidebar` as a sibling of `<main>` so the sections render in the same React pass.

## Responsive

- `md` (≥ 768px): two-column with sidebar.
- Below `md`: sidebar hidden; main is full width. The header's right-side time block wraps via `flex-wrap`.
- No mobile drawer yet — open question if/when that becomes important.
