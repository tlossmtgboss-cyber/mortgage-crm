import React from 'react';
import { Navigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';

/**
 * RoleGuard - Declarative role-based access control wrapper
 *
 * Usage:
 *   <RoleGuard allowedRoles={['admin', 'site_admin']}>
 *     <AdminOnlyContent />
 *   </RoleGuard>
 *
 *   <RoleGuard allowedRoles={['admin', 'manager']} requiredPermissions={['team.manage']}>
 *     <TeamManagementContent />
 *   </RoleGuard>
 *
 *   <RoleGuard allowedRoles={['admin']} fallback="/dashboard">
 *     <SuperAdminContent />
 *   </RoleGuard>
 *
 * Props:
 *   allowedRoles      - Array of role strings. User's effectiveRole OR userRole must match one.
 *   requiredPermissions - Optional array of permission keys. If provided, user must have at least one.
 *   fallback          - String path to redirect to, OR a React element to render. Defaults to AccessDenied UI.
 *   loading           - Optional custom loading element while permissions load.
 */
function RoleGuard({ children, allowedRoles = [], requiredPermissions = [], fallback, loading: customLoading }) {
  const {
    effectiveRole,
    userRole,
    isAdmin,
    isPlatformAdmin,
    isSiteAdmin,
    hasAnyPermission,
    loading
  } = usePermissions();

  // Show loading state while permissions are being fetched
  if (loading) {
    if (customLoading) return customLoading;
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '200px' }}>
        <p style={{ color: '#666', fontSize: '14px' }}>Loading...</p>
      </div>
    );
  }

  // Check if user's role matches any allowed role
  const normalizedEffective = (effectiveRole || '').toLowerCase();
  const normalizedUserRole = (userRole || '').toLowerCase();
  const normalizedAllowed = allowedRoles.map(r => r.toLowerCase());

  let roleMatch = normalizedAllowed.length === 0; // If no roles specified, skip role check
  if (!roleMatch) {
    // Direct role match
    roleMatch = normalizedAllowed.includes(normalizedEffective) ||
                normalizedAllowed.includes(normalizedUserRole);
    // Convenience aliases: 'admin' includes platform admin check, 'manager' includes management
    if (!roleMatch && normalizedAllowed.includes('admin') && (isAdmin || isPlatformAdmin)) {
      roleMatch = true;
    }
    if (!roleMatch && normalizedAllowed.includes('site_admin') && isSiteAdmin) {
      roleMatch = true;
    }
    if (!roleMatch && normalizedAllowed.includes('management') && normalizedUserRole === 'management') {
      roleMatch = true;
    }
  }

  // Check permissions if specified
  let permissionMatch = requiredPermissions.length === 0; // If no permissions specified, skip
  if (!permissionMatch) {
    // Admin/site_admin/management bypass permission checks (hasAnyPermission already does this,
    // but we check roleMatch first to avoid unnecessary permission lookups)
    permissionMatch = hasAnyPermission(requiredPermissions);
  }

  // Access granted if role matches OR permissions match (either path grants access)
  const hasAccess = roleMatch || permissionMatch;

  if (hasAccess) {
    return children;
  }

  // Access denied - use fallback
  if (typeof fallback === 'string') {
    return <Navigate to={fallback} replace />;
  }
  if (React.isValidElement(fallback)) {
    return fallback;
  }

  // Default access denied UI
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px' }}>
      <h2 style={{ marginBottom: '12px', color: '#1f2937' }}>Access Denied</h2>
      <p style={{ color: '#6b7280', marginBottom: '24px' }}>
        You don't have permission to access this page.
      </p>
      <a
        href="/dashboard"
        style={{
          display: 'inline-block',
          padding: '10px 24px',
          backgroundColor: '#3b82f6',
          color: '#fff',
          borderRadius: '8px',
          textDecoration: 'none',
          fontSize: '14px',
          fontWeight: 500,
        }}
      >
        Return to Dashboard
      </a>
    </div>
  );
}

export default RoleGuard;
