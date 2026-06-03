import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { IconButton } from "@/components/IconButton";

/** Copies `value` to the clipboard; the icon flips to a check briefly. */
export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string;
  /** Tooltip / accessible name for the action. */
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
    <IconButton
      variant="outline"
      label={copied ? "Copied" : label}
      onClick={onCopy}
      className={className}
    >
      {copied ? <Check /> : <Copy />}
    </IconButton>
  );
}
