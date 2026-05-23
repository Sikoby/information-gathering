import { Link } from "react-router-dom";
import { Button } from "@ig/ui";
import { useMeetings } from "@/hooks/useMeetings";
import { MeetingCard } from "@/components/MeetingCard";
import type { MeetingStatus } from "@/types";

const GROUPS: { status: MeetingStatus; label: string }[] = [
  { status: "planned", label: "Planned" },
  { status: "running", label: "Running" },
  { status: "done", label: "Done" },
];

export function Dashboard() {
  const { meetings, error, loaded } = useMeetings();

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Meetings</h1>
        <Button asChild>
          <Link to="/new">New meeting</Link>
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      {loaded && meetings.length === 0 && !error && (
        <p className="mt-10 text-sm text-muted-foreground">
          No meetings yet. Create one to get started.
        </p>
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-3">
        {GROUPS.map((group) => {
          const items = meetings.filter((m) => m.status === group.status);
          return (
            <section key={group.status}>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {group.label} ({items.length})
              </h2>
              <div className="space-y-3">
                {items.map((m) => (
                  <MeetingCard key={m.meeting_id} meeting={m} />
                ))}
                {items.length === 0 && (
                  <p className="text-xs text-muted-foreground">None</p>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
