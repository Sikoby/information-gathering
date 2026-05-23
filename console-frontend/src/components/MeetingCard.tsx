import { Link } from "react-router-dom";
import { Card } from "@ig/ui";
import type { MeetingRecord } from "@/types";
import { relativeTime } from "@/lib/format";
import { StatusBadge, TemplateStatusBadge } from "./StatusBadge";

export function MeetingCard({ meeting }: { meeting: MeetingRecord }) {
  return (
    <Link to={`/meetings/${meeting.meeting_id}`} className="block">
      <Card className="p-4 transition-colors hover:bg-accent">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium leading-tight">{meeting.title}</h3>
          <StatusBadge status={meeting.status} />
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
          {meeting.prompt}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {meeting.status === "planned" && (
            <TemplateStatusBadge status={meeting.template_status} />
          )}
          <span>{meeting.target_minutes} min</span>
          <span aria-hidden>·</span>
          <span>{relativeTime(meeting.created_at)}</span>
        </div>
      </Card>
    </Link>
  );
}
