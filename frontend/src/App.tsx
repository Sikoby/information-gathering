import { useMemo } from "react";
import { Agenda } from "@/components/Agenda";
import { Breadcrumb } from "@/components/Breadcrumb";
import { Briefing } from "@/components/Briefing";
import { Followups } from "@/components/Followups";
import { Header } from "@/components/Header";
import { Notebook } from "@/components/Notebook";
import { Sidebar } from "@/components/Sidebar";
import { TransitionLog } from "@/components/TransitionLog";
import { Separator } from "@/components/ui/separator";
import { useSnapshot } from "@/hooks/useSnapshot";

function getRunId(): string {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] ?? "";
}

export default function App() {
  const runId = useMemo(getRunId, []);
  const { state, status } = useSnapshot(runId);

  if (!runId) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        Missing <code>run_id</code> in URL. Expected{" "}
        <code>/&lt;run_id&gt;/</code>.
      </div>
    );
  }

  if (!state) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        {status === "error"
          ? "Couldn't connect to meeting stream. Retrying…"
          : "Connecting to meeting…"}
      </div>
    );
  }

  const isDebug = new URLSearchParams(window.location.search).has("debug");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header state={state} />
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="grid gap-8 md:grid-cols-[12rem_1fr]">
          <Sidebar state={state} />
          <main className="min-w-0 space-y-10">
            <Breadcrumb state={state} />
            <Separator />
            <Agenda state={state} />
            <Separator />
            <Notebook state={state} />
            <Separator />
            <TransitionLog state={state} />
            <Separator />
            <Followups state={state} />
            <Separator />
            <Briefing state={state} />
          </main>
        </div>
        {isDebug && (
          <details className="mt-10 rounded-md border bg-muted p-3 text-xs">
            <summary className="cursor-pointer font-semibold">Debug: raw snapshot</summary>
            <pre className="mt-2 overflow-x-auto">{JSON.stringify(state, null, 2)}</pre>
          </details>
        )}
      </div>
    </div>
  );
}
