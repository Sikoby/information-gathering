/**
 * Meeting template types — shared by the meeting viewer (frontend) and the
 * meeting console (console-frontend).
 *
 * Keep in sync with the Pydantic models in src/templates/schema.py.
 */

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
