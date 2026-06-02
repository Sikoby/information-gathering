# CLAUDE.md — shared/ (`@ig/ui`)

> **Rule of the house:** any substantial change to what the shared library exports, how apps consume it, or its build/Tailwind contract MUST update this file in the same commit. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## What this is

The shared component library for both React apps — the meeting viewer ([`../frontend/`](../frontend/)) and the meeting console ([`../console-frontend/`](../console-frontend/)). Package name `@ig/ui`. It exists so the design-system primitives and theme live in exactly one place.

It is an **npm workspace** package (the repo root `package.json` declares `["shared", "frontend", "console-frontend"]`). Consumed as **source** — no build step — via the workspace symlink; Vite and each app's `tsc` compile its `.tsx` directly.

## What belongs here

- `src/components/ui/*` — shadcn (new-york) primitives: `alert`, `badge`, `button`, `card`, `collapsible`, `dropdown-menu`, `input`, `progress`, `separator`, `textarea`, `tooltip`; plus generic app-shell layout bars `header` + `footer` (a styled `<header>`/`<footer>` with a centered `max-w-6xl` container — apps pass the brand/actions/footer content as children). `tooltip` also exports `InfoTooltip` — a self-contained info-`(i)`-icon-with-tooltip (embeds its own `TooltipProvider`, so it is drop-in with no app-root wiring). Depends on `@radix-ui/react-tooltip` and `lucide-react`.
- `src/lib/utils.ts` — `cn()` (clsx + tailwind-merge).
- `src/types.ts` — `Template`, `Section`, `SectionKind` and pure tree-walk helpers (`sectionById`, `childrenOf`, `pathTo`, `scheduledNodes`, `enclosingPhase`, …) — used by both apps; mirror `src/templates/schema.py`.
- `tailwind-preset.cjs` — the shared Tailwind theme (colors, radius, animation).
- `src/index.ts` — the barrel that re-exports everything.

App-specific components, hooks, and types stay in the app, not here. Adding a new shadcn primitive: add it under `src/components/ui/` (import `cn` from `../../lib/utils`) and export it from `src/index.ts`.

## How apps consume it

- Components / utils / types: `import { Button, cn, type Template } from "@ig/ui"`.
- Tailwind: each app's `tailwind.config.js` does `presets: [require-or-import "@ig/ui/tailwind-preset"]` **and** must include `"../shared/src/**/*.{ts,tsx}"` in `content` — otherwise classes used only by shared components are purged from production builds.
- Each app also defines the theme CSS variables (`--background`, ...) in its own `index.css`; the preset references them via `hsl(var(--...))`.

## Build & verify

- Installed from the repo root: `npm install`.
- `npm run typecheck -w shared` — `tsc --noEmit`.
- The real check is that both apps build: `npm run build -w frontend` and `npm run build -w console-frontend`.

## Not a container

`shared/` ships no container. It is copied into the `webapp` and `console-frontend` Docker build stages (both `npm ci` within the workspace) and compiled into each app's bundle.
