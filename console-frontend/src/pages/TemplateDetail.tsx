import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Check,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  RotateCw,
  Save,
  Trash2,
} from "lucide-react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  InfoTooltip,
  Modal,
  Textarea,
} from "@ig/ui";
import { useTemplate } from "@/hooks/useTemplate";
import {
  ApiError,
  deleteTemplate,
  patchTemplate,
  regenerateTemplate,
} from "@/lib/api";
import { elapsedSeconds } from "@/lib/format";
import { TemplateEditor } from "@/components/TemplateEditor";
import { TemplateStatusIndicator } from "@/components/TemplateStatusIndicator";
import { Page, PageHeader, CenteredMessage } from "@/components/Page";
import { IconButton } from "@/components/IconButton";
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

export function TemplateDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { template, error, loaded } = useTemplate(id);

  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftKey, setDraftKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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

  if (!loaded) return <CenteredMessage>Loading…</CenteredMessage>;
  if (!template || error)
    return <CenteredMessage>{error ?? "Template not found."}</CenteredMessage>;

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
    setDeleteError(null);
    try {
      await deleteTemplate(template.template_id);
      navigate("/");
    } catch (e) {
      setDeleteError(deleteErrorMessage(e));
      setBusy(null);
    }
  };

  const onStartMeeting = async () => {
    if (!(await saveDraft())) return;
    navigate(`/meetings/new?template=${template.template_id}`);
  };

  return (
    <Page>
      <PageHeader
        back
        title={template.title}
        badge={<TemplateStatusIndicator status={template.template_status} />}
      />

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
          onSave={saveDraft}
          onOpenStart={onStartMeeting}
          onRegenerate={onRegenerate}
          onDelete={onDelete}
        />
      )}

      <Modal
        open={deleteError !== null}
        onClose={() => setDeleteError(null)}
        title="Can’t delete this template"
        description={deleteError ?? undefined}
      />
    </Page>
  );
}

/**
 * Turn a failed template-delete into a human sentence. The backend returns a
 * 409 with {total_count, running_count} when meetings still reference the
 * template; everything else falls back to the raw error message.
 */
function deleteErrorMessage(e: unknown): string {
  if (e instanceof ApiError && e.status === 409) {
    const body = e.body as
      | { total_count?: number; running_count?: number }
      | undefined;
    const total = body?.total_count ?? 0;
    const running = body?.running_count ?? 0;
    const count = `${total} meeting${total === 1 ? "" : "s"}`;
    const runningNote =
      running > 0 ? ` (${running} currently running)` : "";
    const which = total === 1 ? "that meeting" : "those meetings";
    return `This template is still used by ${count}${runningNote}. Delete ${which} first, then you can delete the template.`;
  }
  return e instanceof Error ? e.message : String(e);
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
        <IconButton
          onClick={onRegenerate}
          disabled={busy}
          label={busy ? "Retrying…" : "Retry generation"}
        >
          {busy ? <Loader2 className="animate-spin" /> : <RotateCw />}
        </IconButton>
        <IconButton
          variant="ghost"
          onClick={onDelete}
          className="ml-auto text-destructive"
          label="Delete template"
        >
          <Trash2 />
        </IconButton>
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
  onSave: () => void;
  onOpenStart: () => void;
  onRegenerate: () => void;
  onDelete: () => void;
}) {
  const startDisabled = busy !== null;
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
        <div className="flex items-center gap-1.5">
          <h2 className="text-sm font-semibold text-muted-foreground">Prompt</h2>
          <InfoTooltip
            size="sm"
            content="The briefing the agent runs the meeting against. Save edits, or regenerate to rebuild the template from it."
          />
        </div>
        <Textarea
          className="mt-2"
          rows={8}
          value={draft.source_prompt}
          maxLength={16000}
          onChange={(e) => setDraft({ ...draft, source_prompt: e.target.value })}
        />
      </section>

      <section>
        <div className="flex items-center gap-1.5">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Template
          </h2>
          <InfoTooltip
            size="sm"
            content="The structured meeting plan generated from the prompt. Edit its name, description, and the tree of topics and questions below."
          />
        </div>
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
        <IconButton
          onClick={onOpenStart}
          disabled={startDisabled}
          label={busy === "start" ? "Starting…" : "Start"}
        >
          <Play />
        </IconButton>
        <IconButton
          variant="outline"
          onClick={onSave}
          disabled={busy !== null || !dirty}
          label={busy === "save" ? "Saving…" : dirty ? "Save changes" : "Saved"}
        >
          {busy === "save" ? (
            <Loader2 className="animate-spin" />
          ) : dirty ? (
            <Save />
          ) : (
            <Check />
          )}
        </IconButton>
        <IconButton
          variant="outline"
          onClick={onRegenerate}
          disabled={busy !== null}
          label={busy === "regenerate" ? "Regenerating…" : "Regenerate template"}
        >
          <RefreshCw
            className={busy === "regenerate" ? "animate-spin" : undefined}
          />
        </IconButton>
        <IconButton
          variant="ghost"
          onClick={onDelete}
          disabled={busy !== null}
          className="ml-auto text-destructive"
          label="Delete template"
        >
          <Trash2 />
        </IconButton>
      </div>
    </div>
  );
}

