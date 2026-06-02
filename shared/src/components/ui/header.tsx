import * as React from "react";
import { cn } from "../../lib/utils";

const Header = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <header
      ref={ref}
      className={cn(
        "sticky top-0 z-40 w-full border-b bg-background",
        className,
      )}
      {...props}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-6">
        {children}
      </div>
    </header>
  ),
);
Header.displayName = "Header";

export { Header };
