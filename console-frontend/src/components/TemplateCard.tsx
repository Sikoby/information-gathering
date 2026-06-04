import { Link } from "react-router-dom";
import { Card } from "@ig/ui";
import { FileText } from "lucide-react";
import type { TemplateRecord } from "@/types";
import { relativeTime } from "@/lib/format";
import { TemplateStatusIndicator } from "./TemplateStatusIndicator";

export function TemplateCard({ template }: { template: TemplateRecord }) {
  return (
    <Link to={`/templates/${template.template_id}`} className="block">
      <Card className="p-4 transition-colors hover:bg-accent">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium leading-tight">{template.title}</h3>
          <TemplateStatusIndicator status={template.template_status} />
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
          {template.source_prompt}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {template.document_filename && (
            <span className="inline-flex items-center gap-1">
              <FileText className="h-3 w-3" />
              {template.document_filename}
            </span>
          )}
          <span>{template.default_target_minutes} min</span>
          <span aria-hidden>·</span>
          <span>{relativeTime(template.created_at)}</span>
        </div>
      </Card>
    </Link>
  );
}
