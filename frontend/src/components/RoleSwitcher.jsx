/**
 * RoleSwitcher Component
 *
 * Dropdown component for users with multiple roles to switch between different views.
 * Only renders if the user has more than one role assigned.
 *
 * For Master Admin (admin@perenniaai.com):
 * - Shows ALL available roles to preview any user's view
 * - Uses viewAs mode instead of actual role switching
 *
 * When switching roles:
 * - Navigation sidebar changes to show items for the selected role
 * - Dashboard widgets change to match the selected role's view
 * - Permissions remain the same (user keeps highest permissions from all roles)
 */

import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { isMasterAdmin, ROLE_DEFAULT_ROUTES } from '../config/roleConfig';
import './RoleSwitcher.css';
import { getUserData } from '../utils/tokenStore';

// All available roles that master admin can preview
const ALL_AVAILABLE_ROLES = [
  { id: 'admin', name: 'Platform Admin', category: 'Admin' },
  { id: 'site_admin', name: 'Site Administrator', category: 'Admin' },
  { id: 'executive', name: 'Executive', category: 'Leadership' },
  { id: 'manager', name: 'Manager', category: 'Management' },
  { id: 'loan_officer', name: 'Loan Officer', category: 'Sales' },
  { id: 'production_assistant', name: 'Production Assistant', category: 'Support' },
  { id: 'concierge', name: 'Concierge', category: 'Support' },
  { id: 'processor', name: 'Processor', category: 'Operations' },
  { id: 'underwriter', name: 'Underwriter', category: 'Operations' },
  { id: 'closer', name: 'Closer', category: 'Operations' },
];

const RoleSwitcher = () => {
  const navigate = useNavigate();
  const {
    assignedRoles,
    activeRole,
    canSwitchRoles,
    switchRole,
    loading,
    viewAsRole,
    setViewAsRole
  } = usePermissions();

  const [isOpen, setIsOpen] = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [error, setError] = useState(null);

  // Get user email to check if master admin
  const userEmail = useMemo(() => {
    try {
      const user = getUserData();
      if (user) {
        return user.email || null;
      }
      return null;
    } catch {
      return null;
    }
  }, []);

  const isMasterAdminUser = isMasterAdmin(userEmail);

  // Group roles by category for master admin - must be before early return to satisfy hooks rules
  const groupedRoles = useMemo(() => {
    if (!isMasterAdminUser) return null;

    const groups = {};
    ALL_AVAILABLE_ROLES.forEach(role => {
      if (!groups[role.category]) {
        groups[role.category] = [];
      }
      groups[role.category].push(role);
    });
    return groups;
  }, [isMasterAdminUser]);

  // Close dropdown when clicking outside - must be before early return to satisfy hooks rules
  React.useEffect(() => {
    const handleClickOutside = (e) => {
      if (!e.target.closest('.role-switcher')) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('click', handleClickOutside);
    }
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [isOpen]);

  // For master admin, always show the switcher with all roles
  // For regular users, only show if they have multiple assigned roles
  if (loading) {
    return null;
  }

  if (!isMasterAdminUser && (!canSwitchRoles || !assignedRoles || assignedRoles.length <= 1)) {
    return null;
  }

  // For master admin, handle view-as switching
  const handleMasterAdminViewAs = (roleId) => {
    if (roleId === viewAsRole) {
      setIsOpen(false);
      return;
    }

    // Store viewAsRole in localStorage FIRST (synchronous)
    localStorage.setItem('viewAsRole', roleId);

    // Get the default route for the selected role
    const defaultRoute = ROLE_DEFAULT_ROUTES[roleId] || '/dashboard';

    // Immediately redirect to the appropriate page for this role
    // Use a small timeout to ensure localStorage is written before redirect
    setTimeout(() => {
      window.location.href = defaultRoute;
    }, 50);
  };

  const handleRoleSwitch = async (roleId) => {
    // For master admin, use view-as mode
    if (isMasterAdminUser) {
      handleMasterAdminViewAs(roleId);
      return;
    }

    if (roleId === activeRole?.id) {
      setIsOpen(false);
      return;
    }

    setIsSwitching(true);
    setError(null);

    const result = await switchRole(roleId);

    if (result.success) {
      setIsOpen(false);
      // Navigate to the default page for the selected role
      const defaultRoute = ROLE_DEFAULT_ROUTES[roleId] || '/dashboard';
      window.location.href = defaultRoute;
    } else {
      setError(result.error || 'Failed to switch role');
    }

    setIsSwitching(false);
  };

  const toggleDropdown = () => {
    if (!isSwitching) {
      setIsOpen(!isOpen);
      setError(null);
    }
  };

  // Determine which roles to show
  const rolesToShow = isMasterAdminUser ? ALL_AVAILABLE_ROLES : assignedRoles;
  const currentRole = isMasterAdminUser ? (viewAsRole || 'admin') : activeRole?.id;
  const currentRoleName = isMasterAdminUser
    ? (ALL_AVAILABLE_ROLES.find(r => r.id === (viewAsRole || 'admin'))?.name || 'Platform Admin')
    : (activeRole?.name || 'Select Role');

  return (
    <div className="role-switcher">
      <button
        className={`role-switcher-button ${isOpen ? 'open' : ''}`}
        onClick={toggleDropdown}
        disabled={isSwitching}
        title="Switch role view"
      >
        <span className="role-switcher-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="8.5" cy="7" r="4"/>
            <path d="M20 8v6"/>
            <path d="M23 11l-3-3-3 3"/>
          </svg>
        </span>
        <span className="role-switcher-label">
          {currentRoleName}
        </span>
        <span className={`role-switcher-arrow ${isOpen ? 'open' : ''}`}>
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </span>
      </button>

      {isOpen && (
        <div className={`role-switcher-dropdown ${isMasterAdminUser ? 'master-admin-dropdown' : ''}`}>
          <div className="role-switcher-header">
            Switch View As
          </div>
          {error && (
            <div className="role-switcher-error">
              {error}
            </div>
          )}

          {isMasterAdminUser && groupedRoles ? (
            // Master admin sees grouped roles
            <div className="role-switcher-grouped">
              {Object.entries(groupedRoles).map(([category, roles]) => (
                <div key={category} className="role-group">
                  <div className="role-group-header">{category}</div>
                  <ul className="role-switcher-list">
                    {roles.map((role) => (
                      <li key={role.id}>
                        <button
                          className={`role-switcher-option ${role.id === currentRole ? 'active' : ''}`}
                          onClick={() => handleRoleSwitch(role.id)}
                          disabled={isSwitching}
                        >
                          <span className="role-option-name">{role.name}</span>
                          {role.id === currentRole && (
                            <span className="role-option-badge active">Active</span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            // Regular users see their assigned roles
            <ul className="role-switcher-list">
              {assignedRoles.map((role) => (
                <li key={role.id}>
                  <button
                    className={`role-switcher-option ${role.id === activeRole?.id ? 'active' : ''}`}
                    onClick={() => handleRoleSwitch(role.id)}
                    disabled={isSwitching}
                  >
                    <span className="role-option-name">{role.name}</span>
                    {role.is_primary && (
                      <span className="role-option-badge primary">Primary</span>
                    )}
                    {role.id === activeRole?.id && (
                      <span className="role-option-badge active">Active</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {isSwitching && (
            <div className="role-switcher-loading">
              <span className="spinner"></span>
              Switching...
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RoleSwitcher;
