import React, { createContext, useContext, useState, useEffect } from 'react';
import { useImpersonation } from './ImpersonationContext';
import { API_BASE_URL } from '../services/api';

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
  const [loading, setLoading] = useState(true);
  const [currentUserId, setCurrentUserId] = useState(null);
  const { isImpersonating, getImpersonatedUser } = useImpersonation();

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
        console.warn('No user found in localStorage');
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
      // Persist role to localStorage to prevent flicker on reload
      try {
        localStorage.setItem('userRole', role);
      } catch (e) {
        console.warn('Could not save userRole to localStorage:', e);
      }

      console.log('Permissions loaded:', {
        userId,
        role: data.permission_role,
        permissionCount: Object.keys(data.permissions || {}).length,
        isImpersonating
      });

    } catch (error) {
      console.error('Error fetching permissions:', error);
      // Set default permissions on error
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
    // Management role has all permissions
    if (userRole === 'management') {
      return true;
    }

    // Check specific permission
    return permissions[permissionKey] === true;
  };

  // Check if user has ANY of the provided permissions
  const hasAnyPermission = (permissionKeys) => {
    if (userRole === 'management') {
      return true;
    }

    return permissionKeys.some(key => permissions[key] === true);
  };

  // Check if user has ALL of the provided permissions
  const hasAllPermissions = (permissionKeys) => {
    if (userRole === 'management') {
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
    // Management role sees all
    if (userRole === 'management') {
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

  const value = {
    permissions,
    userRole,
    loading,
    currentUserId,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    isReadOnlyMode,
    canPerformAction,
    getDataScope,
    refetchPermissions: fetchPermissions
  };

  return (
    <PermissionContext.Provider value={value}>
      {children}
    </PermissionContext.Provider>
  );
};
