import type {
  BatchScheduleResult,
  BatchStartResult,
  Interviewee,
  MeetingRecord,
  ReferenceTemplate,
  Template,
  TemplateRecord,
} from "@/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Parsed JSON error body when the response had one. */
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function apiErrorFrom(status: number, statusText: string, text: string): ApiError {
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined;
  }
  const message =
    body &&
    typeof body === "object" &&
    typeof (body as { error?: unknown }).error === "string"
      ? (body as { error: string }).error
      : text || `${status} ${statusText}`;
  return new ApiError(status, message, body);
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw apiErrorFrom(res.status, res.statusText, text);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// -------------------------------------------------------------------- me

export function getMe(): Promise<{ email: string; logout_url: string | null }> {
  return req("/api/me");
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
    throw apiErrorFrom(res.status, res.statusText, text);
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

export function scheduleMeetingFromTemplate(
  id: string,
  body: {
    scheduled_at: string;
    title_override?: string;
    target_minutes?: number;
    invitees?: string[];
  },
): Promise<MeetingRecord> {
  return req(`/api/templates/${id}/scheduled-meetings`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function startBatchFromTemplate(
  id: string,
  body: {
    target_minutes?: number;
    title_prefix?: string;
    interviewees: Interviewee[];
  },
): Promise<BatchStartResult> {
  return req(`/api/templates/${id}/batch-meetings`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function scheduleBatchFromTemplate(
  id: string,
  body: {
    scheduled_at: string;
    target_minutes?: number;
    title_prefix?: string;
    interviewees: Interviewee[];
  },
): Promise<BatchScheduleResult> {
  return req(`/api/templates/${id}/scheduled-batch-meetings`, {
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

/** Same-origin URL of the downloadable `.ics` invite for a scheduled meeting. */
export function meetingInviteIcsUrl(id: string): string {
  return `/api/meetings/${id}/invite.ics`;
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
