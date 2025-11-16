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
  const [userRole, setUserRole] = useState('sales'); // Default role
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
      setUserRole(data.permission_role || 'sales');

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

  const value = {
    permissions,
    userRole,
    loading,
    currentUserId,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    refetchPermissions: fetchPermissions
  };

  return (
    <PermissionContext.Provider value={value}>
      {children}
    </PermissionContext.Provider>
  );
};
