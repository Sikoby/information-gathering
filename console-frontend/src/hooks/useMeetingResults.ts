import { useEffect, useState } from "react";
import { getMeetingResults } from "@/lib/api";
import type { MeetingResults } from "@/types";

/**
 * Loads the flushed artifacts of a finished meeting. Fetches once when
 * `enabled` flips true — a done meeting is immutable, so no polling.
 */
export function useMeetingResults(id: string | undefined, enabled: boolean) {
  const [results, setResults] = useState<MeetingResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !enabled || results) return;
    let cancelled = false;
    getMeetingResults(id)
      .then((r) => {
        if (!cancelled) setResults(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [id, enabled, results]);

  return { results, error };
}
