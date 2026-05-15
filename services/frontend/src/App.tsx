import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@/components/theme-provider';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuthProvider } from '@/auth/AuthProvider';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { AppLayout } from '@/components/AppLayout';
import { LoginPage } from '@/pages/LoginPage';
import { HomePage } from '@/pages/HomePage';
import { MessagesPage } from '@/pages/MessagesPage';
import { MessageDetailPage } from '@/pages/MessageDetailPage';
import { SourcesPage } from '@/pages/SourcesPage';
import { ObjectsPage } from '@/pages/ObjectsPage';
import { DashboardsPage } from '@/pages/DashboardsPage';
import { MapPage } from '@/pages/MapPage';
import { SettingsPage } from '@/pages/SettingsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <BrowserRouter>
            <AuthProvider>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  element={
                    <ProtectedRoute>
                      <AppLayout />
                    </ProtectedRoute>
                  }
                >
                  <Route index element={<Navigate to="/home" replace />} />
                  <Route path="/home" element={<HomePage />} />
                  <Route path="/messages" element={<MessagesPage />} />
                  <Route path="/messages/:id" element={<MessageDetailPage />} />
                  <Route path="/sources" element={<SourcesPage />} />
                  <Route path="/objects" element={<ObjectsPage />} />
                  <Route path="/objects/top-undervalued" element={<Navigate to="/objects?undervalued=1" replace />} />
                  <Route path="/trends" element={<Navigate to="/messages?view=trends" replace />} />
                  <Route path="/favorites" element={<Navigate to="/home" replace />} />
                  <Route path="/dashboards" element={<DashboardsPage />} />
                  <Route path="/map" element={<MapPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/home" replace />} />
              </Routes>
              <Toaster position="top-right" richColors />
            </AuthProvider>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
