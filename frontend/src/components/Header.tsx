import { useEffect, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Progress,
  Separator,
  cn,
} from "@ig/ui";
import { extractMeetingTitle } from "@/lib/briefing";
import { elapsedFraction, formatElapsed } from "@/lib/time";
import type { EndReason, MeetingState } from "@/types";

function endVariant(reason: EndReason): "destructive" | "success" | "default" {
  if (reason === "blocked") return "destructive";
  if (reason === "objectives_met") return "success";
  return "default";
}

function endLabel(reason: EndReason): string {
  switch (reason) {
    case "objectives_met":
      return "Objectives met";
    case "time_up":
      return "Time up";
    case "user_ended":
      return "Ended by stakeholder";
    case "blocked":
      return "Blocked";
    default:
      return "";
  }
}

export function Header({ state, className }: { state: MeetingState; className?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (state.end_reason) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [state.end_reason]);

  const title = extractMeetingTitle(state.briefing_markdown, state.template.name);
  const currentPhase = state.template.phases.find((p) => p.id === state.current_phase);
  const fraction = elapsedFraction(state.started_at, state.target_minutes, now);

  if (state.end_reason) {
    const finalElapsed = state.ended_at
      ? formatElapsed(state.started_at, new Date(state.ended_at).getTime())
      : formatElapsed(state.started_at, now);
    return (
      <header className={cn("border-b bg-background", className)}>
        <div className="mx-auto max-w-7xl px-6 py-6 space-y-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            <Badge variant="secondary" className="mt-2 uppercase tracking-wide">
              {state.template.name}
            </Badge>
          </div>
          <Alert variant={endVariant(state.end_reason)}>
            <AlertTitle className="text-base">
              Meeting ended — {endLabel(state.end_reason)}
            </AlertTitle>
            <AlertDescription>
              Final elapsed {finalElapsed} / {state.target_minutes}:00 ·{" "}
              {state.user_turn_count} stakeholder turns
            </AlertDescription>
          </Alert>
        </div>
      </header>
    );
  }

  const elapsed = formatElapsed(state.started_at, now);

  return (
    <header className={cn("border-b bg-background", className)}>
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight truncate">{title}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="secondary" className="uppercase tracking-wide">
                {state.template.name}
              </Badge>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg tabular-nums">
                {elapsed}{" "}
                <span className="text-muted-foreground text-base">
                  / {state.target_minutes}:00
                </span>
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <Badge variant="secondary">{state.user_turn_count} turns</Badge>
              <Badge variant="outline" className="font-mono" title={`run_id ${state.run_id}`}>
                {state.run_id.slice(0, 16)}
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {currentPhase && (
            <Badge variant="default" className="uppercase tracking-wide" title={currentPhase.goal}>
              {currentPhase.label}
            </Badge>
          )}
          <div className="flex-1">
            <Progress
              value={fraction * 100}
              title={`Elapsed ${Math.round(fraction * 100)}% of target`}
            />
          </div>
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            {Math.round(fraction * 100)}%
          </span>
        </div>
      </div>
      <Separator />
    </header>
  );
}
