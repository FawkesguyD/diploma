import { Navigate, Route, Routes } from "react-router-dom";

import { AuthGuard } from "../../features/auth/ui/AuthGuard";
import { LoginPage } from "../../pages/login/LoginPage";
import { NotFoundPage } from "../../pages/not-found/NotFoundPage";
import { ShortlistPage } from "../../pages/shortlist/ShortlistPage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/shortlist" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/shortlist"
        element={
          <AuthGuard>
            <ShortlistPage />
          </AuthGuard>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
