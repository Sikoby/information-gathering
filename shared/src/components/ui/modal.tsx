import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";

export interface ModalProps {
  /** Controlled visibility. */
  open: boolean;
  /** Called on overlay click, Escape, or the corner close button. */
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Optional body, rendered below the description. */
  children?: React.ReactNode;
  /** Optional action row, right-aligned at the bottom. */
  footer?: React.ReactNode;
  /** Extra classes on the dialog panel (e.g. a wider max-width). */
  className?: string;
}

/**
 * Dependency-free centered modal dialog rendered into a portal. Closes on
 * overlay click, Escape, or the corner button; locks body scroll while open.
 * Generic on purpose — callers supply their own title, body, and footer
 * actions so it can back error popups, confirmations, etc.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}: ModalProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="absolute inset-0 bg-black/50 animate-in fade-in"
        onClick={onClose}
      />
      <div
        className={cn(
          "animate-in fade-in zoom-in-95 relative z-10 w-full max-w-md rounded-lg border bg-background p-6 shadow-lg",
          className,
        )}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          title="Close"
          className="absolute right-4 top-4 rounded-sm text-muted-foreground transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-4 w-4" />
        </button>
        {title && (
          <h2 className="pr-6 text-lg font-semibold tracking-tight">{title}</h2>
        )}
        {description && (
          <div className="mt-1.5 text-sm text-muted-foreground">
            {description}
          </div>
        )}
        {children && <div className="mt-4">{children}</div>}
        {footer && (
          <div className="mt-6 flex items-center justify-end gap-2">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  );
}
