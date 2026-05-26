import {
  ArrowDown,
  ArrowRightLeft,
  ArrowUp,
  Play,
  RotateCw,
} from "lucide-react";
import { Badge, cn } from "@ig/ui";
import { sectionById } from "@/types";
import { relativeTime } from "@/lib/time";
import type { MeetingState, Transition, TransitionKind } from "@/types";

function kindMeta(kind: TransitionKind): {
  Icon: typeof ArrowDown;
  variant: "default" | "secondary" | "outline" | "success" | "destructive" | "warning";
  label: string;
} {
  switch (kind) {
    case "drill_down":
      return { Icon: ArrowDown, variant: "secondary", label: "drill down" };
    case "zoom_out":
      return { Icon: ArrowUp, variant: "outline", label: "zoom out" };
    case "sibling":
      return { Icon: ArrowRightLeft, variant: "secondary", label: "sibling" };
    case "revisit":
      return { Icon: RotateCw, variant: "outline", label: "revisit" };
    case "open":
      return { Icon: Play, variant: "default", label: "open" };
  }
}

function TransitionRow({
  state,
  transition,
}: {
  state: MeetingState;
  transition: Transition;
}) {
  const { Icon, variant, label } = kindMeta(transition.kind);
  const to = sectionById(state.sections, transition.to_section_id);
  const from = transition.from_section_id
    ? sectionById(state.sections, transition.from_section_id)
    : null;

  return (
    <li className="rounded-md border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={variant} className="inline-flex items-center gap-1 text-[10px] uppercase">
          <Icon className="h-3 w-3" />
          {label}
        </Badge>
        {transition.crossed_phase_boundary && (
          <Badge variant="outline" className="text-[10px]">
            ↕ phase
          </Badge>
        )}
        <span className="font-mono text-[10px] text-muted-foreground">
          {from ? from.id : "(root)"} → {to ? to.id : transition.to_section_id}
        </span>
        <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground">
          {relativeTime(transition.ts)}
        </span>
      </div>
      <p className="mt-1 text-sm">
        <span className="text-muted-foreground">to: </span>
        <a
          href={`#section-${transition.to_section_id}`}
          className="font-medium hover:underline"
        >
          {to?.header ?? transition.to_section_id}
        </a>
      </p>
      {transition.recap && (
        <p className="mt-1 text-sm text-foreground/85">
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            recap
          </span>{" "}
          {transition.recap}
        </p>
      )}
      {transition.bridge && (
        <p className="mt-1 text-sm text-foreground/85">
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            bridge
          </span>{" "}
          {transition.bridge}
        </p>
      )}
      {transition.preview && (
        <p className="mt-1 text-sm text-foreground/85">
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            preview
          </span>{" "}
          {transition.preview}
        </p>
      )}
    </li>
  );
}

export function TransitionLog({
  state,
  className,
}: {
  state: MeetingState;
  className?: string;
}) {
  return (
    <section id="transitions" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Transitions</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {state.transitions.length} move{state.transitions.length === 1 ? "" : "s"} so far
      </p>
      {state.transitions.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground italic">
          (no transitions yet — waiting for the first navigate call)
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {state.transitions.map((t, idx) => (
            <TransitionRow key={idx} state={state} transition={t} />
          ))}
        </ul>
      )}
    </section>
  );
}
