import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Button, Textarea } from "@ig/ui";
import { useMeeting } from "@/hooks/useMeeting";
import {
  deleteMeeting,
  patchMeeting,
  regenerateMeeting,
  startMeeting,
} from "@/lib/api";
import { elapsedSeconds } from "@/lib/format";
import { TemplateEditor } from "@/components/TemplateEditor";
import { StatusBadge } from "@/components/StatusBadge";
import type { MeetingRecord, Template } from "@/types";

type Draft = { title: string; prompt: string; template: Template | null };

function draftFromMeeting(m: MeetingRecord): Draft {
  return { title: m.title, prompt: m.prompt, template: m.template };
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

export function MeetingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { meeting, error, loaded } = useMeeting(id);

  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftKey, setDraftKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // (Re)initialise the draft when the meeting's generation/template state
  // changes — but not on every poll, so in-progress edits are preserved.
  useEffect(() => {
    if (!meeting) return;
    const key = `${meeting.meeting_id}:${meeting.generation_seq}:${meeting.template_status}`;
    if (key !== draftKey) {
      setDraft(draftFromMeeting(meeting));
      setDraftKey(key);
    }
  }, [meeting, draftKey]);

  const dirty = useMemo(() => {
    if (!meeting || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(draftFromMeeting(meeting));
  }, [meeting, draft]);

  if (!loaded) return <Centered>Loading…</Centered>;
  if (!meeting || error)
    return <Centered>{error ?? "Meeting not found."}</Centered>;

  const saveDraft = async (): Promise<boolean> => {
    if (!draft || !dirty) return true;
    setBusy("save");
    setActionError(null);
    try {
      await patchMeeting(meeting.meeting_id, {
        title: draft.title,
        prompt: draft.prompt,
        ...(draft.template ? { template: draft.template } : {}),
      });
      return true;
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    setBusy(name);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const onStart = async () => {
    if (!(await saveDraft())) return;
    await runAction("start", () => startMeeting(meeting.meeting_id));
  };

  const onRegenerate = () =>
    runAction("regenerate", () =>
      regenerateMeeting(
        meeting.meeting_id,
        draft && draft.prompt !== meeting.prompt
          ? { prompt: draft.prompt }
          : {},
      ),
    );

  const onDelete = async () => {
    setBusy("delete");
    setActionError(null);
    try {
      await deleteMeeting(meeting.meeting_id);
      navigate("/");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <Link
        to="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Meetings
      </Link>
      <div className="mt-2 flex items-start justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {meeting.title}
        </h1>
        <StatusBadge status={meeting.status} />
      </div>

      {actionError && (
        <p className="mt-3 text-sm text-destructive">{actionError}</p>
      )}

      {meeting.status === "planned" &&
        meeting.template_status === "generating" && (
          <GeneratingView since={meeting.updated_at} />
        )}

      {meeting.status === "planned" &&
        meeting.template_status === "failed" && (
          <FailedView
            error={meeting.template_error}
            busy={busy === "regenerate"}
            onRegenerate={onRegenerate}
          />
        )}

      {meeting.status === "planned" &&
        meeting.template_status === "ready" &&
        draft && (
          <PlannedEditor
            draft={draft}
            setDraft={setDraft}
            dirty={dirty}
            busy={busy}
            approved={meeting.template_approved}
            onSave={saveDraft}
            onStart={onStart}
            onRegenerate={onRegenerate}
            onDelete={onDelete}
          />
        )}

      {meeting.status !== "planned" && (
        <RunningOrDoneView
          meeting={meeting}
          busy={busy}
          onDelete={meeting.status === "done" ? onDelete : undefined}
        />
      )}
    </div>
  );
}

function GeneratingView({ since }: { since: string }) {
  const [seconds, setSeconds] = useState(() => elapsedSeconds(since));
  useEffect(() => {
    setSeconds(elapsedSeconds(since));
    const id = window.setInterval(() => setSeconds(elapsedSeconds(since)), 1000);
    return () => window.clearInterval(id);
  }, [since]);
  const mm = Math.floor(seconds / 60);
  const ss = String(seconds % 60).padStart(2, "0");
  return (
    <div className="mt-8 flex flex-col items-center gap-3 rounded-md border border-dashed p-10 text-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <p className="text-sm font-medium">Designing your meeting template…</p>
      <p className="max-w-md text-sm text-muted-foreground">
        The implementation + critique loop is running — propose a template,
        critique it, revise. This usually takes 1-4 minutes; the page updates
        itself the moment it finishes.
      </p>
      <p className="font-mono text-sm tabular-nums text-muted-foreground">
        elapsed {mm}:{ss}
      </p>
    </div>
  );
}

function FailedView({
  error,
  busy,
  onRegenerate,
}: {
  error: string | null;
  busy: boolean;
  onRegenerate: () => void;
}) {
  return (
    <div className="mt-8 space-y-4">
      <Alert variant="destructive">
        <AlertTitle>Template generation failed</AlertTitle>
        <AlertDescription>{error ?? "Unknown error."}</AlertDescription>
      </Alert>
      <Button onClick={onRegenerate} disabled={busy}>
        {busy ? "Retrying…" : "Retry generation"}
      </Button>
    </div>
  );
}

function PlannedEditor({
  draft,
  setDraft,
  dirty,
  busy,
  approved,
  onSave,
  onStart,
  onRegenerate,
  onDelete,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  dirty: boolean;
  busy: string | null;
  approved: boolean | null;
  onSave: () => void;
  onStart: () => void;
  onRegenerate: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="mt-6 space-y-8">
      {approved === false && (
        <Alert variant="warning">
          <AlertTitle>Template generated with open critique notes</AlertTitle>
          <AlertDescription>
            The critic did not fully approve this template. Review it before
            starting, or regenerate.
          </AlertDescription>
        </Alert>
      )}

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Prompt
        </h2>
        <Textarea
          className="mt-2"
          rows={8}
          value={draft.prompt}
          maxLength={16000}
          onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          The prompt is the briefing the agent extracts objectives from. Save
          edits, or Regenerate to rebuild the template from it.
        </p>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Template
        </h2>
        <div className="mt-3">
          {draft.template && (
            <TemplateEditor
              template={draft.template}
              onChange={(t) => setDraft({ ...draft, template: t })}
            />
          )}
        </div>
      </section>

      <div className="flex flex-wrap gap-2 border-t pt-4">
        <Button onClick={onStart} disabled={busy !== null}>
          {busy === "start" ? "Starting…" : "Start meeting"}
        </Button>
        <Button
          variant="outline"
          onClick={onSave}
          disabled={busy !== null || !dirty}
        >
          {busy === "save" ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </Button>
        <Button
          variant="outline"
          onClick={onRegenerate}
          disabled={busy !== null}
        >
          {busy === "regenerate" ? "Regenerating…" : "Regenerate template"}
        </Button>
        <Button
          variant="ghost"
          onClick={onDelete}
          disabled={busy !== null}
          className="ml-auto text-destructive"
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

function RunningOrDoneView({
  meeting,
  busy,
  onDelete,
}: {
  meeting: MeetingRecord;
  busy: string | null;
  onDelete?: () => void;
}) {
  return (
    <div className="mt-6 space-y-5">
      {meeting.status === "running" && (
        <Alert>
          <AlertTitle>Meeting in progress</AlertTitle>
          <AlertDescription>
            This meeting is running. Open the live view to watch it unfold.
          </AlertDescription>
        </Alert>
      )}
      {meeting.status === "done" && (
        <Alert variant="success">
          <AlertTitle>Meeting finished</AlertTitle>
          <AlertDescription>
            Ended{meeting.end_reason ? ` — ${meeting.end_reason}` : ""}.
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-2">
        {meeting.status === "running" && meeting.join_url && (
          <Button asChild>
            <a href={meeting.join_url} target="_blank" rel="noreferrer">
              Join meeting
            </a>
          </Button>
        )}
        {meeting.webapp_url && (
          <Button variant="outline" asChild>
            <a href={meeting.webapp_url} target="_blank" rel="noreferrer">
              Open live view
            </a>
          </Button>
        )}
        {onDelete && (
          <Button
            variant="ghost"
            onClick={onDelete}
            disabled={busy !== null}
            className="ml-auto text-destructive"
          >
            Delete
          </Button>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
        <Info label="Duration" value={`${meeting.target_minutes} min`} />
        <Info label="Template" value={meeting.template?.name ?? "—"} />
        <Info label="Run id" value={meeting.run_id ?? "—"} />
      </dl>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Prompt
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm text-foreground/90">
          {meeting.prompt}
        </p>
      </section>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate font-mono text-xs" title={value}>
        {value}
      </dd>
    </div>
  );
}
