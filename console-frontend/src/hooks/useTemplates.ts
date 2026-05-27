import { useCallback, useEffect, useState } from "react";
import { listTemplates } from "@/lib/api";
import type { TemplateRecord } from "@/types";
import { usePolling } from "./usePolling";

/** Loads the full template list and polls it every 5s for the dashboard. */
export function useTemplates() {
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listTemplates();
      setTemplates(data.templates);
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

  return { templates, error, loaded, refresh };
}
