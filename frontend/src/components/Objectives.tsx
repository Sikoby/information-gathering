import { Badge, cn } from "@ig/ui";
import type { MeetingState, ObjectiveStatus } from "@/types";

function statusVariant(status: ObjectiveStatus["status"]) {
  if (status === "covered") return "success" as const;
  if (status === "partial") return "warning" as const;
  return "outline" as const;
}

export function Objectives({ state, className }: { state: MeetingState; className?: string }) {
  const counts = { covered: 0, partial: 0, open: 0 };
  for (const id of Object.keys(state.tracker)) {
    counts[state.tracker[id].status] += 1;
  }
  const total = state.objectives.length;

  return (
    <section id="objectives" className={cn("scroll-mt-24", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Objectives</h2>
        <p className="text-xs text-muted-foreground">
          {counts.covered}/{total} covered · {counts.partial} partial · {counts.open} open
        </p>
      </div>
      <ul className="mt-4 space-y-3">
        {state.objectives.map((obj) => {
          const tr = state.tracker[obj.id];
          return (
            <li key={obj.id} className="rounded-md border bg-card p-3">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  {obj.id}
                </Badge>
                <Badge variant={statusVariant(tr?.status ?? "open")}>
                  {tr?.status ?? "open"}
                </Badge>
              </div>
              <p className="mt-2 text-sm font-medium">{obj.objective}</p>
              <p className="mt-1 text-xs text-muted-foreground">{obj.success_criteria}</p>
              {tr?.note && (
                <p className="mt-2 text-xs italic text-foreground/80">"{tr.note}"</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
