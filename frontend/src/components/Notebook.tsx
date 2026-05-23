import { CircleHelp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { relativeTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import {
  childrenOf,
  childrenOfKind,
  ROOT_SECTION_ID,
  sectionById,
  type MeetingState,
  type Section,
} from "@/types";

function MeetingCard({
  state,
  node,
  children,
}: {
  state: MeetingState;
  node: Section;
  children: Section[];
}) {
  const phases = children.filter((c) => c.kind === "phase");
  const framed = !!node.header && node.header !== "Meeting";
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
        Meeting frame
      </p>
      {framed ? (
        <>
          <h3 className="mt-1 text-lg font-semibold leading-tight">
            {node.header}
          </h3>
          {node.body && (
            <p className="mt-2 text-sm whitespace-pre-wrap text-foreground/90">
              {node.body}
            </p>
          )}
        </>
      ) : (
        <p className="mt-1 text-sm italic text-muted-foreground">
          Not yet framed — agent will call <code>frame_meeting</code> with the
          BLUF and SCQA.
        </p>
      )}
      {phases.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground mr-1 self-center">
            Agenda
          </span>
          {phases.map((p) => (
            <Badge
              key={p.id}
              variant={p.id === state.current_section_id ? "default" : "outline"}
              className="text-[10px]"
            >
              {p.header}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function PhaseBlock({
  state,
  node,
  depth,
}: {
  state: MeetingState;
  node: Section;
  depth: number;
}) {
  const pct = node.target_fraction != null
    ? `${Math.round(node.target_fraction * 100)}% of meeting`
    : null;
  const current = state.current_section_id === node.id;
  return (
    <section
      id={`section-${node.id}`}
      className="scroll-mt-24 rounded-md border bg-card p-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3
          className={cn(
            "text-base font-semibold",
            current && "text-primary",
          )}
        >
          {current && (
            <span
              aria-hidden
              className="mr-1.5 inline-block h-2 w-2 rounded-full bg-primary align-middle"
            />
          )}
          {node.header}
        </h3>
        {pct && (
          <Badge variant="outline" className="text-[10px]">
            {pct}
          </Badge>
        )}
      </div>
      {node.body && (
        <p className="mt-1 text-sm text-foreground/90">{node.body}</p>
      )}
      <ChildList state={state} parentId={node.id} depth={depth + 1} />
    </section>
  );
}

function TopicBlock({
  state,
  node,
  depth,
}: {
  state: MeetingState;
  node: Section;
  depth: number;
}) {
  const current = state.current_section_id === node.id;
  const indent = Math.min(depth, 4) * 8; // mild indent per depth
  return (
    <section
      id={`section-${node.id}`}
      className="scroll-mt-24"
      style={{ marginLeft: indent }}
    >
      <h4
        className={cn(
          "text-sm font-semibold",
          current && "text-primary",
        )}
      >
        {current && (
          <span
            aria-hidden
            className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-primary align-middle"
          />
        )}
        {node.header}
      </h4>
      {node.body && (
        <p className="mt-0.5 text-xs text-muted-foreground">{node.body}</p>
      )}
      <ChildList state={state} parentId={node.id} depth={depth + 1} />
    </section>
  );
}

function QuestionBlock({
  state,
  node,
  depth,
}: {
  state: MeetingState;
  node: Section;
  depth: number;
}) {
  const answers = childrenOfKind(state.sections, node.id, "answer");
  const current = state.current_section_id === node.id;
  const indent = Math.min(depth, 4) * 8;
  return (
    <div
      id={`section-${node.id}`}
      className="scroll-mt-24 mt-2"
      style={{ marginLeft: indent }}
    >
      <div className="flex items-baseline gap-2">
        <CircleHelp
          className={cn(
            "h-3.5 w-3.5 shrink-0 self-center",
            current ? "text-primary" : "text-muted-foreground",
          )}
        />
        <p
          className={cn(
            "text-sm",
            current && "text-primary font-medium",
            answers.length === 0 && !current && "text-muted-foreground",
          )}
        >
          {node.header}
        </p>
        {answers.length > 0 ? (
          <Badge variant="secondary" className="text-[10px]">
            {answers.length} answer{answers.length === 1 ? "" : "s"}
          </Badge>
        ) : (
          <Badge variant="outline" className="text-[10px]">
            unanswered
          </Badge>
        )}
      </div>
      {answers.length > 0 && (
        <ul className="mt-2 space-y-2">
          {answers.map((a) => (
            <li key={a.id} className="rounded-md border bg-card p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium text-sm">{a.header}</div>
                {a.ts && (
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground shrink-0">
                    {relativeTime(a.ts)}
                  </div>
                )}
              </div>
              {a.body && (
                <p className="mt-1 text-sm text-foreground/90 whitespace-pre-wrap">
                  {a.body}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      <ChildList state={state} parentId={node.id} depth={depth + 1} />
    </div>
  );
}

function ClosingBlock({ node }: { node: Section }) {
  return (
    <section
      id={`section-${node.id}`}
      className="scroll-mt-24 rounded-lg border-2 border-primary/30 bg-primary/5 p-4"
    >
      <p className="text-[10px] uppercase tracking-wide text-primary">
        Closing summary
      </p>
      <h3 className="mt-1 text-base font-semibold">{node.header}</h3>
      {node.body && (
        <p className="mt-2 text-sm whitespace-pre-wrap text-foreground/90">
          {node.body}
        </p>
      )}
    </section>
  );
}

function ChildList({
  state,
  parentId,
  depth,
}: {
  state: MeetingState;
  parentId: string;
  depth: number;
}) {
  const kids = childrenOf(state.sections, parentId)
    .filter((c) => c.kind !== "answer"); // answers render inside their question parent
  if (kids.length === 0) return null;
  return (
    <div className="mt-2 space-y-2">
      {kids.map((c) => (
        <SectionNode key={c.id} state={state} node={c} depth={depth} />
      ))}
    </div>
  );
}

function SectionNode({
  state,
  node,
  depth,
}: {
  state: MeetingState;
  node: Section;
  depth: number;
}) {
  switch (node.kind) {
    case "phase":
      return <PhaseBlock state={state} node={node} depth={depth} />;
    case "topic":
      return <TopicBlock state={state} node={node} depth={depth} />;
    case "question":
      return <QuestionBlock state={state} node={node} depth={depth} />;
    case "closing":
      return <ClosingBlock node={node} />;
    default:
      return null; // meeting handled separately; answer rendered inside its question
  }
}

export function Notebook({ state, className }: { state: MeetingState; className?: string }) {
  const root = sectionById(state.sections, ROOT_SECTION_ID);
  const rootChildren = childrenOf(state.sections, ROOT_SECTION_ID);
  const phases = rootChildren.filter((c) => c.kind === "phase");
  const topLevelTopics = rootChildren.filter((c) => c.kind === "topic");
  const closing = rootChildren.find((c) => c.kind === "closing");

  return (
    <section id="notebook" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Notebook</h2>

      {root && (
        <div className="mt-4">
          <MeetingCard state={state} node={root} children={rootChildren} />
        </div>
      )}

      {phases.length > 0 && (
        <div className="mt-6 space-y-4">
          {phases.map((p, idx) => (
            <div key={p.id}>
              {idx > 0 && <Separator className="mb-4" />}
              <PhaseBlock state={state} node={p} depth={1} />
            </div>
          ))}
        </div>
      )}

      {topLevelTopics.length > 0 && (
        <div className="mt-6 space-y-3">
          <Separator />
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Catch-all
          </p>
          {topLevelTopics.map((t) => (
            <TopicBlock key={t.id} state={state} node={t} depth={1} />
          ))}
        </div>
      )}

      {closing && (
        <div className="mt-6">
          <ClosingBlock node={closing} />
        </div>
      )}
    </section>
  );
}
