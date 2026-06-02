import { useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Footer,
  Header,
} from "@ig/ui";
import { CircleUser, LogOut } from "lucide-react";
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
    <div className="flex min-h-screen flex-col">
      <Header>
        <Link to="/" className="text-sm font-semibold tracking-tight">
          Information Gathering
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Account">
              <CircleUser className="size-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel className="font-normal text-muted-foreground">
              {auth.email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => window.location.assign("/cdn-cgi/access/logout")}
            >
              <LogOut />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </Header>
      <main className="flex-1">{children}</main>
      <Footer>
        <span>flomoo-ai</span>
        <span>© {new Date().getFullYear()}</span>
      </Footer>
    </div>
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
