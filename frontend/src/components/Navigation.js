import React, { useMemo, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { getNavigationForRole, roleHasDashboard } from '../config/roleConfig';
import { usePrefetch } from '../hooks/useQueries';
import NotificationBell from './NotificationBell';
import './Navigation.css';

/**
 * Navigation component with role-based menu items
 * Uses roleConfig.js to determine which navigation items to show for each role
 */
function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const { effectiveRole, userRole, hasAnyPermission } = usePermissions();

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

  // Get navigation items for the current role
  const navItems = useMemo(() => {
    return getNavigationForRole(effectiveRole);
  }, [effectiveRole]);

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

  return (
    <nav className="navigation">
      <div className="nav-container">
        <div className="nav-links">
          {navItems.map((item) => (
            <Link
              key={item.key}
              to={item.path}
              className={`nav-link ${isNavItemActive(item) ? 'active' : ''}`}
              onMouseEnter={() => handleMouseEnter(item.path)}
            >
              {item.label}
              {renderBadge(item)}
            </Link>
          ))}
        </div>

        <div className="nav-actions">
          <NotificationBell />
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
            to="/settings"
            className={`settings-link ${isActive('/settings') ? 'active' : ''}`}
            title="Settings"
          >
            Settings
          </Link>
        </div>
      </div>
    </nav>
  );
}

export default Navigation;
