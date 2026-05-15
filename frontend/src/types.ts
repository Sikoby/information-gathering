export type ObjectiveStatus = {
  status: "open" | "partial" | "covered";
  note: string;
};

export type Objective = {
  id: string;
  objective: string;
  success_criteria: string;
};

export type NotebookEntry = {
  title: string;
  content: string;
  objective_ids: string[];
  ts: string;
};

export type Followup = {
  item: string;
  kind: "action" | "open_question";
  ts: string;
};

export type PhaseTransition = {
  phase_id: string;
  note: string;
  ts: string;
};

export type NotebookSection = {
  id: string;
  label: string;
  description: string;
  repeated: boolean;
};

export type Phase = {
  id: string;
  label: string;
  goal: string;
  target_fraction: number;
  sections_in_focus: string[];
};

export type Template = {
  name: string;
  description: string;
  sections: NotebookSection[];
  phases: Phase[];
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
  objectives: Objective[];
  tracker: Record<string, ObjectiveStatus>;
  template: Template;
  notebook: Record<string, NotebookEntry[]>;
  current_phase: string;
  phase_history: PhaseTransition[];
  followups: Followup[];
  user_turn_count: number;
  end_reason: EndReason;
  ended_at: string | null;
};
