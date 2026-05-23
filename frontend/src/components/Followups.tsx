import { relativeTime } from "@/lib/time";
import { cn } from "@ig/ui";
import type { Followup, MeetingState } from "@/types";

function ItemList({ items }: { items: Followup[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground italic">(none yet)</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((f, idx) => (
        <li key={idx} className="flex items-start justify-between gap-2 text-sm">
          <span>{f.item}</span>
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground shrink-0">
            {relativeTime(f.ts)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Followups({ state, className }: { state: MeetingState; className?: string }) {
  const actions = state.followups.filter((f) => f.kind === "action");
  const questions = state.followups.filter((f) => f.kind === "open_question");

  return (
    <section id="followups" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Follow-ups</h2>
      <div className="mt-4 space-y-4">
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Actions
          </h3>
          <ItemList items={actions} />
        </div>
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Open questions
          </h3>
          <ItemList items={questions} />
        </div>
      </div>
    </section>
  );
}
