import { useCallback, useEffect, useState } from "react";
import { getMeeting } from "@/lib/api";
import type { MeetingRecord } from "@/types";
import { usePolling } from "./usePolling";

/**
 * Loads one meeting. Polls every 3s only while the template is generating or
 * the meeting is running — i.e. exactly the states the UI is waiting on.
 * While a meeting is `planned` + `ready`, polling is off so it never clobbers
 * the user's in-progress edits.
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
    meeting?.template_status === "generating" || meeting?.status === "running";
  usePolling(refresh, 3000, polling);

  return { meeting, error, loaded, refresh };
}
