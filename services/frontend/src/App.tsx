import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@/components/theme-provider';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuthProvider } from '@/auth/AuthProvider';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { AppLayout } from '@/components/AppLayout';
import { LoginPage } from '@/pages/LoginPage';
import { MessagesPage } from '@/pages/MessagesPage';
import { MessageDetailPage } from '@/pages/MessageDetailPage';
import { SourcesPage } from '@/pages/SourcesPage';
import { ObjectsPage } from '@/pages/ObjectsPage';
import { TopUndervaluedPage } from '@/pages/TopUndervaluedPage';
import { DashboardsPage } from '@/pages/DashboardsPage';
import { MapPage } from '@/pages/MapPage';

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
                  <Route index element={<Navigate to="/messages" replace />} />
                  <Route path="/messages" element={<MessagesPage />} />
                  <Route path="/messages/:id" element={<MessageDetailPage />} />
                  <Route path="/sources" element={<SourcesPage />} />
                  <Route path="/objects" element={<ObjectsPage />} />
                  <Route path="/objects/top-undervalued" element={<TopUndervaluedPage />} />
                  <Route path="/dashboards" element={<DashboardsPage />} />
                  <Route path="/map" element={<MapPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/messages" replace />} />
              </Routes>
              <Toaster position="top-right" richColors />
            </AuthProvider>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
