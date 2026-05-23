import { Check, Circle } from "lucide-react";
import {
  childrenOfKind,
  descendantsOf,
  enclosingPhase,
  scheduledNodes,
  type MeetingState,
  type Section,
} from "@/types";
import { cn } from "@/lib/utils";

type PhaseStatus = "visited" | "current" | "upcoming";

function phaseStatus(
  phase: Section,
  visited: Set<string>,
  currentPhaseId: string | undefined,
): PhaseStatus {
  if (phase.id === currentPhaseId) return "current";
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

function questionStats(state: MeetingState, phase: Section): { answered: number; total: number } {
  const questions = descendantsOf(state.sections, phase.id).filter(
    (s) => s.kind === "question",
  );
  let answered = 0;
  for (const q of questions) {
    if (childrenOfKind(state.sections, q.id, "answer").length > 0) answered += 1;
  }
  return { answered, total: questions.length };
}

export function Agenda({ state, className }: { state: MeetingState; className?: string }) {
  const phases = scheduledNodes(state.sections);
  const currentPhase = enclosingPhase(state.sections, state.current_section_id);
  const visited = new Set<string>();
  for (const t of state.transitions) {
    const ph = enclosingPhase(state.sections, t.to_section_id);
    if (ph) visited.add(ph.id);
  }
  if (currentPhase) visited.add(currentPhase.id);

  return (
    <section id="agenda" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Agenda</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {phases.length} phase{phases.length === 1 ? "" : "s"}
        {currentPhase && (
          <>
            {" · current is "}
            <span className="font-medium text-foreground">{currentPhase.header}</span>
          </>
        )}
      </p>

      <ol className="relative mt-4 space-y-4 border-l border-border pl-0">
        {phases.map((phase, idx) => {
          const status = phaseStatus(phase, visited, currentPhase?.id);
          const isCurrent = status === "current";
          const isLast = idx === phases.length - 1;
          const { answered, total } = questionStats(state, phase);
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
                    {phase.header}
                  </h3>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {phase.target_fraction != null
                      ? `${Math.round(phase.target_fraction * 100)}% of meeting`
                      : ""}
                  </span>
                </div>
                {phase.body && (
                  <p
                    className={cn(
                      "mt-1 text-sm",
                      status === "upcoming"
                        ? "text-muted-foreground/80"
                        : "text-foreground/90",
                    )}
                  >
                    {phase.body}
                  </p>
                )}
                {total > 0 && (
                  <p className="mt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {answered}/{total} questions answered
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
