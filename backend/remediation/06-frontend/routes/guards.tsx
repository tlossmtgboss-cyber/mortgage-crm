/**
 * 06-frontend/routes/guards.tsx
 *
 * Route guards: RequireAuth (authenticated), RequireRole (role-gated).
 *
 * Drop-in: frontend/src/routes/guards.tsx
 */

import { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullPageSpinner } from "@/components/FullPageSpinner";
import { useAuthStore, type UserRole } from "@/stores/authStore";

interface RequireAuthProps {
  children?: ReactNode;
  roles?: UserRole[];
}

export function RequireAuth({ children, roles }: RequireAuthProps) {
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (status === "unknown" || status === "checking") {
    return <FullPageSpinner />;
  }

  if (status === "unauthenticated" || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
