import { Route, Routes } from "react-router-dom";
import { LiveView } from "@/components/LiveView";
import { JoinPage } from "@/join/JoinPage";

function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center p-8 text-sm text-muted-foreground">
      Nothing here. Use a meeting link to view a live meeting or join one.
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/join/:meetingId" element={<JoinPage />} />
      <Route path="/:runId" element={<LiveView />} />
      <Route path="/:runId/*" element={<LiveView />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
