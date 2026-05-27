import { useCallback, useEffect, useState } from "react";
import { getTemplate } from "@/lib/api";
import type { TemplateRecord } from "@/types";
import { usePolling } from "./usePolling";

/**
 * Loads one template. Polls every 3s only while `template_status` is
 * `generating` — i.e. exactly the state the UI is waiting on. While the
 * template is `ready`, polling is off so it never clobbers the user's
 * in-progress edits.
 */
export function useTemplate(id: string | undefined) {
  const [template, setTemplate] = useState<TemplateRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      setTemplate(await getTemplate(id));
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

  const polling = template?.template_status === "generating";
  usePolling(refresh, 3000, polling);

  return { template, error, loaded, refresh };
}
