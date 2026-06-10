import { useEffect, useState } from "react";
import type { MeetingState } from "@/types";

export type SnapshotStatus = "connecting" | "open" | "error";

export function useSnapshot(runId: string): {
  state: MeetingState | null;
  status: SnapshotStatus;
} {
  const [state, setState] = useState<MeetingState | null>(null);
  const [status, setStatus] = useState<SnapshotStatus>("connecting");

  useEffect(() => {
    if (!runId) return;

    // Initial fetch so the UI renders something even if SSE is slow to open.
    let cancelled = false;
    fetch(`/api/runs/${runId}/state`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((data) => {
        if (!cancelled) setState(data as MeetingState);
      })
      .catch(() => {
        /* swallow — SSE will retry */
      });

    const es = new EventSource(`/api/runs/${runId}/events`);
    es.onopen = () => setStatus("open");
    es.onerror = () => setStatus("error");
    es.onmessage = (ev) => {
      try {
        const snap = JSON.parse(ev.data) as MeetingState;
        setState(snap);
        setStatus("open");
      } catch (e) {
        console.error("failed to parse snapshot", e);
      }
    };

    return () => {
      cancelled = true;
      es.close();
    };
  }, [runId]);

  return { state, status };
}
