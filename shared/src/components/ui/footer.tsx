import * as React from "react";
import { cn } from "../../lib/utils";

const Footer = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <footer
      ref={ref}
      className={cn("w-full border-t bg-background", className)}
      {...props}
    >
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-6 py-6 text-sm text-muted-foreground sm:flex-row">
        {children}
      </div>
    </footer>
  ),
);
Footer.displayName = "Footer";

export { Footer };
