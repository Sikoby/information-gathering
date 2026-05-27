import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Badge, Button, Input, Textarea } from "@ig/ui";
import {
  CLOSING_SECTION_ID,
  OTHER_QUESTION_ID,
  OTHER_SECTION_ID,
  ROOT_SECTION_ID,
  childrenOf,
  isScheduled,
  scheduledNodes,
} from "@/types";
import type { Section, SectionKind, Template } from "@/types";
import { slugify } from "@/lib/format";

const PROTECTED_IDS = new Set([
  ROOT_SECTION_ID,
  OTHER_SECTION_ID,
  OTHER_QUESTION_ID,
  CLOSING_SECTION_ID,
]);

const KIND_LABELS: Record<SectionKind, string> = {
  meeting: "Meeting",
  topic: "Topic",
  question: "Question",
  answer: "Answer (runtime)",
};

function allowedChildKinds(parentKind: SectionKind): SectionKind[] {
  switch (parentKind) {
    case "meeting":
      return ["topic"];
    case "topic":
      return ["topic", "question"];
    case "question":
      return []; // ANSWERs are runtime only
    case "answer":
      return [];
  }
}

function fractionSum(sections: Section[]): number {
  return scheduledNodes(sections).reduce(
    (s, n) => s + (n.target_fraction ?? 0),
    0,
  );
}

function nextId(parent: Section, kind: SectionKind, sections: Section[]): string {
  const prefix = kind === "topic" ? "t" : kind === "question" ? "q" : "x";
  const siblings = childrenOf(sections, parent.id);
  let n = siblings.length + 1;
  let candidate = `${parent.id}/${prefix}${n}`;
  while (sections.some((s) => s.id === candidate)) {
    n += 1;
    candidate = `${parent.id}/${prefix}${n}`;
  }
  return candidate;
}

function replaceSection(
  sections: Section[],
  id: string,
  patch: Partial<Section>,
): Section[] {
  return sections.map((s) => (s.id === id ? { ...s, ...patch } : s));
}

function removeSubtree(sections: Section[], id: string): Section[] {
  const toDrop = new Set<string>([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const s of sections) {
      if (s.parent_id && toDrop.has(s.parent_id) && !toDrop.has(s.id)) {
        toDrop.add(s.id);
        changed = true;
      }
    }
  }
  return sections.filter((s) => !toDrop.has(s.id));
}

