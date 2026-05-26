# Frontend design

Live read-only viewer for a single meeting run. React 18 + TypeScript + Vite, styled with Tailwind, components from shadcn/ui.

## Page layout

```
┌──────────────────────────────────────────────────────────┐
│  Header (full width)                                     │
│   - meeting title                                        │
│   - template badge · turns · run_id                      │
│   - elapsed / target                                     │
│   - current-phase pill (derived from current_section_id) │
│   - Progress bar                                         │
├──────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────────────────────────────────┐  │
│  │ Sidebar  │  │ Breadcrumb (current tree position)   │  │
│  │ (sticky) │  │ ─── Separator ───                    │  │
│  │          │  │ Agenda (scheduled top-level topics)  │  │
│  │ Position │  │ ─── Separator ───                    │  │
│  │ Agenda   │  │ Notebook (Meeting card + tree)       │  │
│  │ Notebook │  │ ─── Separator ───                    │  │
│  │  - phase │  │ Transitions (typed navigation log)   │  │
│  │  - phase │  │ ─── Separator ───                    │  │
│  │ Transit. │  │ Follow-ups                           │  │
│  │ Followup │  │ ─── Separator ───                    │  │
│  │ Briefing │  │ Briefing (collapsible markdown)      │  │
│  └──────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

Container `max-w-7xl mx-auto px-6`. Body grid `md:grid-cols-[12rem_1fr] gap-8`. Header is outside the container so its bottom border spans the viewport. The sidebar is hidden below `md`.

## Data model in one paragraph

The agent owns a single tree of `Section` nodes (`kind` ∈ `meeting | topic | question | answer`). The root is `kind="meeting"` (id `_root`). Its `header`+`body` hold the BLUF + SCQA framing once `frame_meeting` has been called. Top-level TOPICs with a `target_fraction` set are "phases" — together they form the agenda; their fractions must sum to ~1.0. Inside a phase TOPIC sit other TOPICs and QUESTIONs; QUESTIONs own only ANSWERs, which are runtime nodes (`record_finding` writes them). The pyramid wrap-up is just another TOPIC under root with the well-known id `_root/closing`. The viewer derives the current phase from `enclosingPhase(state.sections, state.current_section_id)` — never from a stored field.

## Section convention

Top-level page sections are rendered as

```tsx
<section id="<id>" className="scroll-mt-24">
  <h2 className="text-lg font-semibold tracking-tight">Label</h2>
  ...
</section>
```

Rules:

- **Sections are not wrapped in `Card`.** Between sections, use a shadcn `<Separator />` (placed in `App.tsx` between siblings). Inside Notebook, scheduled top-level topics are separated with `<Separator />` too.
- Anchor `id`s are stable: `breadcrumb`, `agenda`, `notebook`, `section-<sectionId>` (per node in the tree), `transitions`, `followups`, `briefing`. The Sidebar reads these. Don't rename without updating `Sidebar.tsx`.
- `scroll-mt-24` keeps headings clear of the fixed header on smooth-scroll.

`Card`-style framing (`rounded-md border bg-card p-3`) is reserved for items — a single answer, a single question, a single transition row.

## Typography

| Role | Tailwind |
| --- | --- |
| Meeting title | `text-2xl font-semibold tracking-tight` |
| Section `<h2>` | `text-lg font-semibold tracking-tight` |
| Notebook inner sections `<h3>`/`<h4>` | `text-base font-semibold` / `text-sm font-semibold` |
| Body | `text-sm` |
| Muted detail | `text-xs text-muted-foreground` |
| Micro tag (timestamps, percentages, ids) | `text-[10px] uppercase tracking-wide text-muted-foreground` |
| Monospace numbers / section ids | `font-mono tabular-nums` |

## State cues

| State | Style |
| --- | --- |
| Current section (anywhere in tree) | `text-primary` heading + small `bg-primary` dot |
| Current phase (Agenda + Header pill) | `ring-1 ring-primary/30` Agenda row, primary `Badge` in Header |
| Visited phase | Filled `bg-primary` marker, `Check` icon |
| Upcoming phase | Outline marker, `text-muted-foreground` |
| Scheduled TOPIC | "X% of meeting" outline badge |
| Unanswered question | `outline` badge labelled "unanswered" |
| Answered question | `secondary` badge labelled "N answer(s)" |
| Phase progress | Badge variant: outline (no questions yet) / secondary (some) / success (all answered) |
| Closing TOPIC (`_root/closing`) | `border-2 border-primary/40 bg-primary/5` framed block |
| Transition kind | Coloured `Badge` with directional lucide icon (Play / ArrowDown / ArrowUp / ArrowRightLeft / RotateCw) |
| Phase boundary crossed in transition | Extra outline `"↕ phase"` chip on the transition row |

## shadcn components in use

| Component | Used by | Purpose |
| --- | --- | --- |
| `Badge` | Header, Agenda, Notebook, TransitionLog | Pills (phase, status, kind, target fraction) |
| `Progress` | Header | Linear elapsed-vs-target indicator |
| `Separator` | App, Notebook | Divide sections |
| `Collapsible` | Briefing | Expand/collapse |
| `Alert` | Header (end-of-meeting) | Terminal state banner |

## Data flow

1. `App.tsx` reads `runId` from the URL pathname.
2. `useSnapshot(runId)` fetches `/state` then opens an SSE stream at `/<runId>/events`. Every message replaces the local `MeetingState`.
3. Each component takes `{ state }: { state: MeetingState }` and renders pure functions of state. Tree walks use the helpers exported from `@ig/ui` (`sectionById`, `childrenOf`, `descendantsOf`, `pathTo`, `scheduledNodes`, `enclosingPhase`, …).
4. The meeting title is derived client-side from `state.briefing_markdown` via `extractMeetingTitle` (`lib/briefing.ts`). The agent backend does not send a title field.

## Title extraction

`extractMeetingTitle` strips YAML front-matter, finds the first H1, and removes a leading `Briefing:` prefix. Falls back to the template name. Briefings in this repo already follow `# Briefing: <Title>`.

## Sidebar / scroll

- `Sidebar.tsx` uses an `IntersectionObserver` (`rootMargin: -20% 0px -60% 0px`) to highlight the section nearest the top of the viewport.
- The Notebook sub-tree in the sidebar lists scheduled top-level TOPICs and their inner TOPIC children (so each phase has expand-able sub-anchors).
- Click handlers call `scrollIntoView({ behavior: "smooth" })` and update the URL hash via `history.replaceState`.
- Anchors must exist in the DOM by the time the observer mounts; that is handled by mounting `Sidebar` as a sibling of `<main>` so the sections render in the same React pass.

## Responsive

- `md` (≥ 768px): two-column with sidebar.
- Below `md`: sidebar hidden; main is full width. The header's right-side time block wraps via `flex-wrap`.
- No mobile drawer yet — open question if/when that becomes important.
