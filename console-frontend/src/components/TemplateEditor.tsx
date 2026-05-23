import { Badge, Button, Input, Textarea } from "@ig/ui";
import type { NotebookSection, Phase, Template } from "@/types";
import { slugify } from "@/lib/format";

function replaceAt<T>(list: T[], idx: number, patch: Partial<T>): T[] {
  return list.map((item, i) => (i === idx ? { ...item, ...patch } : item));
}

/** Controlled editor for a meeting Template (sections + phases). */
export function TemplateEditor({
  template,
  onChange,
  disabled = false,
}: {
  template: Template;
  onChange: (t: Template) => void;
  disabled?: boolean;
}) {
  const setSections = (sections: NotebookSection[]) =>
    onChange({ ...template, sections });
  const setPhases = (phases: Phase[]) => onChange({ ...template, phases });

  const phaseTotal = template.phases.reduce(
    (sum, p) => sum + (p.target_fraction || 0),
    0,
  );

  const addSection = () =>
    setSections([
      ...template.sections,
      {
        id: slugify(`section ${template.sections.length + 1}`),
        label: "New section",
        description: "",
        repeated: true,
      },
    ]);

  const addPhase = () =>
    setPhases([
      ...template.phases,
      {
        id: slugify(`phase ${template.phases.length + 1}`),
        label: "New phase",
        goal: "",
        target_fraction: 0.1,
        sections_in_focus: [],
      },
    ]);

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
        <div>
          <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Name
          </label>
          <Input
            className="mt-1"
            value={template.name}
            disabled={disabled}
            onChange={(e) => onChange({ ...template, name: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Description
          </label>
          <Input
            className="mt-1"
            value={template.description}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...template, description: e.target.value })
            }
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            Sections ({template.sections.length})
          </h3>
          {!disabled && (
            <Button type="button" variant="outline" size="sm" onClick={addSection}>
              Add section
            </Button>
          )}
        </div>
        <div className="mt-3 space-y-3">
          {template.sections.map((s, idx) => (
            <div key={idx} className="rounded-md border p-3">
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs text-muted-foreground">{s.id}</code>
                {!disabled && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setSections(template.sections.filter((_, i) => i !== idx))
                    }
                  >
                    Remove
                  </Button>
                )}
              </div>
              <Input
                className="mt-2"
                value={s.label}
                disabled={disabled}
                placeholder="Label"
                onChange={(e) =>
                  setSections(
                    replaceAt(template.sections, idx, { label: e.target.value }),
                  )
                }
              />
              <Textarea
                className="mt-2"
                rows={2}
                value={s.description}
                disabled={disabled}
                placeholder="What belongs in this section"
                onChange={(e) =>
                  setSections(
                    replaceAt(template.sections, idx, {
                      description: e.target.value,
                    }),
                  )
                }
              />
              <label className="mt-2 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={s.repeated}
                  disabled={disabled}
                  onChange={(e) =>
                    setSections(
                      replaceAt(template.sections, idx, {
                        repeated: e.target.checked,
                      }),
                    )
                  }
                />
                Repeated (many entries expected)
              </label>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">
            Phases ({template.phases.length})
          </h3>
          <div className="flex items-center gap-2">
            <Badge
              variant={Math.abs(phaseTotal - 1) < 0.011 ? "success" : "warning"}
            >
              fractions {phaseTotal.toFixed(2)}
            </Badge>
            {!disabled && (
              <Button type="button" variant="outline" size="sm" onClick={addPhase}>
                Add phase
              </Button>
            )}
          </div>
        </div>
        <div className="mt-3 space-y-3">
          {template.phases.map((p, idx) => (
            <div key={idx} className="rounded-md border p-3">
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs text-muted-foreground">{p.id}</code>
                {!disabled && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setPhases(template.phases.filter((_, i) => i !== idx))
                    }
                  >
                    Remove
                  </Button>
                )}
              </div>
              <div className="mt-2 flex gap-2">
                <Input
                  className="flex-1"
                  value={p.label}
                  disabled={disabled}
                  placeholder="Label"
                  onChange={(e) =>
                    setPhases(
                      replaceAt(template.phases, idx, { label: e.target.value }),
                    )
                  }
                />
                <Input
                  className="w-28"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={p.target_fraction}
                  disabled={disabled}
                  onChange={(e) =>
                    setPhases(
                      replaceAt(template.phases, idx, {
                        target_fraction: Number(e.target.value),
                      }),
                    )
                  }
                />
              </div>
              <Textarea
                className="mt-2"
                rows={2}
                value={p.goal}
                disabled={disabled}
                placeholder="Phase goal"
                onChange={(e) =>
                  setPhases(
                    replaceAt(template.phases, idx, { goal: e.target.value }),
                  )
                }
              />
              <div className="mt-2">
                <span className="text-xs text-muted-foreground">
                  Sections in focus
                </span>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                  {template.sections.map((s) => {
                    const on = p.sections_in_focus.includes(s.id);
                    return (
                      <label
                        key={s.id}
                        className="flex items-center gap-1 text-xs"
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={disabled}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...p.sections_in_focus, s.id]
                              : p.sections_in_focus.filter((x) => x !== s.id);
                            setPhases(
                              replaceAt(template.phases, idx, {
                                sections_in_focus: next,
                              }),
                            );
                          }}
                        />
                        {s.id}
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
