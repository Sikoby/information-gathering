import type { Template } from "@ig/ui";

// Template types come from the shared library. Re-exported for local imports.
export type { NotebookSection, Phase, Template } from "@ig/ui";

export type MeetingStatus = "planned" | "running" | "done";
export type TemplateStatus = "generating" | "ready" | "failed";

/** Mirrors src/console/models.py MeetingRecord. Keep in sync. */
export type MeetingRecord = {
  meeting_id: string;
  title: string;
  prompt: string;
  reference_template: string | null;
  target_minutes: number;
  status: MeetingStatus;
  template_status: TemplateStatus;
  template: Template | null;
  template_error: string | null;
  template_approved: boolean | null;
  template_iterations_used: number | null;
  generation_seq: number;
  run_id: string | null;
  room: string | null;
  join_url: string | null;
  webapp_url: string | null;
  created_at: string;
  updated_at: string;
  dispatched_at: string | null;
  ended_at: string | null;
  end_reason: string | null;
};

export type ReferenceTemplate = {
  name: string;
  description: string;
};
