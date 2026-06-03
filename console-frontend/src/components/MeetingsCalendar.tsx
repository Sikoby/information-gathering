import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Calendar } from "@ig/ui";
import type { MeetingRecord } from "@/types";
import { formatTimeOfDay, localDayKey } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

/** The instant a meeting sits at on the calendar, per its lifecycle stage. */
function meetingInstant(m: MeetingRecord): string | null {
  if (m.status === "scheduled") return m.scheduled_at;
  if (m.status === "running") return m.dispatched_at ?? m.created_at;
  return m.ended_at ?? m.created_at;
}

type Positioned = { meeting: MeetingRecord; iso: string; time: number };

export function MeetingsCalendar({
  meetings,
  templateById,
}: {
  meetings: MeetingRecord[];
  templateById: Map<string, string>;
}) {
  const [selected, setSelected] = useState<Date>(() => new Date());

  const positioned = useMemo<Positioned[]>(() => {
    const out: Positioned[] = [];
    for (const meeting of meetings) {
      const iso = meetingInstant(meeting);
      if (!iso) continue;
      const time = new Date(iso).getTime();
      if (Number.isNaN(time)) continue;
      out.push({ meeting, iso, time });
    }
    return out;
  }, [meetings]);

  const daysWithMeetings = useMemo<Date[]>(() => {
    const byDay = new Map<string, Date>();
    for (const p of positioned) {
      const key = localDayKey(p.iso);
      if (!byDay.has(key)) byDay.set(key, new Date(p.iso));
    }
    return [...byDay.values()];
  }, [positioned]);

  const selectedKey = selected.toDateString();
  const groups = useMemo(() => {
    const items = positioned
      .filter((p) => localDayKey(p.iso) === selectedKey)
      .sort((a, b) => a.time - b.time);
    const ordered: { label: string; items: Positioned[] }[] = [];
    for (const p of items) {
      const label = formatTimeOfDay(p.iso);
      const last = ordered[ordered.length - 1];
      if (last && last.label === label) last.items.push(p);
      else ordered.push({ label, items: [p] });
    }
    return ordered;
  }, [positioned, selectedKey]);

  const dayCount = groups.reduce((n, g) => n + g.items.length, 0);
  const headerLabel = selected.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="mt-6 grid gap-6 md:grid-cols-[auto_1fr]">
      <Calendar
        mode="single"
        selected={selected}
        onSelect={(d) => d && setSelected(d)}
        modifiers={{ hasMeeting: daysWithMeetings }}
        modifiersClassNames={{
          hasMeeting:
            "relative after:absolute after:bottom-1 after:left-1/2 after:h-1 after:w-1 after:-translate-x-1/2 after:rounded-full after:bg-current",
        }}
        className="rounded-md border p-3"
      />

      <div>
        <div className="flex items-baseline gap-2">
          <h3 className="text-lg font-semibold tracking-tight">
            {headerLabel}
          </h3>
          <span className="text-sm text-muted-foreground">
            {dayCount === 0
              ? "No meetings"
              : `${dayCount} meeting${dayCount === 1 ? "" : "s"}`}
          </span>
        </div>

        {dayCount === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Nothing scheduled for this day.
          </p>
        ) : (
          <div className="mt-3 space-y-4">
            {groups.map((g) => (
              <div key={g.label} className="flex gap-3">
                <div className="w-20 shrink-0 pt-0.5 text-sm font-medium tabular-nums text-muted-foreground">
                  {g.label}
                </div>
                <ul className="flex-1 space-y-1 border-l pl-3">
                  {g.items.map((p) => {
                    const title =
                      p.meeting.title_override ??
                      templateById.get(p.meeting.template_id) ??
                      "Meeting";
                    return (
                      <li key={p.meeting.meeting_id}>
                        <Link
                          to={`/meetings/${p.meeting.meeting_id}`}
                          className="-mx-2 flex items-center justify-between gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-accent"
                        >
                          <span className="truncate text-sm font-medium">
                            {title}
                          </span>
                          <StatusBadge status={p.meeting.status} />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
