import { Check } from "lucide-react";
import { cn } from "@ig/ui";

export function ReadyIndicator({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="Ready"
      title="Ready"
      className={cn(
        "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground",
        className,
      )}
    >
      <Check className="h-3 w-3" strokeWidth={3} />
    </span>
  );
}
