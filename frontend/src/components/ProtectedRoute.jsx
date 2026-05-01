import { Navigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useModules } from '../contexts/ModuleContext';
import { isAuthenticatedSync as isAuthenticated } from '../utils/auth';

/**
 * ProtectedRoute - Authentication + role-based route guard
 *
 * Extends the existing PrivateRoute pattern with optional role restrictions.
 * When requiredRoles is provided, only users whose effectiveRole or userRole
 * matches one of the allowed roles can access the route.
 *
 * Usage:
 *   <ProtectedRoute requiredRoles={['admin', 'site_admin']}>
 *     <AdminPanel />
 *   </ProtectedRoute>
 *
 *   <ProtectedRoute>
 *     <Dashboard />   // any authenticated user
 *   </ProtectedRoute>
 *
 * Props:
 *   requiredRoles - Optional array of role strings (e.g., ['admin', 'site_admin', 'manager']).
 *                   If omitted, behaves like PrivateRoute (auth-only).
 *   children      - The content to render when access is granted.
 */
function ProtectedRoute({ children, requiredRoles }) {
  const {
    effectiveRole,
    userRole,
    isAdmin,
    isPlatformAdmin,
    isSiteAdmin,
    loading: permissionsLoading,
  } = usePermissions();
  const { loading: modulesLoading } = useModules();

  // Step 1: Check authentication
  if (!isAuthenticated()) {
    return <Navigate to="/login" />;
  }

  // Step 2: Wait for permissions/modules to load (prevents flicker)
  if (permissionsLoading || modulesLoading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        gap: '12px',
      }}>
        <div style={{
          width: '32px',
          height: '32px',
          border: '3px solid #e5e7eb',
          borderTopColor: '#3b82f6',
          borderRadius: '50%',
          animation: 'page-loader-spin 0.7s linear infinite',
        }} />
        <p style={{ fontSize: '14px', color: '#666', margin: 0 }}>Loading...</p>
        <style>{`@keyframes page-loader-spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Step 3: Check role authorization (only when requiredRoles is specified)
  if (requiredRoles && requiredRoles.length > 0) {
    const normalizedEffective = (effectiveRole || '').toLowerCase();
    const normalizedUserRole = (userRole || '').toLowerCase();
    const normalizedRequired = requiredRoles.map(r => r.toLowerCase());

    let roleMatch = false;

    // Direct role match against effectiveRole or userRole
    if (normalizedRequired.includes(normalizedEffective) ||
        normalizedRequired.includes(normalizedUserRole)) {
      roleMatch = true;
    }

    // Convenience: if 'admin' is required, also match isPlatformAdmin and isAdmin
    if (!roleMatch && normalizedRequired.includes('admin') && (isPlatformAdmin || isAdmin)) {
      roleMatch = true;
    }

    // Convenience: if 'site_admin' is required, also match isSiteAdmin
    if (!roleMatch && normalizedRequired.includes('site_admin') && isSiteAdmin) {
      roleMatch = true;
    }

    // Convenience: if 'management' is required, also match 'manager' effective role
    if (!roleMatch && normalizedRequired.includes('management') &&
        (normalizedEffective === 'manager' || normalizedUserRole === 'management')) {
      roleMatch = true;
    }

    if (!roleMatch) {
      return <Navigate to="/forbidden" replace />;
    }
  }

  return children;
}

export default ProtectedRoute;
