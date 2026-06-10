export function formatElapsed(startedAt: string, now: number = Date.now()): string {
  const started = new Date(startedAt).getTime();
  const seconds = Math.max(0, Math.floor((now - started) / 1000));
  const mm = Math.floor(seconds / 60);
  const ss = seconds % 60;
  return `${mm}:${ss.toString().padStart(2, "0")}`;
}

export function elapsedFraction(
  startedAt: string,
  targetMinutes: number,
  now: number = Date.now(),
): number {
  const started = new Date(startedAt).getTime();
  const elapsedMs = Math.max(0, now - started);
  const targetMs = targetMinutes * 60 * 1000;
  if (targetMs <= 0) return 0;
  return Math.min(1, elapsedMs / targetMs);
}

export function relativeTime(ts: string, now: number = Date.now()): string {
  const then = new Date(ts).getTime();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const minutes = Math.floor(diffSec / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(ts).toLocaleString();
}
