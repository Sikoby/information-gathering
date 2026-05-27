import type {
  MeetingRecord,
  ReferenceTemplate,
  Template,
  TemplateRecord,
} from "@/types";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --------------------------------------------------------------- templates

export function listTemplates(): Promise<{ templates: TemplateRecord[] }> {
  return req("/api/templates");
}

export function getTemplate(id: string): Promise<TemplateRecord> {
  return req(`/api/templates/${id}`);
}

export function createTemplate(body: {
  title: string;
  source_prompt: string;
  reference_template: string | null;
  default_target_minutes: number;
}): Promise<TemplateRecord> {
  return req("/api/templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createTemplateFromDocument(
  body: {
    title: string;
    source_prompt: string;
    reference_template: string | null;
    default_target_minutes: number;
  },
  file: File,
): Promise<TemplateRecord> {
  const form = new FormData();
  form.append("title", body.title);
  form.append("source_prompt", body.source_prompt);
  if (body.reference_template)
    form.append("reference_template", body.reference_template);
  form.append("default_target_minutes", String(body.default_target_minutes));
  form.append("file", file, file.name);

  const res = await fetch("/api/templates/upload", {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as TemplateRecord;
}

export function patchTemplate(
  id: string,
  body: Partial<{
    title: string;
    source_prompt: string;
    template: Template;
    default_target_minutes: number;
  }>,
): Promise<TemplateRecord> {
  return req(`/api/templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function regenerateTemplate(
  id: string,
  body: { source_prompt?: string; reference_template?: string } = {},
): Promise<TemplateRecord> {
  return req(`/api/templates/${id}/regenerate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteTemplate(id: string): Promise<void> {
  return req(`/api/templates/${id}`, { method: "DELETE" });
}

export function startMeetingFromTemplate(
  id: string,
  body: { title_override?: string; target_minutes?: number } = {},
): Promise<MeetingRecord> {
  return req(`/api/templates/${id}/meetings`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------- meetings

export function listMeetings(): Promise<{ meetings: MeetingRecord[] }> {
  return req("/api/meetings");
}

export function getMeeting(id: string): Promise<MeetingRecord> {
  return req(`/api/meetings/${id}`);
}

export function deleteMeeting(id: string): Promise<void> {
  return req(`/api/meetings/${id}`, { method: "DELETE" });
}

// ----------------------------------------------------------------- shared

export function listReferenceTemplates(): Promise<{
  templates: ReferenceTemplate[];
}> {
  return req("/api/reference-templates");
}
