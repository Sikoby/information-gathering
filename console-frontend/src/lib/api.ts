import type { MeetingRecord, ReferenceTemplate, Template } from "@/types";

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

export function listMeetings(): Promise<{ meetings: MeetingRecord[] }> {
  return req("/api/meetings");
}

export function getMeeting(id: string): Promise<MeetingRecord> {
  return req(`/api/meetings/${id}`);
}

export function createMeeting(body: {
  title: string;
  prompt: string;
  reference_template: string | null;
  target_minutes: number;
}): Promise<MeetingRecord> {
  return req("/api/meetings", { method: "POST", body: JSON.stringify(body) });
}

export function patchMeeting(
  id: string,
  body: Partial<{
    title: string;
    prompt: string;
    template: Template;
    target_minutes: number;
  }>,
): Promise<MeetingRecord> {
  return req(`/api/meetings/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function startMeeting(id: string): Promise<MeetingRecord> {
  return req(`/api/meetings/${id}/start`, { method: "POST", body: "{}" });
}

export function regenerateMeeting(
  id: string,
  body: { prompt?: string; reference_template?: string } = {},
): Promise<MeetingRecord> {
  return req(`/api/meetings/${id}/regenerate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteMeeting(id: string): Promise<void> {
  return req(`/api/meetings/${id}`, { method: "DELETE" });
}

export function listReferenceTemplates(): Promise<{
  templates: ReferenceTemplate[];
}> {
  return req("/api/reference-templates");
}
