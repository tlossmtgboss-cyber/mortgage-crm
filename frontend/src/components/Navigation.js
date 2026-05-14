import React, { useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useModules } from '../contexts/ModuleContext';
import { useBranding } from '../contexts/BrandingContext';
import { getNavigationForRole, roleHasDashboard, isMasterAdmin, getMasterAdminNavigation } from '../config/roleConfig';
import { usePrefetch } from '../hooks/useQueries';
import NotificationBell from './NotificationBell';
import UpgradeModal from './UpgradeModal';
import RoleSwitcher from './RoleSwitcher';
import ThemeToggle from './ThemeToggle';
import './Navigation.css';
import { getUserData } from '../utils/tokenStore';

/**
 * Navigation component with role-based menu items
 * Uses roleConfig.js to determine which navigation items to show for each role
 * Uses ModuleContext to determine which items are locked based on subscription
 */
function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const { effectiveRole, userRole, viewAsRole, hasAnyPermission } = usePermissions();
  const { hasModule, getModule, loading: modulesLoading } = useModules();
  const { brandName, logoUrl } = useBranding();
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [selectedModule, setSelectedModule] = useState(null);
  const [openDropdown, setOpenDropdown] = useState(null);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
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

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  // Prevent body scroll when mobile menu is open
  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [mobileMenuOpen]);

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

  // Get user email to check for master admin
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

  // Check if current user is the master admin (admin@perenniaai.com)
  const isMasterAdminUser = useMemo(() => {
    return isMasterAdmin(userEmail);
  }, [userEmail]);

  // viewAsRole comes from PermissionContext (reactive when admin switches roles)

  // Get navigation items for the current role, with module lock status
  // Don't show locked state while modules are still loading to avoid flash of upgrade badges
  // Platform Admin users have full access - never lock any items for them
  // Site Admin users get their own limited navigation (not full admin)
  // Master Admin (admin@perenniaai.com) gets consolidated dropdown navigation (unless viewing as another role)
  const navItems = useMemo(() => {
    // Master admin viewing as another role - show that role's navigation
    if (isMasterAdminUser && viewAsRole && viewAsRole !== 'admin') {
      const items = getNavigationForRole(viewAsRole);
      return items.map(item => ({
        ...item,
        isLocked: false // Master admin bypass all module restrictions
      }));
    }

    // Master admin (not viewing as another role) gets special consolidated navigation
    if (isMasterAdminUser && (!viewAsRole || viewAsRole === 'admin')) {
      return getMasterAdminNavigation();
    }

    // Check if user is PLATFORM admin (developer with god-mode)
    // site_admin is NOT a platform admin - they get their own limited navigation
    const platformAdminRoles = ['admin', 'super_admin'];
    const normalizedEffectiveRole = effectiveRole?.toLowerCase();
    const normalizedUserRole = userRole?.toLowerCase();
    const isPlatformAdmin = platformAdminRoles.includes(normalizedEffectiveRole) ||
                            platformAdminRoles.includes(normalizedUserRole);

    // Site admins and other roles use their own role-specific navigation
    // Only platform admins get the full 'admin' navigation
    const navigationRole = isPlatformAdmin ? 'admin' : effectiveRole;
    const items = getNavigationForRole(navigationRole);

    return items.map(item => ({
      ...item,
      // TEMPORARY: All users get full access until proper tool segregation is implemented
      // Original: isLocked: !isPlatformAdmin && !modulesLoading && item.module && !hasModule(item.module)
      isLocked: false
    }));
  }, [effectiveRole, userRole, hasModule, modulesLoading, isMasterAdminUser, viewAsRole]);

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


  // Render badge for dropdown items (for master admin navigation)
  const renderDropdownBadge = (item) => {
    if (!item.badgeKey) return null;
    const count = taskCounts[item.badgeKey];
    if (!count || count === 0) return null;

    return (
      <span className={`nav-badge dropdown-badge ${item.badgeClass || ''}`}>
        ({count})
      </span>
    );
  };

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

    // Regular dropdown item (with optional badge support for master admin nav)
    return (
      <Link
        key={index}
        to={child.path}
        className={`dropdown-item ${location.pathname === child.path ? 'active' : ''}`}
        onClick={() => setOpenDropdown(null)}
      >
        {child.icon && <i className={`fas ${child.icon}`}></i>}
        <span>{child.label}</span>
        {renderDropdownBadge(child)}
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
          {/* Mobile hamburger button */}
          <button
            className={`mobile-menu-btn ${mobileMenuOpen ? 'active' : ''}`}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            <span className="hamburger-line" />
            <span className="hamburger-line" />
            <span className="hamburger-line" />
          </button>

          {/* Brand logo / name — driven by per-org WhiteLabelConfig */}
          {logoUrl ? (
            <Link to="/aria-mobile" className="nav-brand" title="Aria">
              <img src={logoUrl} alt={brandName} className="nav-brand-logo" />
            </Link>
          ) : (
            <Link to="/aria-mobile" className="nav-brand nav-brand-text" title="Aria">
              Aria
            </Link>
          )}

          <div className="nav-links">
            {navItems.map((item) => renderNavItem(item))}
          </div>

          <div className="nav-actions">
            <NotificationBell />
            {/* Multi-Role Switcher - shows when user has multiple assigned roles */}
            <RoleSwitcher />
            <ThemeToggle />
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

      {/* Mobile drawer overlay */}
      {mobileMenuOpen && (
        <div className="mobile-menu-overlay" onClick={() => setMobileMenuOpen(false)} />
      )}

      {/* Mobile slide-out drawer */}
      <div className={`mobile-menu-drawer ${mobileMenuOpen ? 'open' : ''}`}>
        <div className="mobile-menu-header">
          <span className="mobile-menu-title">Menu</span>
          <button
            className="mobile-menu-close"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
          >
            ✕
          </button>
        </div>
        <div className="mobile-menu-items">
          {navItems.map((item) => {
            if (item.children && item.children.length > 0) {
              return (
                <div key={item.key} className="mobile-menu-group">
                  <div className="mobile-menu-group-label">{item.label}</div>
                  {item.children.map((child, idx) => {
                    if (child.children) {
                      return child.children.map((sub, subIdx) => (
                        <Link
                          key={`${idx}-${subIdx}`}
                          to={sub.path}
                          className={`mobile-menu-item mobile-menu-sub ${location.pathname === sub.path ? 'active' : ''}`}
                          onClick={() => setMobileMenuOpen(false)}
                        >
                          {sub.label}
                        </Link>
                      ));
                    }
                    return (
                      <Link
                        key={idx}
                        to={child.path}
                        className={`mobile-menu-item ${location.pathname === child.path ? 'active' : ''}`}
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        {child.icon && <i className={`fas ${child.icon}`} />}
                        {child.label}
                      </Link>
                    );
                  })}
                </div>
              );
            }
            return (
              <Link
                key={item.key}
                to={item.path}
                className={`mobile-menu-item ${isNavItemActive(item) ? 'active' : ''}`}
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.label}
                {renderBadge(item)}
              </Link>
            );
          })}
        </div>
        <div className="mobile-menu-footer">
          <Link
            to="/settings"
            className="mobile-menu-item"
            onClick={() => setMobileMenuOpen(false)}
          >
            Settings
          </Link>
        </div>
      </div>

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
