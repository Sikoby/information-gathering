import { Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "@/pages/Dashboard";
import { NewMeeting } from "@/pages/NewMeeting";
import { MeetingDetail } from "@/pages/MeetingDetail";

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewMeeting />} />
        <Route path="/meetings/:id" element={<MeetingDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
