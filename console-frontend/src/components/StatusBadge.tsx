import { Badge } from "@ig/ui";
import type { MeetingStatus, TemplateStatus } from "@/types";

export function StatusBadge({ status }: { status: MeetingStatus }) {
  const variant =
    status === "running"
      ? "default"
      : status === "done"
        ? "secondary"
        : "outline";
  return (
    <Badge variant={variant}>{status}</Badge>
  );
}

export function TemplateStatusBadge({ status }: { status: TemplateStatus }) {
  const map = {
    generating: { variant: "warning" as const, label: "generating template" },
    ready: { variant: "success" as const, label: "template ready" },
    failed: { variant: "destructive" as const, label: "template failed" },
  };
  const { variant, label } = map[status];
  return <Badge variant={variant}>{label}</Badge>;
}
