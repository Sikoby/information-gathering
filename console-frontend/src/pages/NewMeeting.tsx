import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Input, Textarea } from "@ig/ui";
import { createMeeting, listReferenceTemplates } from "@/lib/api";
import type { ReferenceTemplate } from "@/types";

export function NewMeeting() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [reference, setReference] = useState("");
  const [targetMinutes, setTargetMinutes] = useState(30);
  const [references, setReferences] = useState<ReferenceTemplate[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReferenceTemplates()
      .then((d) => setReferences(d.templates))
      .catch(() => setReferences([]));
  }, []);

  const valid = title.trim().length > 0 && prompt.trim().length > 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);
    try {
      const rec = await createMeeting({
        title: title.trim(),
        prompt: prompt.trim(),
        reference_template: reference || null,
        target_minutes: targetMinutes,
      });
      navigate(`/meetings/${rec.meeting_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <Link
        to="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Meetings
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">New meeting</h1>

      <form onSubmit={submit} className="mt-6 space-y-5">
        <div>
          <label className="text-sm font-medium">Title</label>
          <Input
            className="mt-1"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Q3 platform design review"
            maxLength={200}
          />
        </div>

        <div>
          <label className="text-sm font-medium">Prompt</label>
          <p className="text-xs text-muted-foreground">
            Describe the meeting — who it is with, what to cover, what a good
            outcome looks like. This becomes the agent's briefing.
          </p>
          <Textarea
            className="mt-1"
            rows={10}
            value={prompt}
            maxLength={16000}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="A design review with the platform team to walk through the proposed architecture, surface risks, and assign follow-ups…"
          />
          <p className="mt-1 text-right text-xs text-muted-foreground">
            {prompt.length} / 16000
          </p>
        </div>

        <div className="flex flex-wrap gap-4">
          <div className="min-w-[14rem] flex-1">
            <label className="text-sm font-medium">
              Reference template (optional)
            </label>
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

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={!valid || submitting}>
          {submitting ? "Creating…" : "Create & generate template"}
        </Button>
      </form>
    </div>
  );
}
