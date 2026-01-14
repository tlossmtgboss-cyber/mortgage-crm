import React, { useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useModules } from '../contexts/ModuleContext';
import { getNavigationForRole, roleHasDashboard } from '../config/roleConfig';
import { usePrefetch } from '../hooks/useQueries';
import NotificationBell from './NotificationBell';
import UpgradeModal from './UpgradeModal';
import RoleSwitcher from './RoleSwitcher';
import './Navigation.css';

/**
 * Navigation component with role-based menu items
 * Uses roleConfig.js to determine which navigation items to show for each role
 * Uses ModuleContext to determine which items are locked based on subscription
 */
function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const { effectiveRole, userRole, hasAnyPermission } = usePermissions();
  const { hasModule, getModule, loading: modulesLoading } = useModules();
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [selectedModule, setSelectedModule] = useState(null);
  const [openDropdown, setOpenDropdown] = useState(null);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setOpenDropdown(null);
        setOpenSubmenu(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Prefetch utilities for instant navigation
  const { prefetchLeads, prefetchLoans, prefetchDashboard, prefetchTasks, prefetchPortfolio, prefetchPartners } = usePrefetch();

  // Map paths to prefetch functions for instant data loading on hover
  const prefetchMap = useMemo(() => ({
    '/leads': prefetchLeads,
    '/loans': prefetchLoans,
    '/dashboard': prefetchDashboard,
    '/tasks': prefetchTasks,
    '/portfolio': prefetchPortfolio,
    '/referral-partners': prefetchPartners,
  }), [prefetchLeads, prefetchLoans, prefetchDashboard, prefetchTasks, prefetchPortfolio, prefetchPartners]);

  // Prefetch data when hovering over nav links (instant navigation!)
  const handleMouseEnter = useCallback((path) => {
    const prefetchFn = prefetchMap[path];
    if (prefetchFn) {
      prefetchFn();
    }
  }, [prefetchMap]);

  // Get navigation items for the current role, with module lock status
  // Don't show locked state while modules are still loading to avoid flash of upgrade badges
  // ADMIN users have full access - never lock any items for them
  const navItems = useMemo(() => {
    // Check if user is admin by any role indicator
    // This ensures admin always has full access regardless of module subscriptions
    const adminRoles = ['admin', 'site_admin', 'super_admin', 'owner'];
    const normalizedEffectiveRole = effectiveRole?.toLowerCase();
    const normalizedUserRole = userRole?.toLowerCase();
    const isAdmin = adminRoles.includes(normalizedEffectiveRole) ||
                    adminRoles.includes(normalizedUserRole);

    // IMPORTANT: Admin users (by userRole) always see admin navigation items
    // This allows admins to view as other roles but still have full navigation access
    // The effectiveRole only affects which items are highlighted/active, not which are shown
    const navigationRole = isAdmin ? 'admin' : effectiveRole;
    const items = getNavigationForRole(navigationRole);

    return items.map(item => ({
      ...item,
      // Admin users bypass all module restrictions - no locked items ever
      isLocked: !isAdmin && !modulesLoading && item.module && !hasModule(item.module)
    }));
  }, [effectiveRole, userRole, hasModule, modulesLoading]);

  // Handle click on locked nav item
  const handleLockedClick = useCallback((e, item) => {
    e.preventDefault();
    const moduleInfo = getModule(item.module);
    setSelectedModule(moduleInfo || { module_key: item.module, module_name: item.label });
    setUpgradeModalOpen(true);
  }, [getModule]);

  // Check if path is active (exact match)
  const isActive = (path) => location.pathname === path;

  // Check if path starts with prefix (for nested routes)
  const startsWithPath = (path) => location.pathname.startsWith(path);

  // Determine if a nav item is active
  const isNavItemActive = (item) => {
    // Check matchPaths first for complex matching
    if (item.matchPaths) {
      return item.matchPaths.some(p => startsWithPath(p)) || isActive(item.path);
    }
    return isActive(item.path);
  };

  // Render badge for task counts
  const renderBadge = (item) => {
    if (!item.badgeKey) return null;
    const count = taskCounts[item.badgeKey];
    if (!count || count === 0) return null;

    return (
      <span className={`nav-badge ${item.badgeClass || ''}`}>
        ({count})
      </span>
    );
  };

  // Check if user can see team-related actions
  const canViewTeam = hasAnyPermission(['team.view_all', 'team.view_team', 'team.manage_permissions']) ||
    userRole === 'management' || userRole === 'admin';


  // Render a dropdown submenu item
  const renderDropdownItem = (child, parentKey, index) => {
    if (child.children) {
      // Nested submenu
      const submenuKey = `${parentKey}-${index}`;
      const isSubmenuOpen = openSubmenu === submenuKey;
      const isSubmenuActive = child.children.some(c => location.pathname === c.path);

      return (
        <div
          key={submenuKey}
          className={`dropdown-submenu ${isSubmenuOpen ? 'open' : ''}`}
          onMouseEnter={() => setOpenSubmenu(submenuKey)}
          onMouseLeave={() => setOpenSubmenu(null)}
        >
          <button className={`dropdown-item has-submenu ${isSubmenuActive ? 'active' : ''}`}>
            {child.icon && <i className={`fas ${child.icon}`}></i>}
            <span>{child.label}</span>
            <i className="fas fa-chevron-right submenu-arrow"></i>
          </button>
          <div className="submenu-dropdown">
            {child.children.map((subChild, subIndex) => (
              <Link
                key={subIndex}
                to={subChild.path}
                className={`dropdown-item ${location.pathname === subChild.path ? 'active' : ''}`}
                onClick={() => {
                  setOpenDropdown(null);
                  setOpenSubmenu(null);
                }}
              >
                {subChild.label}
              </Link>
            ))}
          </div>
        </div>
      );
    }

    // Regular dropdown item
    return (
      <Link
        key={index}
        to={child.path}
        className={`dropdown-item ${location.pathname === child.path ? 'active' : ''}`}
        onClick={() => setOpenDropdown(null)}
      >
        {child.icon && <i className={`fas ${child.icon}`}></i>}
        <span>{child.label}</span>
      </Link>
    );
  };

  // Render a navigation item (with or without dropdown)
  const renderNavItem = (item) => {
    if (item.isLocked) {
      return (
        <button
          key={item.key}
          className="nav-link locked"
          onClick={(e) => handleLockedClick(e, item)}
          title={`Upgrade to unlock ${item.label}`}
        >
          {item.label}
          <span className="upgrade-badge">Upgrade</span>
        </button>
      );
    }

    // Item with children (dropdown menu)
    if (item.children && item.children.length > 0) {
      const isDropdownOpen = openDropdown === item.key;
      const isActive = isNavItemActive(item) || location.pathname.startsWith(item.path);

      return (
        <div
          key={item.key}
          className={`nav-dropdown ${isDropdownOpen ? 'open' : ''}`}
          ref={isDropdownOpen ? dropdownRef : null}
        >
          <button
            className={`nav-link dropdown-toggle ${isActive ? 'active' : ''}`}
            onClick={() => setOpenDropdown(isDropdownOpen ? null : item.key)}
          >
            {item.label}
            <i className={`fas fa-chevron-down dropdown-arrow ${isDropdownOpen ? 'rotated' : ''}`}></i>
          </button>
          {isDropdownOpen && (
            <div className="dropdown-menu">
              {item.children.map((child, index) => renderDropdownItem(child, item.key, index))}
            </div>
          )}
        </div>
      );
    }

    // Regular nav link
    return (
      <Link
        key={item.key}
        to={item.path}
        className={`nav-link ${isNavItemActive(item) ? 'active' : ''} ${item.adminOnly ? 'admin-link' : ''}`}
        onMouseEnter={() => handleMouseEnter(item.path)}
      >
        {item.label}
        {renderBadge(item)}
      </Link>
    );
  };

  return (
    <>
      <nav className="navigation">
        <div className="nav-container">
          <div className="nav-links">
            {navItems.map((item) => renderNavItem(item))}
          </div>

          <div className="nav-actions">
            <NotificationBell />
            {/* Multi-Role Switcher - shows when user has multiple assigned roles */}
            <RoleSwitcher />
            {/* Team Members - requires team permissions or management/admin role */}
            {canViewTeam && (
              <Link
                to="/team-members"
                className={`nav-link team-link ${isActive('/team-members') || startsWithPath('/team-members') ? 'active' : ''}`}
                title="Team Members"
              >
                Team
              </Link>
            )}
            <Link
              to="/support"
              className={`settings-link ${isActive('/support') ? 'active' : ''}`}
              title="Support"
            >
              Support
            </Link>
            <Link
              to="/settings"
              className={`settings-link ${isActive('/settings') ? 'active' : ''}`}
              title="Settings"
            >
              Settings
            </Link>
          </div>
        </div>
      </nav>

      {/* Upgrade Modal */}
      <UpgradeModal
        isOpen={upgradeModalOpen}
        onClose={() => setUpgradeModalOpen(false)}
        module={selectedModule}
      />
    </>
  );
}

export default Navigation;
