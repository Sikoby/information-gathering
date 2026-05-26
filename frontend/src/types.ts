// Template + tree types live in the shared library (consumed by both the
// viewer and the console). Re-exported so existing `@/types` imports work.
import type { Section, SectionKind, Template } from "@ig/ui";
export type { Section, SectionKind, Template };
export {
  ROOT_SECTION_ID,
  OTHER_SECTION_ID,
  OTHER_QUESTION_ID,
  CLOSING_SECTION_ID,
  sectionById,
  childrenOf,
  childrenOfKind,
  descendantsOf,
  answersUnder,
  pathTo,
  depthOf,
  isScheduled,
  scheduledNodes,
  enclosingPhase,
} from "@ig/ui";

export type Followup = {
  item: string;
  kind: "action" | "open_question";
  ts: string;
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
