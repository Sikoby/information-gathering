import { ArrowDown, ArrowUp, ArrowRightLeft, RotateCw, Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import { sectionById, type MeetingState, type TransitionKind } from "@/types";

function kindIcon(kind: TransitionKind) {
  switch (kind) {
    case "drill_down":
      return <ArrowDown className="h-3 w-3" aria-hidden />;
    case "zoom_out":
      return <ArrowUp className="h-3 w-3" aria-hidden />;
    case "sibling":
      return <ArrowRightLeft className="h-3 w-3" aria-hidden />;
    case "revisit":
      return <RotateCw className="h-3 w-3" aria-hidden />;
    case "open":
      return <Play className="h-3 w-3" aria-hidden />;
  }
}

function kindVariant(kind: TransitionKind): "default" | "secondary" | "outline" {
  if (kind === "open") return "default";
  if (kind === "drill_down" || kind === "zoom_out") return "secondary";
  return "outline";
}

export function TransitionLog({ state, className }: { state: MeetingState; className?: string }) {
  return (
    <section id="transitions" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Transitions</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {state.transitions.length} move{state.transitions.length === 1 ? "" : "s"}
      </p>
      {state.transitions.length === 0 ? (
        <p className="mt-4 text-sm italic text-muted-foreground">
          (no transitions yet)
        </p>
      ) : (
        <ol className="mt-4 space-y-2">
          {state.transitions.map((t, idx) => {
            const toNode = sectionById(state.sections, t.to_section_id);
            const fromNode = t.from_section_id
              ? sectionById(state.sections, t.from_section_id)
              : null;
            const fromLabel = fromNode?.header ?? t.from_section_id ?? "(start)";
            const toLabel = toNode?.header ?? t.to_section_id;
            return (
              <li
                key={idx}
                className="rounded-md border bg-card p-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={kindVariant(t.kind)} className="gap-1 text-[10px]">
                    {kindIcon(t.kind)}
                    {t.kind}
                  </Badge>
                  {t.crossed_phase_boundary && (
                    <Badge variant="outline" className="text-[10px]" title="Crossed a phase boundary">
                      ↕ phase
                    </Badge>
                  )}
                  <span className="text-muted-foreground truncate">
                    {fromLabel} → <span className="text-foreground font-medium">{toLabel}</span>
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                    {relativeTime(t.ts)}
                  </span>
                </div>
                {(t.recap || t.bridge || t.preview) && (
                  <div className="mt-1 space-y-0.5 pl-1 text-[11px] text-muted-foreground">
                    {t.recap && <p>recap: {t.recap}</p>}
                    {t.bridge && <p>bridge: {t.bridge}</p>}
                    {t.preview && <p>preview: {t.preview}</p>}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
