import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  CalendarClock,
  CalendarPlus,
  LayoutDashboard,
  Play,
  X,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Calendar, Input, Textarea } from "@ig/ui";
import { useTemplates } from "@/hooks/useTemplates";
import {
  meetingInviteIcsUrl,
  scheduleMeetingFromTemplate,
  startMeetingFromTemplate,
} from "@/lib/api";
import { CopyButton } from "@/components/CopyButton";
import { Field } from "@/components/Field";
import { LinkField } from "@/components/LinkField";
import { InviteesList } from "@/components/InviteesList";
import { Page, PageHeader } from "@/components/Page";
import { IconButton } from "@/components/IconButton";
import { formatDateTime } from "@/lib/format";
import type { MeetingRecord } from "@/types";

type Mode = "now" | "schedule";

/** Emails separated by commas, semicolons, or whitespace → trimmed list. */
function parseInvitees(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Merge a picked calendar day with an `HH:mm` time string into one Date. */
function combineDayTime(day: Date, time: string): Date {
  const [h, m] = time.split(":").map(Number);
  const d = new Date(day);
  d.setHours(Number.isFinite(h) ? h : 0, Number.isFinite(m) ? m : 0, 0, 0);
  return d;
}

export function NewMeeting() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const preselect = params.get("template");
  const { templates, loaded } = useTemplates();

  const ready = useMemo(
    () => templates.filter((t) => t.template_status === "ready"),
    [templates],
  );

  const [templateId, setTemplateId] = useState("");
  const [mode, setMode] = useState<Mode>("now");
  const [title, setTitle] = useState("");
  // null = "follow the template default"; a number once the user edits it.
  const [minutes, setMinutes] = useState<number | null>(null);
  const [scheduledDay, setScheduledDay] = useState<Date | undefined>(undefined);
  const [scheduledTime, setScheduledTime] = useState("09:00");
  const [invitees, setInvitees] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MeetingRecord | null>(null);

  // Floor the calendar at today so past days can't be picked; the backend
  // re-checks the full instant against its own clock.
  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  // Pick an initial template once the list loads (the ?template= deep link, or
  // the newest ready one). Runs once — guarded on templateId being empty.
  useEffect(() => {
    if (templateId || ready.length === 0) return;
    const fromParam = preselect
      ? ready.find((t) => t.template_id === preselect)
      : undefined;
    setTemplateId((fromParam ?? ready[0]).template_id);
  }, [ready, preselect, templateId]);

  const selected = ready.find((t) => t.template_id === templateId) ?? null;
  const defaultMinutes = selected?.default_target_minutes ?? 30;
  const effectiveMinutes = minutes ?? defaultMinutes;

  const targetOverride =
    effectiveMinutes !== defaultMinutes ? effectiveMinutes : undefined;

  const onStartNow = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const meeting = await startMeetingFromTemplate(selected.template_id, {
        title_override: title.trim() || undefined,
        target_minutes: targetOverride,
      });
      setResult(meeting);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSchedule = async () => {
    if (!selected || !scheduledDay) return;
    setBusy(true);
    setError(null);
    try {
      const meeting = await scheduleMeetingFromTemplate(selected.template_id, {
        scheduled_at: combineDayTime(scheduledDay, scheduledTime).toISOString(),
        title_override: title.trim() || undefined,
        target_minutes: targetOverride,
        invitees: parseInvitees(invitees),
      });
      setResult(meeting);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader back title="New meeting" />

      <div className="max-w-2xl">
        {loaded && ready.length === 0 && (
          <Alert>
            <AlertTitle>No templates ready yet</AlertTitle>
            <AlertDescription>
              A meeting runs from a template.{" "}
              <Link to="/templates/new" className="underline">
                Create a template
              </Link>{" "}
              first, then come back here.
            </AlertDescription>
          </Alert>
        )}

        {result ? (
          <ResultPanel
            meeting={result}
            onGo={() => navigate(`/meetings/${result.meeting_id}`)}
          />
        ) : (
          ready.length > 0 && (
            <div className="space-y-6">
              <Field label="Template">
                <select
                  className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                >
                  {ready.map((t) => (
                    <option key={t.template_id} value={t.template_id}>
                      {t.title}
                    </option>
                  ))}
                </select>
              </Field>

              <div className="inline-flex gap-0.5 rounded-md border p-0.5">
                <IconButton
                  variant={mode === "now" ? "default" : "ghost"}
                  onClick={() => setMode("now")}
                  label="Start now"
                >
                  <Play />
                </IconButton>
                <IconButton
                  variant={mode === "schedule" ? "default" : "ghost"}
                  onClick={() => setMode("schedule")}
                  label="Schedule"
                >
                  <CalendarClock />
                </IconButton>
              </div>

              <Field label="Title" hint="Defaults to the template title.">
                <Input
                  className="mt-1"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={selected?.title ?? ""}
                  maxLength={200}
                />
              </Field>

              <Field label="Duration (min)">
                <Input
                  className="mt-1 w-36"
                  type="number"
                  min={1}
                  max={120}
                  value={effectiveMinutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                />
              </Field>

              {mode === "schedule" && (
                <>
                  <Field label="Start time">
                    <div className="mt-1 flex flex-col gap-4 sm:flex-row sm:items-start">
                      <Calendar
                        mode="single"
                        selected={scheduledDay}
                        onSelect={setScheduledDay}
                        disabled={{ before: today }}
                        className="rounded-md border p-3"
                      />
                      <div className="space-y-1.5">
                        <label className="text-sm font-medium">Time</label>
                        <Input
                          type="time"
                          className="w-36"
                          value={scheduledTime}
                          onChange={(e) => setScheduledTime(e.target.value)}
                        />
                        {scheduledDay && (
                          <p className="text-sm text-muted-foreground">
                            Starts{" "}
                            {formatDateTime(
                              combineDayTime(
                                scheduledDay,
                                scheduledTime,
                              ).toISOString(),
                            )}
                          </p>
                        )}
                      </div>
                    </div>
                  </Field>

                  <Field
                    label="Invitees"
                    hint="Emails separated by commas or new lines. Each gets a calendar invite (.ics) you download and send."
                  >
                    <Textarea
                      className="mt-1"
                      rows={3}
                      value={invitees}
                      onChange={(e) => setInvitees(e.target.value)}
                      placeholder="alice@example.com, bob@example.com"
                    />
                  </Field>
                </>
              )}

              {error && (
                <Alert variant="destructive">
                  <AlertTitle>
                    {mode === "now"
                      ? "Couldn't start the meeting"
                      : "Couldn't schedule the meeting"}
                  </AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <div className="flex items-center gap-2 border-t pt-4">
                {mode === "now" ? (
                  <IconButton
                    onClick={onStartNow}
                    disabled={busy || !selected}
                    label={busy ? "Starting…" : "Start"}
                  >
                    <Play />
                  </IconButton>
                ) : (
                  <IconButton
                    onClick={onSchedule}
                    disabled={busy || !selected || !scheduledDay}
                    label={busy ? "Scheduling…" : "Schedule meeting"}
                  >
                    <CalendarClock />
                  </IconButton>
                )}
                <IconButton variant="ghost" asChild label="Cancel">
                  <Link to="/">
                    <X />
                  </Link>
                </IconButton>
              </div>
            </div>
          )
        )}
      </div>
    </Page>
  );
}

function ResultPanel({
  meeting,
  onGo,
}: {
  meeting: MeetingRecord;
  onGo: () => void;
}) {
  return meeting.status === "scheduled" ? (
    <ScheduledPanel meeting={meeting} onGo={onGo} />
  ) : (
    <StartedPanel meeting={meeting} onGo={onGo} />
  );
}

/** Go-to-meeting + back-to-dashboard, shared by both result panels. */
function ResultActions({ onGo }: { onGo: () => void }) {
  return (
    <div className="flex items-center gap-2 border-t pt-4">
      <IconButton onClick={onGo} label="Go to meeting">
        <ArrowRight />
      </IconButton>
      <IconButton variant="ghost" asChild label="Back to dashboard">
        <Link to="/">
          <LayoutDashboard />
        </Link>
      </IconButton>
    </div>
  );
}

function ScheduledPanel({
  meeting,
  onGo,
}: {
  meeting: MeetingRecord;
  onGo: () => void;
}) {
  return (
    <div className="space-y-6">
      <Alert variant="success">
        <AlertTitle>Meeting scheduled</AlertTitle>
        <AlertDescription>
          {meeting.scheduled_at
            ? `Starts ${formatDateTime(meeting.scheduled_at)}. `
            : ""}
          It starts automatically at that time — no need to come back.
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap items-center gap-2">
        <IconButton asChild label="Add to calendar (.ics)">
          <a href={meetingInviteIcsUrl(meeting.meeting_id)} download>
            <CalendarPlus />
          </a>
        </IconButton>
        {meeting.webapp_url && (
          <CopyButton value={meeting.webapp_url} label="Copy live link" />
        )}
      </div>

      {meeting.webapp_url && (
        <LinkField
          label="Live view"
          hint="Read-only. The voice-join link appears once the meeting starts."
          url={meeting.webapp_url}
        />
      )}

      <InviteesList emails={meeting.invitees} />

      <ResultActions onGo={onGo} />
    </div>
  );
}

function StartedPanel({
  meeting,
  onGo,
}: {
  meeting: MeetingRecord;
  onGo: () => void;
}) {
  return (
    <div className="space-y-6">
      <Alert variant="success">
        <AlertTitle>Meeting started</AlertTitle>
        <AlertDescription>
          Share a link below, or open the meeting to follow along.
        </AlertDescription>
      </Alert>

      {meeting.join_url && (
        <LinkField label="Join link" hint="Send this to participants." url={meeting.join_url} />
      )}
      {meeting.webapp_url && (
        <LinkField label="Live view" hint="Read-only — watch the meeting unfold." url={meeting.webapp_url} />
      )}

      <ResultActions onGo={onGo} />
    </div>
  );
}
