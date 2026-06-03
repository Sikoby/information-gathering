import { Badge } from "@ig/ui";
import type { MeetingStatus } from "@/types";

export function StatusBadge({ status }: { status: MeetingStatus }) {
  const variant =
    status === "running"
      ? "default"
      : status === "scheduled"
        ? "outline"
        : "secondary";
  return <Badge variant={variant}>{status}</Badge>;
}
