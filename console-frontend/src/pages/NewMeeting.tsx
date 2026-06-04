import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  CalendarClock,
  CalendarPlus,
  LayoutDashboard,
  Plus,
  Trash2,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Calendar, Input } from "@ig/ui";
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
import { StartButton } from "@/components/StartButton";
import { formatDateTime } from "@/lib/format";
import type { MeetingRecord } from "@/types";

type Mode = "now" | "schedule";

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
  const [title, setTitle] = useState("");
  // null = "follow the template default"; a number once the user edits it.
  const [minutes, setMinutes] = useState<number | null>(null);
  const [scheduledDay, setScheduledDay] = useState<Date | undefined>(undefined);
  const [scheduledTime, setScheduledTime] = useState("09:00");
  // One email per row; starts with a single empty row.
  const [invitees, setInvitees] = useState<string[]>([""]);
  // which action is in flight (so only that section's button spins), or null.
  const [busy, setBusy] = useState<Mode | null>(null);
  const [error, setError] = useState<{ mode: Mode; message: string } | null>(null);
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

  const updateInvitee = (i: number, value: string) =>
    setInvitees((prev) => prev.map((e, idx) => (idx === i ? value : e)));
  const addInvitee = () => setInvitees((prev) => [...prev, ""]);
  const removeInvitee = (i: number) =>
    setInvitees((prev) =>
      prev.length === 1 ? [""] : prev.filter((_, idx) => idx !== i),
    );

  const onStartNow = async () => {
    if (!selected) return;
    setBusy("now");
    setError(null);
    try {
      const meeting = await startMeetingFromTemplate(selected.template_id, {
        title_override: title.trim() || undefined,
        target_minutes: targetOverride,
      });
      setResult(meeting);
    } catch (e) {
      setError({ mode: "now", message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const onSchedule = async () => {
    if (!selected || !scheduledDay) return;
    setBusy("schedule");
    setError(null);
    try {
      const meeting = await scheduleMeetingFromTemplate(selected.template_id, {
        scheduled_at: combineDayTime(scheduledDay, scheduledTime).toISOString(),
        title_override: title.trim() || undefined,
        target_minutes: targetOverride,
        invitees: invitees.map((e) => e.trim()).filter(Boolean),
      });
      setResult(meeting);
    } catch (e) {
      setError({ mode: "schedule", message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
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

              <section className="space-y-4 border-t pt-6">
                <h2 className="text-sm font-semibold text-muted-foreground">
                  Start now
                </h2>

                {error?.mode === "now" && (
                  <Alert variant="destructive">
                    <AlertTitle>Couldn't start the meeting</AlertTitle>
                    <AlertDescription>{error.message}</AlertDescription>
                  </Alert>
                )}

                <StartButton
                  onClick={onStartNow}
                  disabled={busy !== null || !selected}
                  busy={busy === "now"}
                />
              </section>

              <section className="space-y-4 border-t pt-6">
                <h2 className="text-sm font-semibold text-muted-foreground">
                  Schedule for later
                </h2>

                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Date and time</h3>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                    <Calendar
                      mode="single"
                      selected={scheduledDay}
                      onSelect={setScheduledDay}
                      disabled={{ before: today }}
                      className="rounded-md border p-3"
                    />
                    <div className="space-y-1.5">
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
                </div>

                <Field
                  label="Attendees"
                  info="Each attendee gets a calendar invite (.ics) you download and send."
                >
                  <div className="mt-1 space-y-2">
                    {invitees.map((email, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Input
                          type="email"
                          value={email}
                          onChange={(e) => updateInvitee(i, e.target.value)}
                          placeholder="alice@example.com"
                        />
                        <IconButton
                          variant="ghost"
                          size="sm"
                          className="shrink-0 text-destructive"
                          label="Remove attendee"
                          onClick={() => removeInvitee(i)}
                        >
                          <Trash2 />
                        </IconButton>
                      </div>
                    ))}
                    <IconButton
                      size="sm"
                      label="Add attendee"
                      onClick={addInvitee}
                    >
                      <Plus />
                    </IconButton>
                  </div>
                </Field>

                {error?.mode === "schedule" && (
                  <Alert variant="destructive">
                    <AlertTitle>Couldn't schedule the meeting</AlertTitle>
                    <AlertDescription>{error.message}</AlertDescription>
                  </Alert>
                )}

                <IconButton
                  onClick={onSchedule}
                  disabled={busy !== null || !selected || !scheduledDay}
                  label={busy === "schedule" ? "Scheduling…" : "Schedule meeting"}
                >
                  <CalendarClock />
                </IconButton>
              </section>
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
