import { Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "@/pages/Dashboard";
import { NewTemplate } from "@/pages/NewTemplate";
import { TemplateDetail } from "@/pages/TemplateDetail";
import { MeetingDetail } from "@/pages/MeetingDetail";

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/templates/new" element={<NewTemplate />} />
        <Route path="/templates/:id" element={<TemplateDetail />} />
        <Route path="/meetings/:id" element={<MeetingDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
