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
│  │ Sidebar  │  │ Breadcrumb (where we are in the tree)│  │
│  │ (sticky) │  │ ─── Separator ───                    │  │
│  │          │  │ Agenda (filtered view of phases)     │  │
│  │ Position │  │ ─── Separator ───                    │  │
│  │ Agenda   │  │ Notebook (recursive Section tree)    │  │
│  │ Notebook │  │ ─── Separator ───                    │  │
│  │  - rapport│ │ Transitions (typed nav log)          │  │
│  │  - define│  │ ─── Separator ───                    │  │
│  │  - ...   │  │ Follow-ups                           │  │
│  │ Transitn │  │ ─── Separator ───                    │  │
│  │ Followup │  │ Briefing (collapsible)               │  │
│  │ Briefing │  │                                      │  │
│  └──────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

Container `max-w-7xl mx-auto px-6`. Body grid `md:grid-cols-[12rem_1fr] gap-8`. Header is outside the container so its bottom border spans the viewport. The sidebar is hidden below `md`.

## The data model — one tree of `Section` nodes

The backend (`src/templates/schema.py` + `src/harness.py`) represents a meeting as a single tree of `Section` nodes. Each node carries a `kind`:

| kind | role | rendered by |
| --- | --- | --- |
| `meeting` | the root; `header` = BLUF, `body` = SCQA | `Notebook.MeetingCard` |
| `phase` | tier with a time budget (`target_fraction`) | `Notebook.PhaseBlock`, `Agenda` |
| `topic` | branch / area of inquiry | `Notebook.TopicBlock` |
| `question` | something to ask the stakeholder | `Notebook.QuestionBlock` |
| `answer` | a recorded finding (created at runtime) | `Notebook.QuestionBlock` (under its parent) |
| `closing` | the pyramid wrap (created at runtime) | `Notebook.ClosingBlock` |

Helpers in `types.ts` walk the tree: `childrenOf`, `descendantsOf`, `pathTo`, `enclosingPhase`, `scheduledNodes` (the PHASE filter — basis of the Agenda), `answersUnder`.

## Section convention

Top-level page sections are rendered as

```tsx
<section id="<id>" className="scroll-mt-24">
  <h2 className="text-lg font-semibold tracking-tight">Label</h2>
  ...
</section>
```

Rules:

- **Sections are not wrapped in `Card`.** Between top-level sections, use a shadcn `<Separator />` (placed in `App.tsx` between siblings).
- Anchor `id`s are stable: `breadcrumb`, `agenda`, `notebook`, `section-<sectionId>`, `transitions`, `followups`, `briefing`. The Sidebar reads these.
- `scroll-mt-24` keeps headings clear of the fixed header on smooth-scroll.

`Card`-like styling is reserved for **items** — a single answer, a single phase block. Items use `rounded-md border bg-card p-3` (or a thicker border for emphasis cards: meeting frame, closing summary).

## Typography

| Role | Tailwind |
| --- | --- |
| Meeting title | `text-2xl font-semibold tracking-tight` |
| Section `<h2>` | `text-lg font-semibold tracking-tight` |
| Phase / closing card heading | `text-base font-semibold` |
| Topic heading | `text-sm font-semibold` |
| Body | `text-sm` |
| Muted detail | `text-xs text-muted-foreground` |
| Micro tag (timestamps, percentages, kind chips) | `text-[10px] uppercase tracking-wide text-muted-foreground` |
| Monospace numbers (elapsed) | `font-mono tabular-nums` |

## State cues

| State | Style |
| --- | --- |
| Current node (any kind) | `text-primary` heading, small `bg-primary` dot prefix; in Agenda, `ring-1 ring-primary/30` on the row |
| Visited phase | Filled `bg-primary` marker, `Check` icon |
| Upcoming phase | Outline marker, `text-muted-foreground` |
| Unanswered QUESTION | Outline "unanswered" badge |
| Answered QUESTION | Secondary badge with answer count |
| Transition crossed a phase boundary | Outline "↕ phase" chip in the transition log |
| Transition kind | Coloured badge in TransitionLog with directional lucide icon |
| Closing summary present | Bordered card with `bg-primary/5` + `border-primary/30` |
| Meeting unframed | Italic "Not yet framed" line in the MeetingCard |

## Transition kinds

The agent's `navigate()` tool moves the active node within the section tree. Each move has a computed `kind` (the system decides from the tree, the agent doesn't have to label):

| kind | meaning | icon |
| --- | --- | --- |
| `open` | first move out of `_root` | ▶ Play |
| `drill_down` | into a direct child | ↓ ArrowDown |
| `zoom_out` | to an ancestor | ↑ ArrowUp |
| `sibling` | sideways under same parent | ↔ ArrowRightLeft |
| `revisit` | back to a previously-visited non-ancestor / non-child | ↻ RotateCw |

`crossed_phase_boundary` is independent of kind: true when the enclosing phase changed. Shown as a "↕ phase" chip.

## shadcn components in use

| Component | Used by | Purpose |
| --- | --- | --- |
| `Badge` | Header, Agenda, Notebook, TransitionLog | Pills (phase, template, answer counts, kind chips) |
| `Progress` | Header | Linear elapsed-vs-target indicator |
| `Separator` | App, Notebook | Divide sections |
| `Collapsible` | Briefing | Expand/collapse |
| `Alert` | Header (end-of-meeting) | Terminal state banner |
| `Card` | Item rows only — never wraps a section |

## Data flow

1. `App.tsx` reads `runId` from the URL pathname.
2. `useSnapshot(runId)` fetches `/state` then opens an SSE stream at `/<runId>/events`. Every message replaces the local `MeetingState`.
3. Each component takes `{ state }: { state: MeetingState }` and renders pure functions of state.
4. The meeting title is derived client-side from `state.briefing_markdown` via `extractMeetingTitle` (`lib/briefing.ts`). The backend does not send a title field.
5. The active phase is derived: `enclosingPhase(state.sections, state.current_section_id)`.

## Sidebar / scroll

- `Sidebar.tsx` uses an `IntersectionObserver` (`rootMargin: -20% 0px -60% 0px`) to highlight the section nearest the top of the viewport.
- The sidebar's Notebook subtree is generated from the live PHASE/TOPIC nodes (`scheduledNodes` + their TOPIC children).
- Click handlers call `scrollIntoView({ behavior: "smooth" })` and update the URL hash via `history.replaceState`.

## Responsive

- `md` (≥ 768px): two-column with sidebar.
- Below `md`: sidebar hidden; main is full width. The header's right-side time block wraps via `flex-wrap`.
