import type { Template } from "@ig/ui";

// Template + Section types come from the shared library. Re-exported for
// local imports.
export type { Section, SectionKind, Template } from "@ig/ui";
export {
  ROOT_SECTION_ID,
  OTHER_SECTION_ID,
  OTHER_QUESTION_ID,
  CLOSING_SECTION_ID,
  sectionById,
  childrenOf,
  isScheduled,
  scheduledNodes,
} from "@ig/ui";

export type MeetingStatus = "scheduled" | "running" | "done";
export type TemplateStatus = "generating" | "ready" | "failed";

export type DocumentKind = "pptx" | "pdf";

export type SlideOutline = {
  index: number;
  title: string | null;
  content: string;
  speaker_notes: string | null;
};

export type DocumentOutline = {
  source_name: string;
  kind: DocumentKind;
  slides: SlideOutline[];
};

/** Mirrors src/console/models.py TemplateRecord. Keep in sync. */
export type TemplateRecord = {
  template_id: string;
  owner_email: string;
  title: string;
  source_prompt: string;
  reference_template: string | null;
  default_target_minutes: number;
  template_status: TemplateStatus;
  template: Template | null;
  template_error: string | null;
  template_approved: boolean | null;
  template_iterations_used: number | null;
  generation_seq: number;
  document_filename: string | null;
  document_kind: DocumentKind | null;
  document_outline: DocumentOutline | null;
  created_at: string;
  updated_at: string;
};

/** Mirrors src/console/models.py MeetingRecord. Keep in sync. */
export type MeetingRecord = {
  meeting_id: string;
  owner_email: string;
  template_id: string;
  title_override: string | null;
  target_minutes: number;
  status: MeetingStatus;
  scheduled_at: string | null;
  invitees: string[];
  invite_sent_at: string | null;
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
