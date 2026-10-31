import type { ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, ProtectedRoute } from "./auth";
import Layout from "./components/Layout";
import AdminOverview from "./pages/admin/AdminOverview";
import AuditPage from "./pages/admin/AuditPage";
import HandoffsPage from "./pages/admin/HandoffsPage";
import SelectionPage from "./pages/admin/SelectionPage";
import UsersPage from "./pages/admin/UsersPage";
import DetectPage from "./pages/expert/DetectPage";
import ExercisePage from "./pages/expert/ExercisePage";
import ExpertHome from "./pages/expert/ExpertHome";
import FindingPage from "./pages/expert/FindingPage";
import HomeRedirect from "./pages/HomeRedirect";
import LearnExercisePage from "./pages/learn/LearnExercisePage";
import LearnHome from "./pages/learn/LearnHome";
import LibraryPage from "./pages/LibraryPage";
import LoginPage from "./pages/LoginPage";
import { ForbiddenPage, NotFoundPage } from "./pages/StatusPages";
import type { Role } from "./types";

// Route guards only shape navigation. The backend decides every permission again.
const only = (roles: Role[], page: ReactNode) => <ProtectedRoute roles={roles}>{page}</ProtectedRoute>;

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route path="admin" element={only(["admin"], <AdminOverview />)} />
        <Route path="admin/users" element={only(["admin"], <UsersPage />)} />
        <Route path="admin/handoffs" element={only(["admin"], <HandoffsPage />)} />
        <Route path="admin/handoffs/:id" element={only(["admin"], <SelectionPage />)} />
        <Route path="admin/audit" element={only(["admin"], <AuditPage />)} />
        <Route path="expert" element={only(["member"], <ExpertHome />)} />
        {/* Admins may read Detect results after running an analysis; they cannot capture. */}
        <Route path="expert/handoffs/:id/detect" element={only(["member", "admin"], <DetectPage />)} />
        <Route path="expert/findings/:id" element={only(["member"], <FindingPage />)} />
        <Route path="expert/knowledge/:id/exercise" element={only(["member"], <ExercisePage />)} />
        <Route path="learn" element={only(["member"], <LearnHome />)} />
        <Route path="learn/exercises/:id" element={only(["member"], <LearnExercisePage />)} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="403" element={<ForbiddenPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
