/**
 * UserMenu Component
 *
 * Dropdown menu for user profile actions in the borrower portal.
 * Shows user info, profile link, settings, and logout.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import './UserMenu.css';

const UserMenu = ({
  user,
  onLogout,
  onProfileClick,
  onSettingsClick,
  onHelpClick,
  menuItems = [],
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

  const handleToggle = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const handleMenuItemClick = useCallback((handler) => {
    setIsOpen(false);
    if (handler) {
      handler();
    }
  }, []);

  const getInitials = (name) => {
    if (!name) return '?';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  const getAvatarColor = (name) => {
    if (!name) return '#94a3b8';
    const colors = [
      '#3b82f6', // blue
      '#B8924A', // violet
      '#ec4899', // pink
      '#f59e0b', // amber
      '#2D7A52', // emerald
      '#06b6d4', // cyan
      '#B8924A', // indigo
      '#f43f5e', // rose
    ];
    const hash = name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  };

  if (!user) {
    return null;
  }

  const defaultMenuItems = [
    {
      id: 'profile',
      label: 'My Profile',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      ),
      onClick: onProfileClick,
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      ),
      onClick: onSettingsClick,
    },
    {
      id: 'help',
      label: 'Help & Support',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
      onClick: onHelpClick,
    },
  ];

  const allMenuItems = [...defaultMenuItems.filter(item => item.onClick), ...menuItems];

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        className="user-menu-trigger"
        onClick={handleToggle}
        aria-label="User menu"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        {user.avatar ? (
          <img
            src={user.avatar}
            alt={user.name}
            className="user-avatar"
          />
        ) : (
          <div
            className="user-avatar-initials"
            style={{ backgroundColor: getAvatarColor(user.name) }}
          >
            {getInitials(user.name)}
          </div>
        )}
        <span className="user-name">{user.name}</span>
        <svg
          className={`chevron ${isOpen ? 'open' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div className="user-menu-panel" role="menu">
          <div className="user-menu-header">
            {user.avatar ? (
              <img
                src={user.avatar}
                alt={user.name}
                className="header-avatar"
              />
            ) : (
              <div
                className="header-avatar-initials"
                style={{ backgroundColor: getAvatarColor(user.name) }}
              >
                {getInitials(user.name)}
              </div>
            )}
            <div className="header-info">
              <span className="header-name">{user.name}</span>
              <span className="header-email">{user.email}</span>
            </div>
          </div>

          <div className="user-menu-divider" />

          <div className="user-menu-items">
            {allMenuItems.map((item) => (
              <button
                key={item.id}
                className="user-menu-item"
                onClick={() => handleMenuItemClick(item.onClick)}
                role="menuitem"
              >
                {item.icon && (
                  <span className="menu-item-icon">{item.icon}</span>
                )}
                <span className="menu-item-label">{item.label}</span>
              </button>
            ))}
          </div>

          {onLogout && (
            <>
              <div className="user-menu-divider" />
              <div className="user-menu-items">
                <button
                  className="user-menu-item logout"
                  onClick={() => handleMenuItemClick(onLogout)}
                  role="menuitem"
                >
                  <span className="menu-item-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                      <polyline points="16 17 21 12 16 7" />
                      <line x1="21" y1="12" x2="9" y2="12" />
                    </svg>
                  </span>
                  <span className="menu-item-label">Sign Out</span>
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

UserMenu.propTypes = {
  user: PropTypes.shape({
    name: PropTypes.string.isRequired,
    email: PropTypes.string.isRequired,
    avatar: PropTypes.string,
  }),
  onLogout: PropTypes.func,
  onProfileClick: PropTypes.func,
  onSettingsClick: PropTypes.func,
  onHelpClick: PropTypes.func,
  menuItems: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      icon: PropTypes.node,
      onClick: PropTypes.func.isRequired,
    })
  ),
};

export default UserMenu;
