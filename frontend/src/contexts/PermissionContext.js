import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import { useImpersonation } from './ImpersonationContext';
import { API_BASE_URL } from '../services/api';
import { getUserEffectiveRole, mapRoleNameToEffective } from '../config/roleConfig';
import { getToken } from '../utils/tokenStore';

const PermissionContext = createContext();

export const usePermissions = () => {
  const context = useContext(PermissionContext);
  if (!context) {
    throw new Error('usePermissions must be used within PermissionProvider');
  }
  return context;
};

export const PermissionProvider = ({ children }) => {
  const [permissions, setPermissions] = useState({});
  // Initialize userRole from localStorage to prevent flicker, fallback to 'sales'
  const [userRole, setUserRole] = useState(() => {
    try {
      const savedRole = localStorage.getItem('userRole');
      if (savedRole) return savedRole;

      // Fallback: infer from user object when userRole key hasn't been set yet
      // (e.g., permissions API has been 500ing since login)
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        if (user.permission_role) return user.permission_role;
        if (user.is_admin === true || user.role === 'admin') return 'admin';
      }
      return 'sales';
    } catch {
      return 'sales';
    }
  });

  // Multi-role system state
  const [assignedRoles, setAssignedRoles] = useState(() => {
    try {
      const saved = localStorage.getItem('assignedRoles');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [activeRole, setActiveRole] = useState(() => {
    try {
      const saved = localStorage.getItem('activeRole');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [canSwitchRoles, setCanSwitchRoles] = useState(() => {
    try {
      const saved = localStorage.getItem('canSwitchRoles');
      return saved === 'true';
    } catch {
      return false;
    }
  });
  // Legacy role from user object (more specific role like processor, underwriter, closer)
  const [legacyRole, setLegacyRole] = useState(() => {
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        return user.role || null;
      }
      return null;
    } catch {
      return null;
    }
  });
  // View-as role for admin role switching (affects navigation and dashboard containers)
  const [viewAsRole, setViewAsRole] = useState(() => {
    try {
      const saved = localStorage.getItem('viewAsRole');
      return saved || null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);
  const [currentUserId, setCurrentUserId] = useState(null);
  const { isImpersonating, getImpersonatedUser } = useImpersonation();

  // Check for role preview mode (admin previewing a specific role's dashboard)
  const [rolePreview, setRolePreview] = useState(() => {
    try {
      const preview = localStorage.getItem('role_preview');
      return preview ? JSON.parse(preview) : null;
    } catch {
      return null;
    }
  });

  // Compute effective role for UI purposes (combines permission_role + legacy role + activeRole from multi-role system)
  // Priority: 1. Role preview mode, 2. Active role from multi-role system, 3. viewAsRole for admin switching, 4. Base role
  // IMPORTANT: Role preview mode takes highest priority
  const effectiveRole = useMemo(() => {
    // If in role preview mode, use the preview role
    if (rolePreview && rolePreview.role_name) {
      const previewRoleName = rolePreview.role_name.toLowerCase().replace(/\s+/g, '_');
      // Map production_assistant variants and concierge to production_assistant
      if (previewRoleName === 'production_assistant_1' || previewRoleName === 'production_assistant_2' || previewRoleName === 'concierge') {
        return 'production_assistant';
      }
      return previewRoleName;
    }

    // If user has multi-role and has selected an active role, use that for UI
    if (canSwitchRoles && activeRole && activeRole.name) {
      const mappedRole = mapRoleNameToEffective(activeRole.name);
      return mappedRole;
    }

    const baseRole = getUserEffectiveRole(userRole, legacyRole);
    // Check if user can switch role views (admin or management/manager)
    const canSwitchViews = baseRole === 'admin' ||
                           baseRole === 'manager' ||
                           userRole === 'admin' ||
                           userRole === 'management';

    // If user can switch views and has a viewAsRole set, use that for navigation
    if (canSwitchViews && viewAsRole && viewAsRole !== 'default' && viewAsRole !== 'admin') {
      // Map production_assistant variants and concierge to production_assistant
      if (viewAsRole === 'production_assistant_1' || viewAsRole === 'production_assistant_2' || viewAsRole === 'concierge') {
        return 'production_assistant';
      }
      // site_admin keeps its own role - NOT mapped to admin
      // site_admin has limited access compared to platform admin
      if (viewAsRole === 'site_admin') {
        return 'site_admin';
      }
      return viewAsRole;
    }
    return baseRole;
  }, [userRole, legacyRole, viewAsRole, rolePreview, activeRole, canSwitchRoles]);

  // Fetch permissions whenever impersonation state changes
  useEffect(() => {
    fetchPermissions();
  }, [isImpersonating]);

  // Listen for auth changes (login/logout) to refresh permissions and clear stale state
  useEffect(() => {
    const handleAuthChange = (event) => {
      const { type } = event.detail || {};

      if (type === 'logout') {
        // Clear all permission state on logout
        setPermissions({});
        setUserRole('sales');
        setLegacyRole(null);
        setAssignedRoles([]);
        setActiveRole(null);
        setCanSwitchRoles(false);
        setViewAsRole(null);
        setRolePreview(null);
        setCurrentUserId(null);

        // Clear localStorage
        try {
          localStorage.removeItem('userRole');
          localStorage.removeItem('assignedRoles');
          localStorage.removeItem('activeRole');
          localStorage.removeItem('canSwitchRoles');
          localStorage.removeItem('viewAsRole');
          localStorage.removeItem('role_preview');
        } catch (e) {
          // Ignore localStorage errors
        }
      } else if (type === 'login') {
        // Clear view-as-role and role-preview state from the previous session.
        // These are NOT cleared by clearTokens() and must be reset at login time
        // so an admin's "view as user" mode from before the timeout doesn't carry
        // into (or out of) the new session.
        setViewAsRole(null);
        setRolePreview(null);
        try {
          localStorage.removeItem('viewAsRole');
          localStorage.removeItem('role_preview');
        } catch (e) { /* ignore */ }
        // Re-fetch permissions on login
        fetchPermissions();
      }
    };

    window.addEventListener('authChange', handleAuthChange);
    return () => window.removeEventListener('authChange', handleAuthChange);
  }, []);

  const fetchPermissions = async () => {
    try {
      setLoading(true);

      // Skip permission fetching on public routes (application pages, booking, portals, etc.)
      const publicRoutes = ['/apply/', '/purl/', '/borrower-portal/', '/book/', '/embed/book/', '/booking/', '/portal/', '/partner/', '/sign/', '/lo/', '/shared/', '/meeting/'];
      const currentPath = window.location.pathname;
      if (publicRoutes.some(route => currentPath.startsWith(route))) {
        setLoading(false);
        return;
      }

      // Get the current user from localStorage
      const userStr = localStorage.getItem('user');
      if (!userStr) {
        setUserRole('sales');
        setLoading(false);
        return;
      }

      const user = JSON.parse(userStr);
      let userId = user.id;

      // If impersonating, use impersonated user's ID
      if (isImpersonating) {
        const impersonatedUser = getImpersonatedUser();
        if (impersonatedUser && impersonatedUser.id) {
          userId = impersonatedUser.id;
        }
      }

      setCurrentUserId(userId);

      // Fetch permissions from backend
      const token = getToken();
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Add impersonation token if present
      const impersonationData = localStorage.getItem('impersonation');
      if (impersonationData) {
        try {
          const data = JSON.parse(impersonationData);
          if (data.session_token) {
            headers['X-Impersonation-Token'] = data.session_token;
          }
        } catch (error) {
          console.error('Error parsing impersonation data:', error);
        }
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/users/${userId}/permissions`, {
        headers
      });

      if (!response.ok) {
        if (response.status === 401) {
          // Don't clear tokens or redirect here — the api.js interceptor
          // handles 401 session management with retry-with-refresh logic.
          // Redirecting here races with login navigation and causes loops.
          console.warn('[PermissionContext] 401 on permissions fetch — using defaults');
          return;
        }
        throw new Error(`Failed to fetch permissions: ${response.status}`);
      }

      const data = await response.json();

      setPermissions(data.permissions || {});
      const role = data.permission_role || 'sales';
      setUserRole(role);

      // Extract legacy role from user object for more specific role detection
      const userLegacyRole = user.role || data.role || null;
      setLegacyRole(userLegacyRole);

      // Persist role to localStorage to prevent flicker on reload
      try {
        localStorage.setItem('userRole', role);
      } catch (e) {
        // Ignore localStorage errors
      }

    } catch (error) {
      console.error('PermissionContext: Error fetching permissions:', error);
      // When API fails, infer role from the current session's user object (written at
      // login time by setAuth). Always override — not just when userRole === 'sales' —
      // so a stale 'admin' from a previous session doesn't persist when a non-admin logs in
      // and the permissions endpoint is temporarily down.
      try {
        const userStr = localStorage.getItem('user');
        if (userStr) {
          const user = JSON.parse(userStr);
          if (user.permission_role) {
            setUserRole(user.permission_role);
          }
        }
      } catch (e) {
        // Ignore localStorage errors
      }
    } finally {
      setLoading(false);
    }
  };

  // Fetch user's assigned roles (multi-role system)
  const fetchUserRoles = useCallback(async () => {
    try {
      const token = getToken();
      if (!token) {
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/users/me/roles`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        if (response.status === 401) {
          console.warn('[PermissionContext] 401 on roles fetch — skipping');
          return;
        }
        // If endpoint doesn't exist yet (404), silently continue
        if (response.status === 404) {
          return;
        }
        throw new Error(`Failed to fetch user roles: ${response.status}`);
      }

      const data = await response.json();

      setAssignedRoles(data.assigned_roles || []);
      setActiveRole(data.active_role || null);
      setCanSwitchRoles(data.can_switch_roles || false);

      // Persist to localStorage
      try {
        localStorage.setItem('assignedRoles', JSON.stringify(data.assigned_roles || []));
        localStorage.setItem('activeRole', JSON.stringify(data.active_role || null));
        localStorage.setItem('canSwitchRoles', String(data.can_switch_roles || false));
      } catch (e) {
        // Ignore localStorage errors
      }
    } catch (error) {
      console.error('Error fetching user roles:', error);
    }
  }, []);

  // Switch active role for UI view (multi-role system)
  const switchRole = useCallback(async (roleId) => {
    try {
      const token = getToken();
      if (!token) {
        throw new Error('No authentication token');
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/users/me/roles/switch`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ role_id: roleId })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to switch role');
      }

      const data = await response.json();

      // Update active role state
      const newActiveRole = {
        id: data.active_role.id,
        name: data.active_role.name,
        is_primary: assignedRoles.find(r => r.id === data.active_role.id)?.is_primary || false
      };
      setActiveRole(newActiveRole);

      // Persist to localStorage
      try {
        localStorage.setItem('activeRole', JSON.stringify(newActiveRole));
      } catch (e) {
        // Ignore localStorage errors
      }

      return { success: true, message: data.message };
    } catch (error) {
      console.error('Error switching role:', error);
      return { success: false, error: error.message };
    }
  }, [assignedRoles]);

  // Fetch user roles when permissions load
  useEffect(() => {
    if (!loading && currentUserId) {
      fetchUserRoles();
    }
  }, [loading, currentUserId, fetchUserRoles]);

  // Check if user has a specific permission
  const hasPermission = (permissionKey) => {
    // Admin (platform), site_admin (org), and management roles have all permissions
    if ((effectiveRole || userRole) === 'admin' || (effectiveRole || userRole) === 'site_admin' || (effectiveRole || userRole) === 'management') {
      return true;
    }

    // Check specific permission
    return permissions[permissionKey] === true;
  };

  // Check if user has ANY of the provided permissions
  const hasAnyPermission = (permissionKeys) => {
    // Admin (platform), site_admin (org), and management roles have all permissions
    if ((effectiveRole || userRole) === 'admin' || (effectiveRole || userRole) === 'site_admin' || userRole === 'management') {
      return true;
    }

    return permissionKeys.some(key => permissions[key] === true);
  };

  // Check if user has ALL of the provided permissions
  const hasAllPermissions = (permissionKeys) => {
    // Admin (platform), site_admin (org), and management roles have all permissions
    if ((effectiveRole || userRole) === 'admin' || (effectiveRole || userRole) === 'site_admin' || userRole === 'management') {      return true;
    }

    return permissionKeys.every(key => permissions[key] === true);
  };

  // Check if currently in read-only impersonation mode
  const isReadOnlyMode = () => {
    const impersonationData = localStorage.getItem('impersonation');
    if (!impersonationData) {
      return false;
    }
    try {
      const data = JSON.parse(impersonationData);
      return data.mode === 'read_only';
    } catch {
      return false;
    }
  };

  // Check if user can perform an action (combines permission check + impersonation mode)
  // For write operations (create, edit, delete), also checks if in read-only mode
  const canPerformAction = (permissionKey, isWriteOperation = false) => {
    // If it's a write operation and we're in read-only mode, block it
    if (isWriteOperation && isReadOnlyMode()) {
      return false;
    }
    // Otherwise, check the permission
    return hasPermission(permissionKey);
  };

  // Get the data scope for a resource type (what data can user see)
  // Returns: 'all', 'team', 'own', or 'none'
  const getDataScope = (resourceType) => {
    // Admin (platform), site_admin (org), and management roles see all (within their scope)
    if (userRole === 'admin' || userRole === 'site_admin' ||
      userRole === 'management') {
      return 'all';
    }

    // Check view permissions in order of broadest to narrowest
    const viewAllKey = `${resourceType}.view_all`;
    const viewTeamKey = `${resourceType}.view_team`;
    const viewAssignedKey = `${resourceType}.view_assigned`;

    if (permissions[viewAllKey] === true) {
      return 'all';
    }
    if (permissions[viewTeamKey] === true) {
      return 'team';
    }
    if (permissions[viewAssignedKey] === true) {
      return 'own';
    }

    // Default to own data only
    return 'own';
  };

  // Update view-as role (for admin role switching)
  const updateViewAsRole = (role) => {
    setViewAsRole(role);
    try {
      if (role) {
        localStorage.setItem('viewAsRole', role);
      } else {
        localStorage.removeItem('viewAsRole');
      }
    } catch (e) {
      // Ignore localStorage errors
    }
  };

  // Check if user can switch role views (admin, site_admin, or management)
  // Also checks localStorage user object as fallback for is_admin flag or role='admin'
  const isAdmin = useMemo(() => {
    const baseRole = getUserEffectiveRole(userRole, legacyRole);

    // Check computed roles
    if (baseRole === 'admin' || baseRole === 'site_admin' || baseRole === 'manager') {
      return true;
    }
    if (userRole === 'admin' || userRole === 'site_admin' || userRole === 'management') {
      return true;
    }
    // Direct legacyRole check - getUserEffectiveRole doesn't map 'admin' as a legacy role
    if (legacyRole === 'admin' || legacyRole === 'site_admin' || legacyRole === 'Admin') {
      return true;
    }

    // Fallback: check localStorage user object for is_admin flag or admin role
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        if (user.is_admin === true || user.role === 'admin' || user.permission_role === 'admin') {
          return true;
        }
      }
    } catch (e) {
      // Ignore localStorage errors
    }

    return false;
  }, [userRole, legacyRole]);

  // Check if user is a platform admin (developer) vs site admin (licensee)
  // Site admins are NOT platform admins - they only manage their own organization
  const isPlatformAdmin = useMemo(() => {
    // First check: site_admin is explicitly NOT a platform admin
    const effectiveRole = getUserEffectiveRole(userRole, legacyRole);
    if (userRole === 'site_admin' || effectiveRole === 'site_admin') {
      return false;
    }

    // Check context role
    if (userRole === 'admin' || effectiveRole === 'admin') {
      return true;
    }

    // Fallback: check localStorage user object
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        // site_admin in localStorage is NOT a platform admin
        if (user.role === 'site_admin' || user.permission_role === 'site_admin') {
          return false;
        }
        // Only true platform admins
        if (user.role === 'admin' || user.permission_role === 'admin') {
          return true;
        }
      }
    } catch (e) {
      // Ignore localStorage errors
    }

    return false;
  }, [userRole, legacyRole]);

  // Check if user is a site administrator (licensee managing their org)
  const isSiteAdmin = useMemo(() => {
    return userRole === 'site_admin'
      || getUserEffectiveRole(userRole, legacyRole) === 'site_admin';
  }, [userRole, legacyRole]);

  // Exit role preview mode and restore original user
  const exitRolePreview = () => {
    try {
      const originalUser = localStorage.getItem('original_user_backup');
      const originalToken = localStorage.getItem('original_token_backup');

      if (originalUser) {
        localStorage.setItem('user', originalUser);
      }
      if (originalToken) {
        localStorage.setItem('token', originalToken);
      }

      // Clear preview data
      localStorage.removeItem('role_preview');
      localStorage.removeItem('original_user_backup');
      localStorage.removeItem('original_token_backup');

      setRolePreview(null);

      // Redirect to admin panel
      window.location.href = '/admin';
    } catch (error) {
      console.error('Error exiting role preview:', error);
    }
  };

  const value = {
    permissions,
    userRole,
    legacyRole,
    effectiveRole,  // Computed role for UI (combines permission_role + legacy role + viewAsRole + activeRole)
    viewAsRole,     // Current view-as role selection (for admin role switching - legacy)
    isAdmin,        // Whether user is admin (can switch views) - includes both platform & site admins
    isPlatformAdmin, // Whether user is platform admin (developer with god-mode)
    isSiteAdmin,    // Whether user is site admin (licensee managing their org)
    loading,
    currentUserId,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    isReadOnlyMode,
    canPerformAction,
    getDataScope,
    updateViewAsRole,  // Function to update view-as role (legacy)
    refetchPermissions: fetchPermissions,
    // Role preview mode
    rolePreview,       // Current role preview info (if any)
    isRolePreview: !!rolePreview,  // Boolean flag for easy checking
    exitRolePreview,   // Function to exit role preview mode
    // Multi-role system
    assignedRoles,     // List of roles assigned to user [{id, name, is_primary, assigned_at}]
    activeRole,        // Currently active role for UI view {id, name, is_primary}
    canSwitchRoles,    // Whether user has multiple roles and can switch between them
    switchRole,        // Function to switch active role: switchRole(roleId) -> {success, message/error}
    refetchUserRoles: fetchUserRoles  // Function to refresh user roles
  };

  return (
    <PermissionContext.Provider value={value}>
      {children}
    </PermissionContext.Provider>
  );
};
