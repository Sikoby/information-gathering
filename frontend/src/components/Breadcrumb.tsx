import { ChevronRight } from "lucide-react";
import { pathTo, type MeetingState, type Section } from "@/types";
import { cn } from "@/lib/utils";

function kindGlyph(kind: Section["kind"]): string {
  switch (kind) {
    case "meeting":
      return "◆";
    case "phase":
      return "▶";
    case "topic":
      return "•";
    case "question":
      return "?";
    case "answer":
      return "→";
    case "closing":
      return "★";
  }
}

export function Breadcrumb({ state, className }: { state: MeetingState; className?: string }) {
  const chain = pathTo(state.sections, state.current_section_id);

  return (
    <nav
      id="breadcrumb"
      aria-label="Tree position"
      className={cn("scroll-mt-24 text-sm", className)}
    >
      <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        Tree position
      </p>
      <ol className="flex flex-wrap items-center gap-1">
        {chain.map((node, idx) => {
          const isLast = idx === chain.length - 1;
          return (
            <li key={node.id} className="flex items-center gap-1">
              <a
                href={`#section-${node.id}`}
                title={`${node.kind}: ${node.id}`}
                className={cn(
                  "inline-flex items-center gap-1 rounded px-1.5 py-0.5",
                  isLast
                    ? "bg-secondary font-medium text-foreground"
                    : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
                )}
              >
                <span aria-hidden className="text-[10px] opacity-70">
                  {kindGlyph(node.kind)}
                </span>
                <span className="truncate max-w-[20ch]">{node.header}</span>
              </a>
              {!isLast && (
                <ChevronRight className="h-3 w-3 text-muted-foreground" aria-hidden />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
