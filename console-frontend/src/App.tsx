import { useState, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@ig/ui";
import { useAuth } from "@/hooks/useAuth";
import { Dashboard } from "@/pages/Dashboard";
import { NewTemplate } from "@/pages/NewTemplate";
import { TemplateDetail } from "@/pages/TemplateDetail";
import { MeetingDetail } from "@/pages/MeetingDetail";
import { Welcome } from "@/pages/Welcome";

function RootRedirect() {
  const [dismissed] = useState(
    () => sessionStorage.getItem("welcome:dismissed") === "1",
  );
  return dismissed ? <Dashboard /> : <Navigate to="/welcome" replace />;
}

function AuthMessage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-6">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {children}
        </CardContent>
      </Card>
    </div>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();

  if (auth.status === "loading") {
    return null;
  }
  if (auth.status === "unauthenticated") {
    return (
      <AuthMessage title="Sign in required">
        The console is gated by Cloudflare Access. Sign in via Cloudflare to
        continue. If you are developing locally, set the
        {" "}<code className="rounded bg-muted px-1">CONSOLE_DEV_USER_EMAIL</code>
        {" "}env var on the console service.
      </AuthMessage>
    );
  }
  if (auth.status === "error") {
    return (
      <AuthMessage title="Couldn't reach the console">
        {auth.message}
      </AuthMessage>
    );
  }

  return (
    <>
      <div className="pointer-events-none fixed right-4 top-3 z-50 text-xs text-muted-foreground">
        signed in as {auth.email}
      </div>
      {children}
    </>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AuthGate>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/welcome" element={<Welcome />} />
          <Route path="/templates/new" element={<NewTemplate />} />
          <Route path="/templates/:id" element={<TemplateDetail />} />
          <Route path="/meetings/:id" element={<MeetingDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthGate>
    </div>
  );
}
