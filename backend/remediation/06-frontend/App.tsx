/**
 * 06-frontend/App.tsx
 *
 * Replaces the 4,843-line App.jsx. Now just: error boundary, query client,
 * route manifest. Routes themselves are lazy-loaded from feature modules.
 *
 * Drop-in: frontend/src/App.tsx
 */

import { Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { FullPageSpinner } from "@/components/FullPageSpinner";
import { routeManifest } from "@/routes/manifest";
import { RequireAuth } from "@/routes/guards";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  const initialize = useAuthStore((s) => s.initialize);
  const theme = useUIStore((s) => s.theme);

  useEffect(() => {
    initialize();
  }, [initialize]);

  useEffect(() => {
    const root = document.documentElement;
    const resolved =
      theme === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme;
    root.classList.toggle("dark", resolved === "dark");
  }, [theme]);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Suspense fallback={<FullPageSpinner />}>
            <Routes>
              {/* Public routes */}
              {routeManifest.public.map((r) => (
                <Route key={r.path} path={r.path} element={<r.Component />} />
              ))}

              {/* Auth-required, role-gated routes */}
              <Route element={<RequireAuth />}>
                {routeManifest.authenticated.map((r) => (
                  <Route
                    key={r.path}
                    path={r.path}
                    element={
                      r.roles ? (
                        <RequireAuth roles={r.roles}>
                          <r.Component />
                        </RequireAuth>
                      ) : (
                        <r.Component />
                      )
                    }
                  />
                ))}
              </Route>

              {/* Fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
