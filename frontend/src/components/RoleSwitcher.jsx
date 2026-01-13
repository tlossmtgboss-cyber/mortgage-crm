/**
 * RoleSwitcher Component
 *
 * Dropdown component for users with multiple roles to switch between different views.
 * Only renders if the user has more than one role assigned.
 *
 * When switching roles:
 * - Navigation sidebar changes to show items for the selected role
 * - Dashboard widgets change to match the selected role's view
 * - Permissions remain the same (user keeps highest permissions from all roles)
 */

import React, { useState } from 'react';
import { usePermissions } from '../contexts/PermissionContext';
import './RoleSwitcher.css';

const RoleSwitcher = () => {
  const {
    assignedRoles,
    activeRole,
    canSwitchRoles,
    switchRole,
    loading
  } = usePermissions();

  const [isOpen, setIsOpen] = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [error, setError] = useState(null);

  // Don't render if user can't switch roles or data is loading
  if (loading || !canSwitchRoles || !assignedRoles || assignedRoles.length <= 1) {
    return null;
  }

  const handleRoleSwitch = async (roleId) => {
    if (roleId === activeRole?.id) {
      setIsOpen(false);
      return;
    }

    setIsSwitching(true);
    setError(null);

    const result = await switchRole(roleId);

    if (result.success) {
      setIsOpen(false);
      // Reload the page to apply the new role's navigation and dashboard
      window.location.reload();
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

  // Close dropdown when clicking outside
  const handleClickOutside = (e) => {
    if (!e.target.closest('.role-switcher')) {
      setIsOpen(false);
    }
  };

  React.useEffect(() => {
    if (isOpen) {
      document.addEventListener('click', handleClickOutside);
    }
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [isOpen]);

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
          {activeRole?.name || 'Select Role'}
        </span>
        <span className={`role-switcher-arrow ${isOpen ? 'open' : ''}`}>
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </span>
      </button>

      {isOpen && (
        <div className="role-switcher-dropdown">
          <div className="role-switcher-header">
            Switch View As
          </div>
          {error && (
            <div className="role-switcher-error">
              {error}
            </div>
          )}
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
