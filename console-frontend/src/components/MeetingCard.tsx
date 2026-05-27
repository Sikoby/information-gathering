import { Link } from "react-router-dom";
import { Card } from "@ig/ui";
import type { MeetingRecord } from "@/types";
import { relativeTime } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

export function MeetingCard({
  meeting,
  templateTitle,
}: {
  meeting: MeetingRecord;
  templateTitle: string | null;
}) {
  const title = meeting.title_override ?? templateTitle ?? "Meeting";
  return (
    <Link to={`/meetings/${meeting.meeting_id}`} className="block">
      <Card className="p-4 transition-colors hover:bg-accent">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium leading-tight">{title}</h3>
          <StatusBadge status={meeting.status} />
        </div>
        {templateTitle && meeting.title_override && (
          <p className="mt-1 text-xs text-muted-foreground">
            from {templateTitle}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{meeting.target_minutes} min</span>
          <span aria-hidden>·</span>
          <span>
            {relativeTime(meeting.ended_at ?? meeting.created_at)}
          </span>
        </div>
      </Card>
    </Link>
  );
}
