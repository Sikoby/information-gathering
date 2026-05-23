export type SectionKind =
  | "meeting"
  | "phase"
  | "topic"
  | "question"
  | "answer"
  | "closing";

export type Section = {
  id: string;
  parent_id: string | null;
  kind: SectionKind;
  header: string;
  body: string | null;
  repeated: boolean;
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

export type TransitionKind =
  | "sibling"
  | "drill_down"
  | "zoom_out"
  | "revisit"
  | "open";

export type Transition = {
  from_section_id: string | null;
  to_section_id: string;
  kind: TransitionKind;
  crossed_phase_boundary: boolean;
  recap: string | null;
  bridge: string | null;
  preview: string | null;
  ts: string;
};

export type Followup = {
  item: string;
  kind: "action" | "open_question";
  ts: string;
};

export type EndReason =
  | "objectives_met"
  | "time_up"
  | "user_ended"
  | "blocked"
  | null;

export type MeetingState = {
  run_id: string;
  briefing_path: string;
  target_minutes: number;
  started_at: string;
  briefing_markdown: string;
  template: Template;
  sections: Section[];
  current_section_id: string;
  visited_section_ids: string[];
  transitions: Transition[];
  followups: Followup[];
  user_turn_count: number;
  end_reason: EndReason;
  ended_at: string | null;
};

export const ROOT_SECTION_ID = "_root";

// Tree helpers operating on a flat section list.

export function sectionById(sections: Section[], id: string): Section | undefined {
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
  return childrenOf(sections, id).filter((s) => s.kind === kind);
}

export function descendantsOf(sections: Section[], id: string): Section[] {
  const out: Section[] = [];
  const stack = [id];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const child of childrenOf(sections, cur)) {
      out.push(child);
      stack.push(child.id);
    }
  }
  return out;
}

export function answersUnder(sections: Section[], id: string): Section[] {
  return descendantsOf(sections, id).filter((s) => s.kind === "answer");
}

export function pathTo(sections: Section[], id: string): Section[] {
  const byId = new Map(sections.map((s) => [s.id, s]));
  const target = byId.get(id);
  if (!target) return [];
  const chain: Section[] = [];
  let cur: Section | undefined = target;
  while (cur) {
    chain.push(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return chain.reverse();
}

export function scheduledNodes(sections: Section[]): Section[] {
  return sections.filter((s) => s.kind === "phase");
}

export function enclosingPhase(
  sections: Section[],
  id: string,
): Section | undefined {
  const chain = pathTo(sections, id);
  for (let i = chain.length - 1; i >= 0; i--) {
    if (chain[i].kind === "phase") return chain[i];
  }
  return undefined;
}
