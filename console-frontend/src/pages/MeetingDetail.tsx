import { type ReactNode, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, AlertDescription, AlertTitle, Button } from "@ig/ui";
import { useMeeting } from "@/hooks/useMeeting";
import { useTemplate } from "@/hooks/useTemplate";
import { deleteMeeting, meetingInviteIcsUrl } from "@/lib/api";
import { CopyButton } from "@/components/CopyButton";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDateTime } from "@/lib/format";
import type { MeetingRecord } from "@/types";

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

export function MeetingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { meeting, error, loaded } = useMeeting(id);
  const { template } = useTemplate(meeting?.template_id);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!loaded) return <Centered>Loading…</Centered>;
  if (!meeting || error)
    return <Centered>{error ?? "Meeting not found."}</Centered>;

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

  const displayTitle =
    meeting.title_override ?? template?.title ?? "Meeting";

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <Link
        to="/"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back
      </Link>
      <div className="mt-2 flex items-start justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{displayTitle}</h1>
        <StatusBadge status={meeting.status} />
      </div>

      {actionError && (
        <p className="mt-3 text-sm text-destructive">{actionError}</p>
      )}

      <MeetingView
        meeting={meeting}
        templateTitle={template?.title ?? null}
        busy={busy}
        onDelete={meeting.status !== "running" ? onDelete : undefined}
      />
    </div>
  );
}

function MeetingView({
  meeting,
  templateTitle,
  busy,
  onDelete,
}: {
  meeting: MeetingRecord;
  templateTitle: string | null;
  busy: string | null;
  onDelete?: () => void;
}) {
  const scheduled = meeting.status === "scheduled";
  return (
    <div className="mt-6 space-y-5">
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
          <Button asChild>
            <a href={meetingInviteIcsUrl(meeting.meeting_id)} download>
              Add to calendar (.ics)
            </a>
          </Button>
        )}
        {meeting.status === "running" && meeting.join_url && (
          <>
            <Button asChild>
              <a href={meeting.join_url} target="_blank" rel="noreferrer">
                Join meeting
              </a>
            </Button>
            <CopyButton value={meeting.join_url} label="Copy join link" />
          </>
        )}
        {!scheduled && meeting.webapp_url && (
          <Button variant="outline" asChild>
            <a href={meeting.webapp_url} target="_blank" rel="noreferrer">
              Open live view
            </a>
          </Button>
        )}
        {meeting.webapp_url && (
          <CopyButton value={meeting.webapp_url} label="Copy live link" />
        )}
        {onDelete && (
          <Button
            variant="ghost"
            onClick={onDelete}
            disabled={busy !== null}
            className="ml-auto text-destructive"
          >
            Delete
          </Button>
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

      {scheduled && meeting.invitees.length > 0 && (
        <div>
          <p className="text-sm font-medium">
            Invitees ({meeting.invitees.length})
          </p>
          <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
            {meeting.invitees.map((email) => (
              <li key={email}>{email}</li>
            ))}
          </ul>
        </div>
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
