/**
 * Meeting template types and Section tree — shared by the meeting viewer
 * (frontend) and the meeting console (console-frontend).
 *
 * Keep in sync with the Pydantic models in src/templates/schema.py.
 */

export const ROOT_SECTION_ID = "_root";
export const OTHER_SECTION_ID = "other";
export const OTHER_QUESTION_ID = "other/q";
export const CLOSING_SECTION_ID = "_root/closing";

export type SectionKind = "meeting" | "topic" | "question" | "answer";

export type Section = {
  id: string;
  parent_id: string | null;
  kind: SectionKind;
  header: string;
  body: string | null;
  private_notes: string | null;
  target_fraction: number | null;
  opening_signpost: string | null;
  closing_signpost: string | null;
  ts: string | null;
};

export type Template = {
  name: string;
  description: string;
  sections: Section[];
};

// ---- tree-walk helpers (pure functions over Section[]) ----

export function sectionById(
  sections: Section[],
  id: string,
): Section | undefined {
  return sections.find((s) => s.id === id);
}

export function childrenOf(sections: Section[], id: string): Section[] {
  return sections.filter((s) => s.parent_id === id);
}

export function childrenOfKind(
  sections: Section[],
  id: string,
  kind: SectionKind,
): Section[] {
  return sections.filter((s) => s.parent_id === id && s.kind === kind);
}

export function descendantsOf(sections: Section[], id: string): Section[] {
  const out: Section[] = [];
  const frontier: string[] = [id];
  while (frontier.length) {
    const pid = frontier.pop()!;
    for (const s of sections) {
      if (s.parent_id === pid) {
        out.push(s);
        frontier.push(s.id);
      }
    }
  }
  return out;
}

export function answersUnder(sections: Section[], id: string): Section[] {
  return descendantsOf(sections, id).filter((s) => s.kind === "answer");
}

export function pathTo(sections: Section[], id: string): Section[] {
  const byId = new Map(sections.map((s) => [s.id, s]));
  if (!byId.has(id)) return [];
  const chain: Section[] = [];
  let cur: Section | undefined = byId.get(id);
  while (cur) {
    chain.push(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return chain.reverse();
}

export function depthOf(sections: Section[], id: string): number {
  const p = pathTo(sections, id);
  return p.length ? p.length - 1 : -1;
}

export function isScheduled(section: Section): boolean {
  return section.kind === "topic" && section.target_fraction != null;
}

/** Top-level scheduled TOPICs (the "phases") in declared order. */
export function scheduledNodes(sections: Section[]): Section[] {
  return sections.filter(
    (s) => s.parent_id === ROOT_SECTION_ID && isScheduled(s),
  );
}

/** Walk up to the first scheduled TOPIC. null if none on the path. */
export function enclosingPhase(
  sections: Section[],
  id: string,
): Section | null {
  const chain = pathTo(sections, id);
  for (let i = chain.length - 1; i >= 0; i--) {
    if (isScheduled(chain[i])) return chain[i];
  }
  return null;
}
