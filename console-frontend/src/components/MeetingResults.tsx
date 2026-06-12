import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
} from "lucide-react";
import { IconButton } from "@/components/IconButton";
import {
  OTHER_QUESTION_ID,
  OTHER_SECTION_ID,
  ROOT_SECTION_ID,
  answersUnder,
  childrenOf,
} from "@/types";
import type { MeetingResults, Section, TranscriptLine } from "@/types";
import { formatTimeOfDay } from "@/lib/format";

/**
 * Structural children of a node: ANSWERs render inside their question row,
 * and the extractor's catch-all ("Other") is hidden while it stayed empty so
 * it doesn't read as an unanswered agenda item.
 */
function visibleChildren(sections: Section[], id: string): Section[] {
  return childrenOf(sections, id).filter((c) => {
    if (c.kind === "answer") return false;
    if (
      (c.id === OTHER_SECTION_ID || c.id === OTHER_QUESTION_ID) &&
      answersUnder(sections, c.id).length === 0
    )
      return false;
    return true;
  });
}

function ResultRow({
  section,
  sections,
  collapsedIds,
  onToggle,
}: {
  section: Section;
  sections: Section[];
  collapsedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const children = visibleChildren(sections, section.id);
  const answers =
    section.kind === "question"
      ? childrenOf(sections, section.id).filter((c) => c.kind === "answer")
      : [];
  const expanded = !collapsedIds.has(section.id);

  return (
    <div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onToggle(section.id)}
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse" : "Expand"}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>
        <span
          className={
            section.kind === "topic" ? "text-sm font-medium" : "text-sm"
          }
        >
          {section.header}
        </span>
      </div>

      {expanded && (
        <div className="ml-7 mt-1 space-y-2">
          {section.body && (
            <p className="text-sm text-muted-foreground">{section.body}</p>
          )}
          {section.kind === "question" &&
            (answers.length > 0 ? (
              <div className="space-y-2">
                {answers.map((a) => (
                  <div key={a.id}>
                    <p className="text-sm">{a.header}</p>
                    {a.body && (
                      <p className="text-sm text-muted-foreground">{a.body}</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No answer recorded
              </p>
            ))}
          {children.length > 0 && (
            <div className="space-y-2 border-l border-border pl-4">
              {children.map((c) => (
                <ResultRow
                  key={c.id}
                  section={c}
                  sections={sections}
                  collapsedIds={collapsedIds}
                  onToggle={onToggle}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultsTree({ sections }: { sections: Section[] | null }) {
  // Inverted vs TemplateEditor: the page exists to read answers, so the tree
  // starts fully expanded and we track the *collapsed* ids.
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(
    () => new Set(),
  );

  const toggle = (id: string) =>
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const topLevel = sections ? visibleChildren(sections, ROOT_SECTION_ID) : [];

  return (
    <section>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Results</h2>
        {topLevel.length > 0 && (
          <div className="flex items-center gap-2">
            <IconButton
              size="sm"
              variant="outline"
              onClick={() => setCollapsedIds(new Set())}
              label="Expand all"
            >
              <ChevronsUpDown />
            </IconButton>
            <IconButton
              size="sm"
              variant="outline"
              onClick={() =>
                setCollapsedIds(
                  new Set(
                    (sections ?? [])
                      .filter((s) => s.kind !== "answer")
                      .map((s) => s.id),
                  ),
                )
              }
              label="Collapse all"
            >
              <ChevronsDownUp />
            </IconButton>
          </div>
        )}
      </div>
      {topLevel.length > 0 ? (
        <div className="mt-3 space-y-2">
          {topLevel.map((c) => (
            <ResultRow
              key={c.id}
              section={c}
              sections={sections!}
              collapsedIds={collapsedIds}
              onToggle={toggle}
            />
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          No results were recorded for this meeting.
        </p>
      )}
    </section>
  );
}

function Transcript({ transcript }: { transcript: TranscriptLine[] | null }) {
  return (
    <section>
      <h2 className="text-lg font-semibold tracking-tight">Transcript</h2>
      {transcript && transcript.length > 0 ? (
        <div className="mt-3 max-h-[32rem] space-y-3 overflow-y-auto pr-2">
          {transcript.map((line, i) => (
            <div key={i} className="flex gap-3">
              <div className="w-24 shrink-0">
                <p className="text-xs font-medium">
                  {line.role === "assistant" ? "Agent" : "Participant"}
                </p>
                <p className="text-xs tabular-nums text-muted-foreground">
                  {formatTimeOfDay(line.ts)}
                </p>
              </div>
              <p className="text-sm">{line.text}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          No transcript was recorded for this meeting.
        </p>
      )}
    </section>
  );
}

/** The finished-meeting panels: agenda tree with answers, then transcript. */
export function MeetingResultsPanels({ results }: { results: MeetingResults }) {
  return (
    <div className="space-y-8">
      <ResultsTree sections={results.sections} />
      <Transcript transcript={results.transcript} />
    </div>
  );
}
