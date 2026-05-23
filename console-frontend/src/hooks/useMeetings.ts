import { useCallback, useEffect, useState } from "react";
import { listMeetings } from "@/lib/api";
import type { MeetingRecord } from "@/types";
import { usePolling } from "./usePolling";

/** Loads the full meeting list and polls it every 5s for the dashboard. */
export function useMeetings() {
  const [meetings, setMeetings] = useState<MeetingRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listMeetings();
      setMeetings(data.meetings);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);
  usePolling(refresh, 5000, true);

  return { meetings, error, loaded, refresh };
}
