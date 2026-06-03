import { Check, Loader2, X, type LucideIcon } from "lucide-react";
import { cn } from "@ig/ui";
import type { TemplateStatus } from "@/types";

const CONFIG: Record<
  TemplateStatus,
  { label: string; tone: string; Icon: LucideIcon; strokeWidth: number; spin?: boolean }
> = {
  ready: {
    label: "Ready",
    tone: "bg-success text-success-foreground",
    Icon: Check,
    strokeWidth: 3,
  },
  generating: {
    label: "Generating",
    tone: "bg-warning text-warning-foreground",
    Icon: Loader2,
    strokeWidth: 2.5,
    spin: true,
  },
  failed: {
    label: "Failed",
    tone: "bg-destructive text-destructive-foreground",
    Icon: X,
    strokeWidth: 3,
  },
};

export function TemplateStatusIndicator({
  status,
  className,
}: {
  status: TemplateStatus;
  className?: string;
}) {
  const { label, tone, Icon, strokeWidth, spin } = CONFIG[status];
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
        tone,
        className,
      )}
    >
      <Icon className={cn("h-3 w-3", spin && "animate-spin")} strokeWidth={strokeWidth} />
    </span>
  );
}
