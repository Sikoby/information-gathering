import { Check, Circle } from "lucide-react";
import {
  Badge,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  cn,
} from "@ig/ui";
import { relativeTime } from "@/lib/time";
import type { MeetingState, Phase } from "@/types";

type PhaseStatus = "visited" | "current" | "upcoming";

function phaseStatus(phase: Phase, state: MeetingState, visited: Set<string>): PhaseStatus {
  if (phase.id === state.current_phase) return "current";
  if (visited.has(phase.id)) return "visited";
  return "upcoming";
}

function Marker({ status }: { status: PhaseStatus }) {
  return (
    <div
      className={cn(
        "relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2",
        status === "current" && "border-primary bg-primary text-primary-foreground",
        status === "visited" && "border-primary bg-primary text-primary-foreground",
        status === "upcoming" && "border-muted-foreground/40 bg-background text-muted-foreground",
      )}
      aria-label={status}
    >
      {status === "visited" ? (
        <Check className="h-3 w-3" />
      ) : status === "current" ? (
        <Circle className="h-2 w-2 fill-current" />
      ) : null}
    </div>
  );
}

export function Agenda({ state, className }: { state: MeetingState; className?: string }) {
  const visited = new Set(state.phase_history.map((t) => t.phase_id));
  visited.add(state.current_phase);
  const sectionLabel = (id: string) =>
    state.template.sections.find((s) => s.id === id)?.label ?? id;

  return (
    <section id="agenda" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Agenda</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {state.template.phases.length} phases · current is{" "}
        <span className="font-medium text-foreground">
          {state.template.phases.find((p) => p.id === state.current_phase)?.label ??
            state.current_phase}
        </span>
      </p>

      <ol className="relative mt-4 space-y-4 border-l border-border pl-0">
        {state.template.phases.map((phase, idx) => {
          const status = phaseStatus(phase, state, visited);
          const isCurrent = status === "current";
          const isLast = idx === state.template.phases.length - 1;
          return (
            <li key={phase.id} className="relative pl-10">
              <div className="absolute left-0 top-0 -translate-x-1/2">
                <Marker status={status} />
              </div>
              {!isLast && (
                <span
                  aria-hidden
                  className="absolute left-0 top-6 h-[calc(100%+1rem)] w-px bg-border"
                />
              )}
              <div
                className={cn(
                  "rounded-md transition-colors",
                  isCurrent && "bg-primary/5 ring-1 ring-primary/30 p-3 -mx-3",
                )}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3
                    className={cn(
                      "text-base font-semibold",
                      status === "upcoming" && "text-muted-foreground",
                    )}
                  >
                    {phase.label}
                  </h3>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {Math.round(phase.target_fraction * 100)}% of meeting
                  </span>
                </div>
                <p
                  className={cn(
                    "mt-1 text-sm",
                    status === "upcoming"
                      ? "text-muted-foreground/80"
                      : "text-foreground/90",
                  )}
                >
                  {phase.goal}
                </p>
                {phase.sections_in_focus.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {phase.sections_in_focus.map((sid) => (
                      <Badge key={sid} variant="outline" className="text-[10px]">
                        {sectionLabel(sid)}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {state.phase_history.length > 0 && (
        <Collapsible className="mt-4">
          <CollapsibleTrigger className="text-xs text-muted-foreground hover:text-foreground">
            {state.phase_history.length} phase transition
            {state.phase_history.length === 1 ? "" : "s"} — show
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-1 text-xs">
            {state.phase_history.map((t, idx) => (
              <div key={idx} className="flex gap-2">
                <span className="font-mono text-muted-foreground">{relativeTime(t.ts)}</span>
                <span className="font-medium">→ {t.phase_id}</span>
                {t.note && <span className="text-muted-foreground">— {t.note}</span>}
              </div>
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  );
}
