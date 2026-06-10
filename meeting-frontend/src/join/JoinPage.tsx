import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
} from "@ig/ui";

type JoinStatus = {
  status: "scheduled" | "running" | "done" | "not_found" | null;
  scheduled_at: string | null;
  ready: boolean;
};

type Phase = "loading" | "error" | "ready";

function formatWhen(iso: string | null): string {
  if (!iso) return "the scheduled time";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          {children}
        </CardContent>
      </Card>
    </div>
  );
}

export function JoinPage() {
  const { meetingId = "" } = useParams();
  const [info, setInfo] = useState<JoinStatus | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!meetingId) return;
    let cancelled = false;
    fetch(`/api/join/${meetingId}`)
      .then(async (r) => {
        const data = (await r.json()) as JoinStatus;
        if (!r.ok) return { ...data, status: data.status ?? "not_found" } as JoinStatus;
        return data;
      })
      .then((data) => {
        if (cancelled) return;
        setInfo(data);
        setPhase("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [meetingId]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const r = await fetch(`/api/join/${meetingId}/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pin.trim() }),
      });
      const data = (await r.json()) as { join_url?: string; error?: string };
      if (r.ok && data.join_url) {
        window.location.assign(data.join_url);
        return;
      }
      setError(data.error ?? "Couldn't join the meeting. Please try again.");
    } catch {
      setError("Couldn't reach the meeting service. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "loading") {
    return <Shell title="Loading…">Checking the meeting status…</Shell>;
  }

  if (phase === "error" || info === null) {
    return (
      <Shell title="Something went wrong">
        We couldn't load this meeting. Please refresh and try again.
      </Shell>
    );
  }

  if (info.status === "not_found") {
    return <Shell title="Meeting not found">This join link isn't valid.</Shell>;
  }

  if (!info.ready) {
    if (info.status === "done") {
      return <Shell title="Meeting ended">This meeting has already finished.</Shell>;
    }
    return (
      <Shell title="Not started yet">
        <p>
          This meeting starts at{" "}
          <strong className="text-foreground">{formatWhen(info.scheduled_at)}</strong>.
          Open this link again at the start time to join.
        </p>
      </Shell>
    );
  }

  return (
    <Shell title="Join the meeting">
      <p>Enter the PIN from your invitation to enter the room.</p>
      <form onSubmit={onSubmit} className="space-y-4">
        <Input
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          inputMode="numeric"
          autoComplete="off"
          autoFocus
          maxLength={6}
          placeholder="••••••"
          className="text-center text-2xl tracking-[0.3em]"
        />
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" className="w-full" disabled={submitting || !pin.trim()}>
          {submitting ? "Joining…" : "Join"}
        </Button>
      </form>
    </Shell>
  );
}
