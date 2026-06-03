import { useState } from "react";
import { Button } from "@ig/ui";
import { Check, Copy } from "lucide-react";

/** Copies `value` to the clipboard and flips the label to "Copied" briefly. */
export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API is unavailable in insecure contexts — leave the field
      // selectable so the user can copy manually.
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={onCopy}
      className={className}
    >
      {copied ? <Check /> : <Copy />}
      {copied ? "Copied" : label}
    </Button>
  );
}
