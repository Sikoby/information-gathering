import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  CalendarClock,
  CalendarPlus,
  LayoutDashboard,
  ListPlus,
  X,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Calendar, Input } from "@ig/ui";
import { useTemplates } from "@/hooks/useTemplates";
import {
  meetingInviteIcsUrl,
  scheduleBatchFromTemplate,
} from "@/lib/api";
import { CopyButton } from "@/components/CopyButton";
import { Field } from "@/components/Field";
import { Page, PageHeader } from "@/components/Page";
import { IconButton } from "@/components/IconButton";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDateTime } from "@/lib/format";
import type { BatchStartResult, Interviewee, MeetingRecord } from "@/types";

/** An editable interviewee row (name kept as a string for the controlled input). */
type Row = { name: string; email: string };

/** Merge a picked calendar day with an `HH:mm` time string into one Date. */
function combineDayTime(day: Date, time: string): Date {
  const [h, m] = time.split(":").map(Number);
  const d = new Date(day);
  d.setHours(Number.isFinite(h) ? h : 0, Number.isFinite(m) ? m : 0, 0, 0);
  return d;
}

export function NewBatchMeetings() {
  const [params] = useSearchParams();
  const preselect = params.get("template");
  const { templates, loaded } = useTemplates();

  const ready = useMemo(
    () => templates.filter((t) => t.template_status === "ready"),
    [templates],
  );

  const [templateId, setTemplateId] = useState("");
  const [titlePrefix, setTitlePrefix] = useState("");
  // null = "follow the template default"; a number once the user edits it.
  const [minutes, setMinutes] = useState<number | null>(null);
  const [scheduledDay, setScheduledDay] = useState<Date | undefined>(undefined);
  const [scheduledTime, setScheduledTime] = useState("09:00");
  const [rows, setRows] = useState<Row[]>([{ name: "", email: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchStartResult | null>(null);

  // Floor the calendar at today so past days can't be picked; the backend
  // re-checks the full instant against its own clock.
  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

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

  const addRow = () => setRows((rs) => [...rs, { name: "", email: "" }]);
  const removeRow = (i: number) =>
    setRows((rs) => (rs.length === 1 ? rs : rs.filter((_, j) => j !== i)));
  const updateRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  // Drop empty-email rows; blank name → null. Submit needs at least one.
  const interviewees: Interviewee[] = rows
    .filter((r) => r.email.trim())
    .map((r) => ({ name: r.name.trim() || null, email: r.email.trim() }));

  const canSubmit = !!selected && interviewees.length > 0 && !!scheduledDay;

  const onSchedule = async () => {
    if (!selected || !scheduledDay || interviewees.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const res = await scheduleBatchFromTemplate(selected.template_id, {
        scheduled_at: combineDayTime(scheduledDay, scheduledTime).toISOString(),
        title_prefix: titlePrefix.trim() ? titlePrefix : undefined,
        target_minutes: targetOverride,
        interviewees,
      });
      setResult({ meetings: res.meetings, errors: [] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader
        back
        title="Batch create meetings"
        info="Schedule one meeting per interviewee from a single template — each gets their own room at the same start time. Each runs automatically when its time arrives."
      />

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
          <BatchResultPanel
            result={result}
            fallbackTitle={selected?.title ?? "Meeting"}
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

              <Field
                label="Title prefix"
                hint="Prepended to each interviewee's name (include a trailing space or separator). Blank uses just the name, or the template title."
              >
                <Input
                  className="mt-1"
                  value={titlePrefix}
                  onChange={(e) => setTitlePrefix(e.target.value)}
                  placeholder="Interview — "
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
                  Schedule
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
                  label="Interviewees"
                  hint="Each person gets their own meeting room. Name is optional; email is required."
                >
                  <div className="mt-2 space-y-2 border-l pl-4">
                    {rows.map((row, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Input
                          value={row.name}
                          onChange={(e) => updateRow(i, { name: e.target.value })}
                          placeholder="Name (optional)"
                          maxLength={200}
                        />
                        <Input
                          type="email"
                          value={row.email}
                          onChange={(e) =>
                            updateRow(i, { email: e.target.value })
                          }
                          placeholder="email@example.com"
                        />
                        <IconButton
                          variant="ghost"
                          size="sm"
                          onClick={() => removeRow(i)}
                          disabled={rows.length === 1}
                          label="Remove person"
                        >
                          <X />
                        </IconButton>
                      </div>
                    ))}
                    <IconButton
                      variant="ghost"
                      size="sm"
                      onClick={addRow}
                      label="Add person"
                    >
                      <ListPlus />
                    </IconButton>
                  </div>
                </Field>

                {error && (
                  <Alert variant="destructive">
                    <AlertTitle>Couldn't schedule the meetings</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <div className="flex items-center gap-2 border-t pt-4">
                  <IconButton
                    onClick={onSchedule}
                    disabled={busy || !canSubmit}
                    label={busy ? "Scheduling…" : "Schedule meetings"}
                  >
                    <CalendarClock />
                  </IconButton>
                  <IconButton variant="ghost" asChild label="Cancel">
                    <Link to="/">
                      <X />
                    </Link>
                  </IconButton>
                </div>
              </section>
            </div>
          )
        )}
      </div>
    </Page>
  );
}

function BatchResultPanel({
  result,
  fallbackTitle,
}: {
  result: BatchStartResult;
  fallbackTitle: string;
}) {
  const { meetings, errors } = result;
  const scheduled = meetings.some((m) => m.status === "scheduled");
  return (
    <div className="space-y-6">
      <Alert variant="success">
        <AlertTitle>
          {meetings.length} meeting{meetings.length === 1 ? "" : "s"}{" "}
          {scheduled ? "scheduled" : "started"}
        </AlertTitle>
        <AlertDescription>
          {scheduled
            ? "Each starts automatically at its time — no need to come back. Download a calendar invite per person below."
            : "Each interviewee has their own room. Share a link, or open a meeting to follow along."}
        </AlertDescription>
      </Alert>

      {meetings.length > 0 && (
        <div className="space-y-1 border-l pl-4">
          {meetings.map((m) => (
            <MeetingResultRow
              key={m.meeting_id}
              meeting={m}
              fallbackTitle={fallbackTitle}
            />
          ))}
        </div>
      )}

      {errors.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>
            {errors.length} couldn't start
          </AlertTitle>
          <AlertDescription>
            <ul className="mt-1 space-y-1">
              {errors.map((e, i) => (
                <li key={i}>
                  <span className="font-medium">{e.name ?? e.email}</span>: {e.error}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex items-center gap-2 border-t pt-4">
        <IconButton asChild label="Back to dashboard">
          <Link to="/">
            <LayoutDashboard />
          </Link>
        </IconButton>
      </div>
    </div>
  );
}

function MeetingResultRow({
  meeting,
  fallbackTitle,
}: {
  meeting: MeetingRecord;
  fallbackTitle: string;
}) {
  const name = meeting.title_override ?? fallbackTitle;
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="text-sm font-medium">{name}</span>
      <StatusBadge status={meeting.status} />
      <div className="ml-auto flex items-center gap-1">
        {meeting.status === "scheduled" ? (
          <>
            <IconButton
              asChild
              variant="outline"
              size="sm"
              label="Add to calendar (.ics)"
            >
              <a href={meetingInviteIcsUrl(meeting.meeting_id)} download>
                <CalendarPlus />
              </a>
            </IconButton>
            {meeting.webapp_url && (
              <CopyButton
                value={meeting.webapp_url}
                label="Copy live link"
                className="h-8 w-8 [&_svg]:size-3.5"
              />
            )}
          </>
        ) : (
          <>
            {meeting.join_url && (
              <CopyButton
                value={meeting.join_url}
                label="Copy join link"
                className="h-8 w-8 [&_svg]:size-3.5"
              />
            )}
            {meeting.webapp_url && (
              <CopyButton
                value={meeting.webapp_url}
                label="Copy live link"
                className="h-8 w-8 [&_svg]:size-3.5"
              />
            )}
            <IconButton asChild size="sm" label="Go to meeting">
              <Link to={`/meetings/${meeting.meeting_id}`}>
                <ArrowRight />
              </Link>
            </IconButton>
          </>
        )}
      </div>
    </div>
  );
}
