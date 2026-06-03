import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { InfoTooltip, cn } from "@ig/ui";
import { IconButton } from "@/components/IconButton";

/**
 * Outer page container. `max-w-6xl px-6` matches the shared Header/Footer so
 * every page's left/right edges line up with the brand and account menu.
 */
export function Page({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("mx-auto max-w-6xl px-6 py-8", className)}>{children}</div>
  );
}

/** Icon-only back-arrow to the dashboard. Top-left of every non-dashboard page. */
export function BackLink() {
  return (
    <IconButton asChild variant="ghost" label="Back" className="-ml-2">
      <Link to="/">
        <ArrowLeft />
      </Link>
    </IconButton>
  );
}

export interface PageHeaderProps {
  title: string;
  /** Status badge rendered at the top-right of the title row. */
  badge?: React.ReactNode;
  /** InfoTooltip content shown next to the title. */
  info?: React.ReactNode;
  /** Render a BackLink above the title. */
  back?: boolean;
}

/** The title row shared by every page: optional back-link, h1, badge, info. */
export function PageHeader({ title, badge, info, back }: PageHeaderProps) {
  return (
    <div className="mb-8">
      {back && <BackLink />}
      <div className={cn("flex items-start justify-between gap-3", back && "mt-2")}>
        <div className="flex items-center gap-1.5">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {info != null && <InfoTooltip size="lg" content={info} />}
        </div>
        {badge}
      </div>
    </div>
  );
}

/** Full-page centered status line (loading / not-found / error). */
export function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-6xl px-6 py-16 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}
