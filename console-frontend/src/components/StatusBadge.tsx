import { Badge } from "@ig/ui";
import type { MeetingStatus, TemplateStatus } from "@/types";

export function StatusBadge({ status }: { status: MeetingStatus }) {
  const variant =
    status === "running"
      ? "default"
      : status === "scheduled"
        ? "outline"
        : "secondary";
  return <Badge variant={variant}>{status}</Badge>;
}

export function TemplateStatusBadge({ status }: { status: TemplateStatus }) {
  const map = {
    generating: { variant: "warning" as const, label: "generating" },
    ready: { variant: "success" as const, label: "ready" },
    failed: { variant: "destructive" as const, label: "failed" },
  };
  const { variant, label } = map[status];
  return <Badge variant={variant}>{label}</Badge>;
}
