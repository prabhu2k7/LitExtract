import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import UploadPage from "./pages/UploadPage";
import ResultsPage from "./pages/ResultsPage";
import HistoryPage from "./pages/HistoryPage";
import BiomarkersPage from "./pages/BiomarkersPage";
import ValidationPage from "./pages/ValidationPage";
import SettingsPage from "./pages/SettingsPage";
import AboutPage from "./pages/AboutPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/upload" replace />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/results/:paperId" element={<ResultsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/biomarkers" element={<BiomarkersPage />} />
        <Route path="/validation" element={<ValidationPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/upload" replace />} />
      </Routes>
    </Layout>
  );
}
