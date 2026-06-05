import * as React from "react";
import { Loader2 } from "lucide-react";
import { Button, type ButtonProps } from "@ig/ui";

export interface StartButtonProps extends Omit<ButtonProps, "children"> {
  /** While true the button reads "Starting…", shows a spinner, and is disabled. */
  busy?: boolean;
}

/**
 * The primary "Start a meeting" action as a text button. Defaults to the
 * shared Button's `h-9` height so it lines up with the icon buttons beside it.
 */
export const StartButton = React.forwardRef<HTMLButtonElement, StartButtonProps>(
  ({ busy = false, disabled, type, ...props }, ref) => (
    <Button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || busy}
      {...props}
    >
      {busy && <Loader2 className="animate-spin" />}
      {busy ? "Starting…" : "Start"}
    </Button>
  ),
);
StartButton.displayName = "StartButton";
