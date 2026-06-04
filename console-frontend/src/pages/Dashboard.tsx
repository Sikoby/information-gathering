import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Plus, Users } from "lucide-react";
import { InfoTooltip } from "@ig/ui";
import { Page } from "@/components/Page";
import { IconButton } from "@/components/IconButton";
import { useTemplates } from "@/hooks/useTemplates";
import { useMeetings } from "@/hooks/useMeetings";
import { TemplateCard } from "@/components/TemplateCard";
import { MeetingCard } from "@/components/MeetingCard";
import { MeetingsCalendar } from "@/components/MeetingsCalendar";
import type { MeetingStatus } from "@/types";

const MEETING_GROUPS: { status: MeetingStatus; label: string }[] = [
  { status: "scheduled", label: "Scheduled" },
  { status: "running", label: "Running" },
  { status: "done", label: "Done" },
];

export function Dashboard() {
  const {
    templates,
    error: templatesError,
    loaded: templatesLoaded,
  } = useTemplates();
  const {
    meetings,
    error: meetingsError,
    loaded: meetingsLoaded,
  } = useMeetings();

  const templateById = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of templates) m.set(t.template_id, t.title);
    return m;
  }, [templates]);

  return (
    <Page className="space-y-12">
      <section>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <h2 className="text-2xl font-semibold tracking-tight">Templates</h2>
            <InfoTooltip
              size="lg"
              content="A template is a reusable meeting definition — generate it once, then start as many meetings from it as you want."
            />
          </div>
          <IconButton asChild label="New template">
            <Link to="/templates/new">
              <Plus />
            </Link>
          </IconButton>
        </div>
        {templatesError && (
          <p className="mt-4 text-sm text-destructive">{templatesError}</p>
        )}
        {templatesLoaded && templates.length === 0 && !templatesError && (
          <p className="mt-6 text-sm text-muted-foreground">
            No templates yet. Create one to get started — then launch a meeting
            from it.
          </p>
        )}
        <div className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <TemplateCard key={t.template_id} template={t} />
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <h2 className="text-2xl font-semibold tracking-tight">Meetings</h2>
            <InfoTooltip
              size="lg"
              content="A meeting is a live, AI-run instance of a template. It goes from running to done, and several can run in parallel."
            />
          </div>
          <div className="flex items-center gap-2">
            <IconButton asChild label="Batch create meetings">
              <Link to="/meetings/batch">
                <Users />
              </Link>
            </IconButton>
            <IconButton asChild label="New meeting">
              <Link to="/meetings/new">
                <Plus />
              </Link>
            </IconButton>
          </div>
        </div>
        {meetingsError && (
          <p className="mt-4 text-sm text-destructive">{meetingsError}</p>
        )}
        {meetingsLoaded && meetings.length === 0 && !meetingsError && (
          <p className="mt-4 text-sm text-muted-foreground">
            No meetings yet.
          </p>
        )}
        <MeetingsCalendar meetings={meetings} templateById={templateById} />
        <div className="mt-6 grid gap-6 md:grid-cols-3">
          {MEETING_GROUPS.map((group) => {
            const items = meetings.filter((m) => m.status === group.status);
            return (
              <section key={group.status}>
                <h3 className="mb-3 text-sm font-semibold text-muted-foreground">
                  {group.label} ({items.length})
                </h3>
                <div className="space-y-3">
                  {items.map((m) => (
                    <MeetingCard
                      key={m.meeting_id}
                      meeting={m}
                      templateTitle={templateById.get(m.template_id) ?? null}
                    />
                  ))}
                  {items.length === 0 && (
                    <p className="text-xs text-muted-foreground">None</p>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </section>
    </Page>
  );
}