function SectionRow({
  section,
  sections,
  depth,
  onChange,
  disabled,
}: {
  section: Section;
  sections: Section[];
  depth: number;
  onChange: (next: Section[]) => void;
  disabled: boolean;
}) {
  const isProtected = PROTECTED_IDS.has(section.id);
  const isTopLevel = section.parent_id === ROOT_SECTION_ID;
  const isRoot = section.id === ROOT_SECTION_ID;
  const allowedKinds = section.parent_id
    ? allowedChildKinds(
        sections.find((s) => s.id === section.parent_id)?.kind ?? "meeting",
      )
    : ["meeting" as SectionKind];
  const childKinds = allowedChildKinds(section.kind);
  const children = childrenOf(sections, section.id).filter(
    (c) => c.kind !== "answer",
  );
  const hasChildren = children.length > 0;

  // Root + scheduled top-level topics start expanded; deeper nodes collapsed
  // by default so a big template opens to a quick scan, not a wall of text.
  const [expanded, setExpanded] = useState<boolean>(
    isRoot || (isTopLevel && isScheduled(section)) || !hasChildren,
  );

  const setField = (patch: Partial<Section>) =>
    onChange(replaceSection(sections, section.id, patch));

  const addChild = (kind: SectionKind) => {
    const id = nextId(section, kind, sections);
    const next: Section = {
      id,
      parent_id: section.id,
      kind,
      header: kind === "question" ? "New question?" : "New topic",
      body: null,
      private_notes: null,
      target_fraction: null,
      opening_signpost: null,
      closing_signpost: null,
      ts: null,
    };
    onChange([...sections, next]);
    setExpanded(true);
  };

  const remove = () => {
    if (isProtected) return;
    onChange(removeSubtree(sections, section.id));
  };

  return (
    <div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
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
        <Input
          value={section.header}
          disabled={disabled}
          placeholder="Header"
          onChange={(e) => setField({ header: e.target.value })}
          className="h-7 flex-1 border-0 px-1 text-sm font-medium shadow-none focus-visible:bg-secondary/40"
        />
        {isTopLevel && isScheduled(section) && (
          <span className="text-xs text-muted-foreground">scheduled</span>
        )}
        {!isProtected && !disabled && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={remove}
            title="Remove this section and its children"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        )}
      </div>

      {expanded && (
        <div className="ml-7 mt-2 space-y-2">
          {section.kind !== "meeting" && !isProtected && allowedKinds.length > 1 && (
            <div>
              <label className="text-xs text-muted-foreground">Kind</label>
              <div className="mt-1 flex gap-1">
                {allowedKinds.map((k) => (
                  <Button
                    key={k}
                    type="button"
                    size="sm"
                    variant={k === section.kind ? "default" : "outline"}
                    disabled={disabled}
                    onClick={() => setField({ kind: k })}
                  >
                    {KIND_LABELS[k]}
                  </Button>
                ))}
              </div>
            </div>
          )}
          <Textarea
            rows={2}
            value={section.body ?? ""}
            disabled={disabled}
            placeholder={
              section.kind === "topic"
                ? "What this section covers (optional)"
                : section.kind === "question"
                  ? "Optional context for the question"
                  : "Body"
            }
            onChange={(e) =>
              setField({ body: e.target.value ? e.target.value : null })
            }
          />
          <div>
            <label className="text-xs text-muted-foreground">
              Speaker notes
            </label>
            <Textarea
              className="mt-1"
              rows={2}
              value={section.private_notes ?? ""}
              disabled={disabled}
              placeholder="Speaker notes for the agent — hidden from participants. Tone, things to say or avoid, framing cues."
              onChange={(e) =>
                setField({
                  private_notes: e.target.value ? e.target.value : null,
                })
              }
            />
          </div>
          {isTopLevel && section.kind === "topic" && !isProtected && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-muted-foreground">
                Target fraction (leave blank for un-scheduled)
              </label>
              <Input
                type="number"
                step="0.05"
                min="0"
                max="1"
                className="w-24"
                value={
                  section.target_fraction == null ? "" : section.target_fraction
                }
                disabled={disabled}
                onChange={(e) =>
                  setField({
                    target_fraction:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </div>
          )}

          {childKinds.length > 0 && !disabled && (
            <div className="flex gap-1">
              {childKinds.map((k) => (
                <Button
                  key={k}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => addChild(k)}
                >
                  <Plus className="mr-1 h-3 w-3" />
                  add {k}
                </Button>
              ))}
            </div>
          )}

          {hasChildren && (
            <div className="space-y-2 border-l border-border pl-4">
              {children.map((c) => (
                <SectionRow
                  key={c.id}
                  section={c}
                  sections={sections}
                  depth={depth + 1}
                  onChange={onChange}
                  disabled={disabled}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Controlled editor for a meeting Template (kinded Section tree). */
export function TemplateEditor({
  template,
  onChange,
  disabled = false,
}: {
  template: Template;
  onChange: (t: Template) => void;
  disabled?: boolean;
}) {
  const setSections = (sections: Section[]) =>
    onChange({ ...template, sections });

  const total = fractionSum(template.sections);
  const root = template.sections.find((s) => s.id === ROOT_SECTION_ID);

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
        <div>
          <label className="text-xs text-muted-foreground">Name</label>
          <Input
            className="mt-1"
            value={template.name}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...template, name: slugify(e.target.value) })
            }
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Description</label>
          <Input
            className="mt-1"
            value={template.description}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...template, description: e.target.value })
            }
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">
            Sections ({template.sections.length})
          </h3>
          <Badge
            variant={Math.abs(total - 1) < 0.011 ? "success" : "warning"}
          >
            scheduled fractions {total.toFixed(2)}
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Tree of sections. Top-level TOPICs with a target_fraction are "phases"
          and must sum to ≈ 1.0. QUESTIONs accept ANSWERs at runtime.
        </p>
        <div className="mt-3 space-y-2">
          {root && (
            <SectionRow
              section={root}
              sections={template.sections}
              depth={0}
              onChange={setSections}
              disabled={disabled}
            />
          )}
        </div>
      </div>
    </div>
  );
}
