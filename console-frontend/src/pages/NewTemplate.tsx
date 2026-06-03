import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Loader2, Plus, Upload, X } from "lucide-react";
import { Input, Textarea } from "@ig/ui";
import {
  createTemplate,
  createTemplateFromDocument,
  listReferenceTemplates,
} from "@/lib/api";
import { Page, PageHeader } from "@/components/Page";
import { Field } from "@/components/Field";
import { IconButton } from "@/components/IconButton";
import type { ReferenceTemplate } from "@/types";

const ACCEPTED_EXT = /\.(pptx|pdf)$/i;
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export function NewTemplate() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [sourcePrompt, setSourcePrompt] = useState("");
  const [reference, setReference] = useState("");
  const [defaultTargetMinutes, setDefaultTargetMinutes] = useState(30);
  const [references, setReferences] = useState<ReferenceTemplate[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listReferenceTemplates()
      .then((d) => setReferences(d.templates))
      .catch(() => setReferences([]));
  }, []);

  const valid = title.trim().length > 0 && sourcePrompt.trim().length > 0;

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const f = e.target.files?.[0] ?? null;
    if (f && !ACCEPTED_EXT.test(f.name)) {
      setError("Only .pptx and .pdf files are supported.");
      e.target.value = "";
      return;
    }
    if (f && f.size > MAX_UPLOAD_BYTES) {
      setError(`File is larger than 50 MB (${Math.round(f.size / 1024 / 1024)} MB).`);
      e.target.value = "";
      return;
    }
    setFile(f);
  };

  const clearFile = () => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        title: title.trim(),
        source_prompt: sourcePrompt.trim(),
        reference_template: reference || null,
        default_target_minutes: defaultTargetMinutes,
      };
      const rec = file
        ? await createTemplateFromDocument(body, file)
        : await createTemplate(body);
      navigate(`/templates/${rec.template_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <Page>
      <PageHeader
        back
        title="New template"
        info="A template is reusable — generate it once, then start as many meetings from it as you want."
      />

      <form onSubmit={submit} className="max-w-2xl space-y-5">
        <Field label="Title">
          <Input
            className="mt-1"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Q3 platform design review"
            maxLength={200}
          />
        </Field>

        <Field
          label="Prompt"
          info="Describe the meeting — who it is with, what to cover, what a good outcome looks like. This becomes the agent's briefing."
        >
          <Textarea
            className="mt-1"
            rows={10}
            value={sourcePrompt}
            maxLength={16000}
            onChange={(e) => setSourcePrompt(e.target.value)}
            placeholder={
              file
                ? "Who you'll present this to, what outcome you want. The slides drive the structure; this gives the agent context around them."
                : "A design review with the platform team to walk through the proposed architecture, surface risks, and assign follow-ups…"
            }
          />
          <p className="mt-1 text-right text-xs text-muted-foreground">
            {sourcePrompt.length} / 16000
          </p>
        </Field>

        <Field
          label="Presentation document (optional)"
          info="Upload a .pptx or .pdf to drive the meeting. Each slide becomes a topic; speaker notes pre-populate so the agent can read them during the meeting."
        >
          {file ? (
            <div className="mt-2 flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm">
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate" title={file.name}>
                {file.name}
              </span>
              <span className="ml-auto text-xs text-muted-foreground">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </span>
              <button
                type="button"
                onClick={clearFile}
                aria-label="Remove file"
                className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <label
              htmlFor="template-document"
              className="mt-2 flex cursor-pointer items-center gap-2 rounded-md border border-dashed bg-card px-3 py-3 text-sm text-muted-foreground hover:bg-secondary"
            >
              <Upload className="h-4 w-4" />
              <span>Choose a .pptx or .pdf…</span>
            </label>
          )}
          <input
            id="template-document"
            ref={fileInputRef}
            type="file"
            accept=".pptx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
            className="hidden"
            onChange={onFileChange}
          />
        </Field>

        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-[14rem] flex-1">
            <Field label="Reference template (optional)">
              <select
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">None</option>
                {references.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="w-44">
            <Field label="Default duration (min)">
              <Input
                className="mt-1"
                type="number"
                min={1}
                max={120}
                value={defaultTargetMinutes}
                onChange={(e) => setDefaultTargetMinutes(Number(e.target.value))}
              />
            </Field>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <IconButton
          type="submit"
          disabled={!valid || submitting}
          label={
            submitting
              ? file
                ? "Uploading & generating…"
                : "Creating…"
              : file
                ? "Create from document"
                : "Create template"
          }
        >
          {submitting ? (
            <Loader2 className="animate-spin" />
          ) : file ? (
            <Upload />
          ) : (
            <Plus />
          )}
        </IconButton>
      </form>
    </Page>
  );
}
