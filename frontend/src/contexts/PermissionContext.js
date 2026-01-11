import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import { useImpersonation } from './ImpersonationContext';
import { API_BASE_URL } from '../services/api';
import { getUserEffectiveRole } from '../config/roleConfig';

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
      return savedRole || 'sales';
    } catch {
      return 'sales';
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

  // Compute effective role for UI purposes (combines permission_role + legacy role)
  // If viewAsRole is set and user can switch views (admin or manager), use that instead
  // IMPORTANT: Role preview mode takes highest priority
  const effectiveRole = useMemo(() => {
    // If in role preview mode, use the preview role
    if (rolePreview && rolePreview.role_name) {
      const previewRoleName = rolePreview.role_name.toLowerCase().replace(/\s+/g, '_');
      console.log('Role preview mode active, using role:', previewRoleName);
      // Map production_assistant variants and concierge to production_assistant
      if (previewRoleName === 'production_assistant_1' || previewRoleName === 'production_assistant_2' || previewRoleName === 'concierge') {
        return 'production_assistant';
      }
      return previewRoleName;
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
      // Map site_admin to admin for navigation purposes
      if (viewAsRole === 'site_admin') {
        return 'admin';
      }
      return viewAsRole;
    }
    return baseRole;
  }, [userRole, legacyRole, viewAsRole, rolePreview]);

  // Fetch permissions whenever impersonation state changes
  useEffect(() => {
    fetchPermissions();
  }, [isImpersonating]);

  const fetchPermissions = async () => {
    try {
      setLoading(true);

      // Get the current user from localStorage
      const userStr = localStorage.getItem('user');
      if (!userStr) {
        console.warn('PermissionContext: No user found in localStorage - setting default sales role');
        setUserRole('sales');
        setLoading(false);
        return;
      }
      console.log('PermissionContext: User from localStorage:', userStr?.substring(0, 100));

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
      const token = localStorage.getItem('token');
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
        console.warn('Could not save userRole to localStorage:', e);
      }

      console.log('Permissions loaded:', {
        userId,
        permissionRole: data.permission_role,
        legacyRole: userLegacyRole,
        effectiveRole: getUserEffectiveRole(role, userLegacyRole),
        permissionCount: Object.keys(data.permissions || {}).length,
        isImpersonating
      });

    } catch (error) {
      console.error('PermissionContext: Error fetching permissions:', error);
      console.error('PermissionContext: Error details:', error.message, error.stack);
      // Set default permissions on error - this causes Access Denied on admin pages
      setPermissions({});
      setUserRole('sales');
      // Clear cached role on error
      try {
        localStorage.removeItem('userRole');
      } catch (e) {
        // Ignore localStorage errors
      }
    } finally {
      setLoading(false);
    }
  };

  // Check if user has a specific permission
  const hasPermission = (permissionKey) => {
    // Admin and management roles have all permissions
    if (userRole === 'admin' || userRole === 'management') {
      return true;
    }

    // Check specific permission
    return permissions[permissionKey] === true;
  };

  // Check if user has ANY of the provided permissions
  const hasAnyPermission = (permissionKeys) => {
    // Admin and management roles have all permissions
    if (userRole === 'admin' || userRole === 'management') {
      return true;
    }

    return permissionKeys.some(key => permissions[key] === true);
  };

  // Check if user has ALL of the provided permissions
  const hasAllPermissions = (permissionKeys) => {
    // Admin and management roles have all permissions
    if (userRole === 'admin' || userRole === 'management') {
      return true;
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
    // Admin and management roles see all
    if (userRole === 'admin' || userRole === 'management') {
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
      console.warn('Could not save viewAsRole to localStorage:', e);
    }
  };

  // Check if user can switch role views (admin or management)
  const isAdmin = useMemo(() => {
    const baseRole = getUserEffectiveRole(userRole, legacyRole);
    return baseRole === 'admin' ||
           baseRole === 'manager' ||
           userRole === 'admin' ||
           userRole === 'management';
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
    effectiveRole,  // Computed role for UI (combines permission_role + legacy role + viewAsRole)
    viewAsRole,     // Current view-as role selection (for admin role switching)
    isAdmin,        // Whether user is admin (can switch views)
    loading,
    currentUserId,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    isReadOnlyMode,
    canPerformAction,
    getDataScope,
    updateViewAsRole,  // Function to update view-as role
    refetchPermissions: fetchPermissions,
    // Role preview mode
    rolePreview,       // Current role preview info (if any)
    isRolePreview: !!rolePreview,  // Boolean flag for easy checking
    exitRolePreview    // Function to exit role preview mode
  };

  return (
    <PermissionContext.Provider value={value}>
      {children}
    </PermissionContext.Provider>
  );
};
