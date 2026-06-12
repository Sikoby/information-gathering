import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  CalendarPlus,
  Download,
  ExternalLink,
  Trash2,
  Video,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@ig/ui";
import { useMeeting } from "@/hooks/useMeeting";
import { useMeetingResults } from "@/hooks/useMeetingResults";
import { useTemplate } from "@/hooks/useTemplate";
import {
  deleteMeeting,
  meetingAnswersXlsxUrl,
  meetingInviteIcsUrl,
} from "@/lib/api";
import { CopyButton } from "@/components/CopyButton";
import { MeetingResultsPanels } from "@/components/MeetingResults";
import { StatusBadge } from "@/components/StatusBadge";
import { TemplateStatusIndicator } from "@/components/TemplateStatusIndicator";
import { InviteesList } from "@/components/InviteesList";
import { Page, PageHeader, CenteredMessage } from "@/components/Page";
import { IconButton } from "@/components/IconButton";
import { formatDateTime } from "@/lib/format";
import type { MeetingRecord, MeetingResults } from "@/types";

export function MeetingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { meeting, error, loaded } = useMeeting(id);
  const { template } = useTemplate(meeting?.template_id);
  const { results } = useMeetingResults(id, meeting?.status === "done");

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!loaded) return <CenteredMessage>Loading…</CenteredMessage>;
  if (!meeting || error)
    return <CenteredMessage>{error ?? "Meeting not found."}</CenteredMessage>;

  const onDelete = async () => {
    setBusy("delete");
    setActionError(null);
    try {
      await deleteMeeting(meeting.meeting_id);
      navigate("/");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

  const displayTitle = meeting.title_override ?? template?.title ?? "Meeting";

  return (
    <Page>
      <PageHeader
        back
        title={displayTitle}
        badge={
          meeting.status === "scheduled" ? (
            <TemplateStatusIndicator status="scheduled" />
          ) : (
            <StatusBadge status={meeting.status} />
          )
        }
      />

      {actionError && (
        <p className="mb-3 text-sm text-destructive">{actionError}</p>
      )}

      <MeetingView
        meeting={meeting}
        templateTitle={template?.title ?? null}
        results={results}
        busy={busy}
        onDelete={meeting.status !== "running" ? onDelete : undefined}
      />
    </Page>
  );
}

function MeetingView({
  meeting,
  templateTitle,
  results,
  busy,
  onDelete,
}: {
  meeting: MeetingRecord;
  templateTitle: string | null;
  results: MeetingResults | null;
  busy: string | null;
  onDelete?: () => void;
}) {
  const scheduled = meeting.status === "scheduled";
  return (
    <div className="space-y-5">
      {scheduled && (
        <Alert>
          <AlertTitle>Meeting scheduled</AlertTitle>
          <AlertDescription>
            {meeting.scheduled_at
              ? `Starts ${formatDateTime(meeting.scheduled_at)}. `
              : ""}
            It starts automatically at that time.
          </AlertDescription>
        </Alert>
      )}
      {meeting.status === "running" && (
        <Alert>
          <AlertTitle>Meeting in progress</AlertTitle>
          <AlertDescription>
            This meeting is running. Open the live view to watch it unfold.
          </AlertDescription>
        </Alert>
      )}
      {meeting.status === "done" && (
        <Alert variant="success">
          <AlertTitle>Meeting finished</AlertTitle>
          <AlertDescription>
            Ended{meeting.end_reason ? ` — ${meeting.end_reason}` : ""}.
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-2">
        {scheduled && (
          <IconButton asChild label="Add to calendar (.ics)">
            <a href={meetingInviteIcsUrl(meeting.meeting_id)} download>
              <CalendarPlus />
            </a>
          </IconButton>
        )}
        {meeting.status === "running" && meeting.join_url && (
          <>
            <IconButton asChild label="Join meeting">
              <a href={meeting.join_url} target="_blank" rel="noreferrer">
                <Video />
              </a>
            </IconButton>
            <CopyButton value={meeting.join_url} label="Copy join link" />
          </>
        )}
        {meeting.status === "done" && (results?.sections?.length ?? 0) > 0 && (
          <IconButton asChild label="Download answers (.xlsx)">
            <a href={meetingAnswersXlsxUrl(meeting.meeting_id)} download>
              <Download />
            </a>
          </IconButton>
        )}
        {!scheduled && meeting.live_view_url && (
          <IconButton variant="outline" asChild label="Open live view">
            <a href={meeting.live_view_url} target="_blank" rel="noreferrer">
              <ExternalLink />
            </a>
          </IconButton>
        )}
        {meeting.live_view_url && (
          <CopyButton value={meeting.live_view_url} label="Copy live link" />
        )}
        {onDelete && (
          <IconButton
            variant="ghost"
            onClick={onDelete}
            disabled={busy !== null}
            className="ml-auto text-destructive"
            label="Delete meeting"
          >
            <Trash2 />
          </IconButton>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
        {scheduled && meeting.scheduled_at && (
          <Info label="Start time" value={formatDateTime(meeting.scheduled_at)} />
        )}
        <Info label="Duration" value={`${meeting.target_minutes} min`} />
        <Info
          label="Source template"
          value={templateTitle ?? "—"}
          to={`/templates/${meeting.template_id}`}
        />
      </dl>

      {scheduled && <InviteesList emails={meeting.invitees} />}

      {meeting.status === "done" && results && (
        <MeetingResultsPanels results={results} />
      )}
    </div>
  );
}

function Info({
  label,
  value,
  to,
}: {
  label: string;
  value: string;
  to?: string;
}) {
  const inner = (
    <>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-xs" title={value}>
        {value}
      </dd>
    </>
  );
  return to ? (
    <Link to={to} className="block rounded-md border p-2 hover:bg-accent">
      {inner}
    </Link>
  ) : (
    <div className="rounded-md border p-2">{inner}</div>
  );
}
