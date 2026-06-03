import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Input,
  Textarea,
} from "@ig/ui";
import { useTemplates } from "@/hooks/useTemplates";
import {
  meetingInviteIcsUrl,
  scheduleMeetingFromTemplate,
  startMeetingFromTemplate,
} from "@/lib/api";
import { CopyButton } from "@/components/CopyButton";
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

/** Local-time value for a `<input type="datetime-local">` (no seconds). */
function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
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
  const [scheduledAt, setScheduledAt] = useState(""); // datetime-local value
  const [invitees, setInvitees] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MeetingRecord | null>(null);

  // Floor the picker at "now" so the obvious mistake (a past time) can't be
  // entered; the backend re-checks against its own clock.
  const minLocal = useMemo(() => toLocalInputValue(new Date()), []);

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
    if (!selected || !scheduledAt) return;
    setBusy(true);
    setError(null);
    try {
      const meeting = await scheduleMeetingFromTemplate(selected.template_id, {
        scheduled_at: new Date(scheduledAt).toISOString(),
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
    <div className="mx-auto max-w-2xl px-6 py-8">
      <Link
        to="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">New meeting</h1>

      {loaded && ready.length === 0 && (
        <Alert className="mt-6">
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
          <div className="mt-6 space-y-6">
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

            <div className="inline-flex rounded-md border p-0.5">
              <ModeTab active={mode === "now"} onClick={() => setMode("now")}>
                Start now
              </ModeTab>
              <ModeTab
                active={mode === "schedule"}
                onClick={() => setMode("schedule")}
              >
                Schedule
              </ModeTab>
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
                  <Input
                    className="mt-1 w-64"
                    type="datetime-local"
                    min={minLocal}
                    value={scheduledAt}
                    onChange={(e) => setScheduledAt(e.target.value)}
                  />
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
                <Button onClick={onStartNow} disabled={busy || !selected}>
                  {busy ? "Starting…" : "Start meeting"}
                </Button>
              ) : (
                <Button
                  onClick={onSchedule}
                  disabled={busy || !selected || !scheduledAt}
                >
                  {busy ? "Scheduling…" : "Schedule meeting"}
                </Button>
              )}
              <Button variant="ghost" asChild>
                <Link to="/">Cancel</Link>
              </Button>
            </div>
          </div>
        )
      )}
    </div>
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

function ScheduledPanel({
  meeting,
  onGo,
}: {
  meeting: MeetingRecord;
  onGo: () => void;
}) {
  return (
    <div className="mt-6 space-y-6">
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
        <Button asChild>
          <a href={meetingInviteIcsUrl(meeting.meeting_id)} download>
            Add to calendar (.ics)
          </a>
        </Button>
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

      {meeting.invitees.length > 0 && (
        <Field label={`Invitees (${meeting.invitees.length})`}>
          <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
            {meeting.invitees.map((email) => (
              <li key={email}>{email}</li>
            ))}
          </ul>
        </Field>
      )}

      <div className="flex items-center gap-2 border-t pt-4">
        <Button onClick={onGo}>Go to meeting</Button>
        <Button variant="ghost" asChild>
          <Link to="/">Back to dashboard</Link>
        </Button>
      </div>
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
    <div className="mt-6 space-y-6">
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

      <div className="flex items-center gap-2 border-t pt-4">
        <Button onClick={onGo}>Go to meeting</Button>
        <Button variant="ghost" asChild>
          <Link to="/">Back to dashboard</Link>
        </Button>
      </div>
    </div>
  );
}

function LinkField({
  label,
  hint,
  url,
}: {
  label: string;
  hint?: string;
  url: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="mt-1 flex gap-2">
        <Input
          readOnly
          value={url}
          className="flex-1"
          onFocus={(e) => e.currentTarget.select()}
        />
        <CopyButton value={url} />
        <Button variant="outline" size="sm" asChild>
          <a href={url} target="_blank" rel="noreferrer">
            Open
          </a>
        </Button>
      </div>
    </Field>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function ModeTab({
  active,
  onClick,
  disabled,
  hint,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={disabled ? hint : undefined}
      className={[
        "rounded px-3 py-1 text-sm font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground shadow"
          : "text-muted-foreground hover:text-foreground",
        disabled ? "cursor-not-allowed opacity-50" : "",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
