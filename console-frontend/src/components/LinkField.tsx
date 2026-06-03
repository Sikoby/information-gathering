import { Input } from "@ig/ui";
import { ExternalLink } from "lucide-react";
import { Field } from "@/components/Field";
import { CopyButton } from "@/components/CopyButton";
import { IconButton } from "@/components/IconButton";

/** A read-only link with copy + open-in-new-tab actions. */
export function LinkField({
  label,
  hint,
  url,
}: {
  label: string;
  hint?: string;
  url: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="mt-1 flex gap-2">
        <Input
          readOnly
          value={url}
          className="flex-1"
          onFocus={(e) => e.currentTarget.select()}
        />
        <CopyButton value={url} label="Copy link" />
        <IconButton asChild variant="outline" label="Open in new tab">
          <a href={url} target="_blank" rel="noreferrer">
            <ExternalLink />
          </a>
        </IconButton>
      </div>
    </Field>
  );
}
