import { useEffect } from "react";

/** Call `fn` every `intervalMs` while `enabled`. `fn` should be stable. */
export function usePolling(
  fn: () => void,
  intervalMs: number,
  enabled: boolean,
): void {
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(fn, intervalMs);
    return () => window.clearInterval(id);
  }, [fn, intervalMs, enabled]);
}
