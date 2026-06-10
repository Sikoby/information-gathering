import { cn } from "@ig/ui";
import { ROOT_SECTION_ID, pathTo, sectionById } from "@/types";
import type { MeetingState, Section } from "@/types";

function kindGlyph(s: Section): string {
  switch (s.kind) {
    case "meeting":
      return "🏛";
    case "topic":
      return "▸";
    case "question":
      return "?";
    case "answer":
      return "✎";
  }
}

export function Breadcrumb({
  state,
  className,
}: {
  state: MeetingState;
  className?: string;
}) {
  const chain = pathTo(state.sections, state.current_section_id);
  if (chain.length === 0) {
    const root = sectionById(state.sections, ROOT_SECTION_ID);
    return (
      <section id="breadcrumb" className={cn("scroll-mt-24", className)}>
        <h2 className="text-lg font-semibold tracking-tight">Position</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Current section unknown
          {root && (
            <>
              {" "}— at root <span className="font-mono">{root.id}</span>
            </>
          )}
          .
        </p>
      </section>
    );
  }

  return (
    <section id="breadcrumb" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Position</h2>
      <nav aria-label="Breadcrumb" className="mt-2 flex flex-wrap items-center gap-1">
        {chain.map((s, idx) => {
          const isLast = idx === chain.length - 1;
          return (
            <span key={s.id} className="flex items-center gap-1">
              <a
                href={`#section-${s.id}`}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs",
                  isLast
                    ? "border-primary/50 bg-primary/10 text-foreground font-medium"
                    : "border-border bg-card text-muted-foreground hover:text-foreground",
                )}
                title={s.body ?? undefined}
              >
                <span aria-hidden className="opacity-70">
                  {kindGlyph(s)}
                </span>
                <span className="max-w-[14rem] truncate">
                  {s.id === ROOT_SECTION_ID ? "Meeting" : s.header}
                </span>
              </a>
              {!isLast && (
                <span aria-hidden className="text-muted-foreground">
                  ›
                </span>
              )}
            </span>
          );
        })}
      </nav>
    </section>
  );
}
