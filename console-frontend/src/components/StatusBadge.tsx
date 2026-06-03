import { Badge } from "@ig/ui";
import type { MeetingStatus, TemplateStatus } from "@/types";
import { ReadyIndicator } from "./ReadyIndicator";

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
  if (status === "ready") return <ReadyIndicator />;
  const map = {
    generating: { variant: "warning" as const, label: "generating" },
    failed: { variant: "destructive" as const, label: "failed" },
  };
  const { variant, label } = map[status];
  return <Badge variant={variant}>{label}</Badge>;
}
