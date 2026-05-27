import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FileText, Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Badge, Button, Input, Textarea } from "@ig/ui";
import { useTemplate } from "@/hooks/useTemplate";
import { useMeetings } from "@/hooks/useMeetings";
import {
  deleteTemplate,
  patchTemplate,
  regenerateTemplate,
  startMeetingFromTemplate,
} from "@/lib/api";
import { elapsedSeconds } from "@/lib/format";
import { TemplateEditor } from "@/components/TemplateEditor";
import { TemplateStatusBadge } from "@/components/StatusBadge";
import type { Template, TemplateRecord } from "@/types";

type Draft = {
  title: string;
  source_prompt: string;
  template: Template | null;
  default_target_minutes: number;
};

function draftFromTemplate(t: TemplateRecord): Draft {
  return {
    title: t.title,
    source_prompt: t.source_prompt,
    template: t.template,
    default_target_minutes: t.default_target_minutes,
  };
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

export function TemplateDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { template, error, loaded } = useTemplate(id);
  const { meetings } = useMeetings();

  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftKey, setDraftKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [startOpen, setStartOpen] = useState(false);

  useEffect(() => {
    if (!template) return;
    const key = `${template.template_id}:${template.generation_seq}:${template.template_status}`;
    if (key !== draftKey) {
      setDraft(draftFromTemplate(template));
      setDraftKey(key);
    }
  }, [template, draftKey]);

  const dirty = useMemo(() => {
    if (!template || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(draftFromTemplate(template));
  }, [template, draft]);

  const runningMeeting = useMemo(
    () => meetings.find((m) => m.status === "running") ?? null,
    [meetings],
  );

  if (!loaded) return <Centered>Loading…</Centered>;
  if (!template || error)
    return <Centered>{error ?? "Template not found."}</Centered>;

  const saveDraft = async (): Promise<boolean> => {
    if (!draft || !dirty) return true;
    setBusy("save");
    setActionError(null);
    try {
      await patchTemplate(template.template_id, {
        title: draft.title,
        source_prompt: draft.source_prompt,
        default_target_minutes: draft.default_target_minutes,
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

  const onRegenerate = () =>
    runAction("regenerate", () =>
      regenerateTemplate(
        template.template_id,
        draft && draft.source_prompt !== template.source_prompt
          ? { source_prompt: draft.source_prompt }
          : {},
      ),
    );

  const onDelete = async () => {
    setBusy("delete");
    setActionError(null);
    try {
      await deleteTemplate(template.template_id);
      navigate("/");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

  const onStart = async (opts: {
    title_override?: string;
    target_minutes?: number;
  }) => {
    if (!(await saveDraft())) return;
    setBusy("start");
    setActionError(null);
    try {
      const meeting = await startMeetingFromTemplate(
        template.template_id,
        opts,
      );
      navigate(`/meetings/${meeting.meeting_id}`);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <Link
        to="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back
      </Link>
      <div className="mt-2 flex items-start justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {template.title}
        </h1>
        <TemplateStatusBadge status={template.template_status} />
      </div>

      {template.document_filename && (
        <DocumentBadge
          filename={template.document_filename}
          slides={template.document_outline?.slides.length ?? null}
        />
      )}

      {actionError && (
        <p className="mt-3 text-sm text-destructive">{actionError}</p>
      )}

      {template.template_status === "generating" && (
        <GeneratingView since={template.updated_at} />
      )}

      {template.template_status === "failed" && (
        <FailedView
          error={template.template_error}
          busy={busy === "regenerate"}
          onRegenerate={onRegenerate}
          onDelete={onDelete}
        />
      )}

      {template.template_status === "ready" && draft && (
        <ReadyEditor
          draft={draft}
          setDraft={setDraft}
          dirty={dirty}
          busy={busy}
          approved={template.template_approved}
          runningMeeting={runningMeeting?.meeting_id ?? null}
          onSave={saveDraft}
          onOpenStart={() => setStartOpen(true)}
          onRegenerate={onRegenerate}
          onDelete={onDelete}
        />
      )}

      {startOpen && draft && (
        <StartMeetingDialog
          defaultTitle={draft.title}
          defaultTargetMinutes={draft.default_target_minutes}
          busy={busy === "start"}
          onCancel={() => setStartOpen(false)}
          onSubmit={async (opts) => {
            setStartOpen(false);
            await onStart(opts);
          }}
        />
      )}
    </div>
  );
}

function DocumentBadge({
  filename,
  slides,
}: {
  filename: string;
  slides: number | null;
}) {
  return (
    <div className="mt-3 inline-flex items-center gap-2 rounded-md border bg-card px-3 py-1.5 text-xs text-muted-foreground">
      <FileText className="h-3.5 w-3.5" />
      <span className="font-medium text-foreground">{filename}</span>
      {slides !== null && (
        <Badge variant="outline" className="text-[10px]">
          {slides} slide{slides === 1 ? "" : "s"}
        </Badge>
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
      <p className="text-sm tabular-nums text-muted-foreground">
        elapsed {mm}:{ss}
      </p>
    </div>
  );
}

function FailedView({
  error,
  busy,
  onRegenerate,
  onDelete,
}: {
  error: string | null;
  busy: boolean;
  onRegenerate: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="mt-8 space-y-4">
      <Alert variant="destructive">
        <AlertTitle>Template generation failed</AlertTitle>
        <AlertDescription>{error ?? "Unknown error."}</AlertDescription>
      </Alert>
      <div className="flex gap-2">
        <Button onClick={onRegenerate} disabled={busy}>
          {busy ? "Retrying…" : "Retry generation"}
        </Button>
        <Button
          variant="ghost"
          onClick={onDelete}
          className="ml-auto text-destructive"
        >
          Delete template
        </Button>
      </div>
    </div>
  );
}

function ReadyEditor({
  draft,
  setDraft,
  dirty,
  busy,
  approved,
  runningMeeting,
  onSave,
  onOpenStart,
  onRegenerate,
  onDelete,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  dirty: boolean;
  busy: string | null;
  approved: boolean | null;
  runningMeeting: string | null;
  onSave: () => void;
  onOpenStart: () => void;
  onRegenerate: () => void;
  onDelete: () => void;
}) {
  const startDisabled = busy !== null || runningMeeting !== null;
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
        <h2 className="text-sm font-semibold text-muted-foreground">Prompt</h2>
        <Textarea
          className="mt-2"
          rows={8}
          value={draft.source_prompt}
          maxLength={16000}
          onChange={(e) => setDraft({ ...draft, source_prompt: e.target.value })}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          The prompt is the briefing the agent runs the meeting against. Save
          edits, or Regenerate to rebuild the template from it.
        </p>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-muted-foreground">Template</h2>
        <div className="mt-3">
          {draft.template && (
            <TemplateEditor
              template={draft.template}
              onChange={(t) => setDraft({ ...draft, template: t })}
            />
          )}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2 border-t pt-4">
        <Button onClick={onOpenStart} disabled={startDisabled}>
          {busy === "start" ? "Starting…" : "Start meeting"}
        </Button>
        {runningMeeting && (
          <Link
            to={`/meetings/${runningMeeting}`}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            another meeting is running →
          </Link>
        )}
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

function StartMeetingDialog({
  defaultTitle,
  defaultTargetMinutes,
  busy,
  onCancel,
  onSubmit,
}: {
  defaultTitle: string;
  defaultTargetMinutes: number;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (opts: {
    title_override?: string;
    target_minutes?: number;
  }) => void;
}) {
  const [titleOverride, setTitleOverride] = useState("");
  const [targetMinutes, setTargetMinutes] = useState(defaultTargetMinutes);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Start meeting</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Launch this template as a new meeting. The template stays put — you
          can start more meetings from it later.
        </p>

        <div className="mt-5 space-y-4">
          <div>
            <label className="text-sm font-medium">Title (optional)</label>
            <Input
              className="mt-1"
              value={titleOverride}
              onChange={(e) => setTitleOverride(e.target.value)}
              placeholder={defaultTitle}
              maxLength={200}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Defaults to the template title.
            </p>
          </div>
          <div className="w-36">
            <label className="text-sm font-medium">Duration (min)</label>
            <Input
              className="mt-1"
              type="number"
              min={1}
              max={120}
              value={targetMinutes}
              onChange={(e) => setTargetMinutes(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            disabled={busy}
            onClick={() =>
              onSubmit({
                title_override: titleOverride.trim() || undefined,
                target_minutes:
                  targetMinutes && targetMinutes !== defaultTargetMinutes
                    ? targetMinutes
                    : undefined,
              })
            }
          >
            {busy ? "Starting…" : "Start meeting"}
          </Button>
        </div>
      </div>
    </div>
  );
}
