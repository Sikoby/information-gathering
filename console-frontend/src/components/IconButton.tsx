import * as React from "react";
import { Button, type ButtonProps, cn } from "@ig/ui";

export interface IconButtonProps extends Omit<ButtonProps, "size" | "aria-label"> {
  /** Required: used as both the accessible name and the hover tooltip. */
  label: string;
  /** "default" → h-9 w-9 (page action bars); "sm" → h-8 w-8 (dense rows). */
  size?: "default" | "sm";
}

/**
 * The console's only button. Square, icon-only, with the action exposed as
 * `aria-label` + native `title` (hover tooltip) so it stays discoverable
 * without visible text. Children must be exactly one lucide icon.
 */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ label, size = "default", className, type, asChild, ...props }, ref) => (
    <Button
      ref={ref}
      asChild={asChild}
      type={asChild ? type : (type ?? "button")}
      size="icon"
      aria-label={label}
      title={label}
      className={cn(
        size === "sm" ? "h-8 w-8 [&_svg]:size-3.5" : "h-9 w-9",
        className,
      )}
      {...props}
    />
  ),
);
IconButton.displayName = "IconButton";
