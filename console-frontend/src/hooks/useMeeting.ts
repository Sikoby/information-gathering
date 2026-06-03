import { useCallback, useEffect, useState } from "react";
import { getMeeting } from "@/lib/api";
import type { MeetingRecord } from "@/types";
import { usePolling } from "./usePolling";

/**
 * Loads one meeting. Polls every 3s while the meeting is `scheduled` or
 * `running` — the states the UI is waiting on (a scheduled meeting flips to
 * running when deferred dispatch fires). Once the meeting is `done` we stop.
 */
export function useMeeting(id: string | undefined) {
  const [meeting, setMeeting] = useState<MeetingRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      setMeeting(await getMeeting(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoaded(true);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const polling =
    meeting?.status === "running" || meeting?.status === "scheduled";
  usePolling(refresh, 3000, polling);

  return { meeting, error, loaded, refresh };
}
