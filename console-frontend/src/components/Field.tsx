import * as React from "react";
import { InfoTooltip } from "@ig/ui";

/** Labelled form field: `text-sm font-medium` label, the control, optional hint. */
export function Field({
  label,
  hint,
  info,
  children,
}: {
  label: string;
  hint?: string;
  /** Optional info tooltip rendered next to the label. */
  info?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <label className="text-sm font-medium">{label}</label>
        {info != null && <InfoTooltip size="sm" content={info} />}
      </div>
      {children}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
