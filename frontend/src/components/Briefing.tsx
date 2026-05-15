import { ChevronDown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { MeetingState } from "@/types";

export function Briefing({ state, className }: { state: MeetingState; className?: string }) {
  return (
    <section id="briefing" className={cn("scroll-mt-24", className)}>
      <Collapsible>
        <CollapsibleTrigger className="group flex w-full items-center justify-between gap-2 text-left">
          <h2 className="text-lg font-semibold tracking-tight">Briefing</h2>
          <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-4">
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown>{state.briefing_markdown}</ReactMarkdown>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </section>
  );
}
