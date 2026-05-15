const H1_RE = /^\s*#\s+(.+?)\s*$/m;
const BRIEFING_PREFIX_RE = /^briefing\s*:\s*/i;

export function extractMeetingTitle(
  briefingMarkdown: string,
  fallback = "Meeting",
): string {
  const stripped = briefingMarkdown.replace(/^---\s*\n[\s\S]*?\n---\s*\n/, "");
  const match = stripped.match(H1_RE);
  if (!match) return fallback;
  return match[1].replace(BRIEFING_PREFIX_RE, "").trim() || fallback;
}
