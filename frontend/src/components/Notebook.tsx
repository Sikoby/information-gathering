import { AlertTriangle } from "lucide-react";
import { Badge, Separator, cn } from "@ig/ui";
import { relativeTime } from "@/lib/time";
import type { MeetingState, NotebookEntry, NotebookSection } from "@/types";

function SectionBlock({
  section,
  entries,
  highlighted,
}: {
  section: NotebookSection;
  entries: NotebookEntry[];
  highlighted: boolean;
}) {
  const overFilled = !section.repeated && entries.length > 1;

  return (
    <section id={`section-${section.id}`} className="scroll-mt-24">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3
            className={cn(
              "text-base font-semibold",
              highlighted && "text-primary",
            )}
          >
            {highlighted && (
              <span
                aria-hidden
                className="mr-1.5 inline-block h-2 w-2 rounded-full bg-primary align-middle"
              />
            )}
            {section.label}{" "}
            <span className="text-muted-foreground font-normal">({entries.length})</span>
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{section.description}</p>
        </div>
        {overFilled && (
          <span
            className="inline-flex items-center gap-1 text-xs text-warning"
            title="This section is marked single-entry but has multiple entries"
          >
            <AlertTriangle className="h-3 w-3" />
            multiple
          </span>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground italic">(empty)</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {entries.map((e, idx) => (
            <li key={idx} className="rounded-md border bg-card p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium text-sm">{e.title}</div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground shrink-0">
                  {relativeTime(e.ts)}
                </div>
              </div>
              <p className="mt-1 text-sm text-foreground/90">{e.content}</p>
              {e.objective_ids.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {e.objective_ids.map((id) => (
                    <Badge key={id} variant="outline" className="text-[10px]">
                      {id}
                    </Badge>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function Notebook({ state, className }: { state: MeetingState; className?: string }) {
  const currentPhase = state.template.phases.find((p) => p.id === state.current_phase);
  const focusIds = new Set(currentPhase?.sections_in_focus ?? []);

  return (
    <section id="notebook" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Notebook</h2>
      <div className="mt-4 space-y-6">
        {state.template.sections.map((section, idx) => (
          <div key={section.id}>
            {idx > 0 && <Separator className="mb-6" />}
            <SectionBlock
              section={section}
              entries={state.notebook[section.id] ?? []}
              highlighted={focusIds.has(section.id)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
