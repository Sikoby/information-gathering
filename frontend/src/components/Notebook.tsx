import { useState } from "react";
import { ChevronDown, ChevronRight, CircleHelp, ListTree } from "lucide-react";
import { Badge, Separator, cn } from "@ig/ui";
import {
  CLOSING_SECTION_ID,
  ROOT_SECTION_ID,
  childrenOf,
  childrenOfKind,
  isScheduled,
  pathTo,
  scheduledNodes,
} from "@/types";
import { relativeTime } from "@/lib/time";
import type { MeetingState, Section } from "@/types";

function AnswerCard({ answer }: { answer: Section }) {
  return (
    <li className="rounded-md border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium">{answer.header}</div>
        <div className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
          {answer.ts && relativeTime(answer.ts)}
        </div>
      </div>
      {answer.body && (
        <p className="mt-1 text-sm text-foreground/90">{answer.body}</p>
      )}
    </li>
  );
}

function QuestionBlock({
  question,
  state,
  isCurrent,
}: {
  question: Section;
  state: MeetingState;
  isCurrent: boolean;
}) {
  const answers = childrenOfKind(state.sections, question.id, "answer");
  const hasAnswers = answers.length > 0;
  const [expanded, setExpanded] = useState<boolean>(hasAnswers);

  return (
    <section id={`section-${question.id}`} className="scroll-mt-24">
      <div className="flex items-start gap-2">
        {hasAnswers ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse answers" : "Expand answers"}
            className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <span aria-hidden className="mt-1 h-5 w-5 shrink-0" />
        )}
        <CircleHelp
          aria-hidden
          className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground"
        />
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "text-sm font-medium leading-snug",
              isCurrent && "text-primary",
            )}
          >
            {isCurrent && (
              <span
                aria-hidden
                className="mr-1.5 inline-block h-2 w-2 rounded-full bg-primary align-middle"
              />
            )}
            {question.header}
          </p>
          <div className="mt-0.5 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
            <Badge
              variant={hasAnswers ? "secondary" : "outline"}
              className="text-[10px]"
            >
              {hasAnswers
                ? `${answers.length} answer${answers.length === 1 ? "" : "s"}`
                : "unanswered"}
            </Badge>
            {hasAnswers && !expanded && (
              <Badge variant="outline" className="text-[10px]">
                {answers.length} hidden
              </Badge>
            )}
          </div>
        </div>
      </div>
      {hasAnswers && expanded && (
        <ul className="mt-3 ml-2.5 space-y-2 border-l border-border pl-5">
          {answers.map((a) => (
            <AnswerCard key={a.id} answer={a} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TopicBlock({
  topic,
  state,
  depth,
  currentId,
  currentPath,
}: {
  topic: Section;
  state: MeetingState;
  depth: number;
  currentId: string;
  currentPath: Set<string>;
}) {
  const isCurrent = topic.id === currentId;
  const isOnCurrentPath = currentPath.has(topic.id);
  const scheduled = isScheduled(topic);
  const isClosing = topic.id === CLOSING_SECTION_ID;
  const children = childrenOf(state.sections, topic.id).filter(
    (s) => s.kind !== "answer",
  );
  const hasChildren = children.length > 0;

  // Default-collapsed if there are children AND this topic is not on the path
  // to the current section (and not a scheduled top-level "phase", which we
  // always want to see).
  const [expanded, setExpanded] = useState<boolean>(
    !hasChildren || isOnCurrentPath || scheduled,
  );
  const showChildren = hasChildren && expanded;

  const HeadingTag: keyof JSX.IntrinsicElements =
    depth === 1 ? "h3" : depth === 2 ? "h4" : "h5";

  return (
    <section
      id={`section-${topic.id}`}
      className={cn(
        "scroll-mt-24",
        isClosing && "rounded-md border-2 border-primary/40 bg-primary/5 p-4",
      )}
    >
      <div className="flex items-start gap-2">
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse" : "Expand"}
            className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <span aria-hidden className="mt-1 h-5 w-5 shrink-0" />
        )}
        <ListTree
          aria-hidden
          className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground"
        />
        <div className="min-w-0 flex-1">
          <HeadingTag
            className={cn(
              depth === 1 ? "text-base font-semibold" : "text-sm font-semibold",
              isCurrent && "text-primary",
            )}
          >
            {isCurrent && (
              <span
                aria-hidden
                className="mr-1.5 inline-block h-2 w-2 rounded-full bg-primary align-middle"
              />
            )}
            {topic.header}
          </HeadingTag>
          {(scheduled || isClosing || (hasChildren && !expanded)) && (
            <div className="mt-0.5 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
              {scheduled && topic.target_fraction != null && (
                <Badge variant="outline" className="text-[10px]">
                  {Math.round(topic.target_fraction * 100)}% of meeting
                </Badge>
              )}
              {isClosing && (
                <Badge variant="secondary" className="text-[10px]">
                  closing
                </Badge>
              )}
              {hasChildren && !expanded && (
                <Badge variant="outline" className="text-[10px]">
                  {children.length} hidden
                </Badge>
              )}
            </div>
          )}
          {topic.body && (
            <p className="mt-2 whitespace-pre-line text-sm text-foreground/85">
              {topic.body}
            </p>
          )}
        </div>
      </div>

      {showChildren && (
        <div
          className={cn(
            "mt-3 space-y-3",
            depth > 0 && "ml-2.5 border-l border-border pl-5",
          )}
        >
          {children.map((c) =>
            c.kind === "question" ? (
              <QuestionBlock
                key={c.id}
                question={c}
                state={state}
                isCurrent={c.id === currentId}
              />
            ) : (
              <TopicBlock
                key={c.id}
                topic={c}
                state={state}
                depth={depth + 1}
                currentId={currentId}
                currentPath={currentPath}
              />
            ),
          )}
        </div>
      )}
    </section>
  );
}

export function Notebook({
  state,
  className,
}: {
  state: MeetingState;
  className?: string;
}) {
  // Top-level layout: scheduled phases first, then non-scheduled top-level
  // topics (e.g. "other" and `_root/closing` when present). The root MEETING
  // node is not rendered — the BLUF/agenda live in the Header and Agenda.
  const scheduled = scheduledNodes(state.sections);
  const nonScheduled = childrenOf(state.sections, ROOT_SECTION_ID).filter(
    (s) => s.kind === "topic" && s.target_fraction == null,
  );

  // The set of section ids on the path from root to the current section.
  // TopicBlock keeps itself expanded when its id is on this path, so the
  // user can always see where the conversation is — no manual digging needed.
  const currentPath = new Set(
    pathTo(state.sections, state.current_section_id).map((s) => s.id),
  );

  return (
    <section id="notebook" className={cn("scroll-mt-24", className)}>
      <h2 className="text-lg font-semibold tracking-tight">Notebook</h2>
      <div className="mt-4 space-y-6">
        {scheduled.map((topic, idx) => (
          <div key={topic.id}>
            {idx > 0 && <Separator className="mb-6" />}
            <TopicBlock
              topic={topic}
              state={state}
              depth={1}
              currentId={state.current_section_id}
              currentPath={currentPath}
            />
          </div>
        ))}
        {nonScheduled.length > 0 && <Separator />}
        {nonScheduled.map((topic) => (
          <TopicBlock
            key={topic.id}
            topic={topic}
            state={state}
            depth={1}
            currentId={state.current_section_id}
            currentPath={currentPath}
          />
        ))}
      </div>
    </section>
  );
}
