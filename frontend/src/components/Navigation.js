import React, { useMemo, useCallback, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useModules } from '../contexts/ModuleContext';
import { getNavigationForRole, roleHasDashboard } from '../config/roleConfig';
import { usePrefetch } from '../hooks/useQueries';
import NotificationBell from './NotificationBell';
import UpgradeModal from './UpgradeModal';
import './Navigation.css';

/**
 * Navigation component with role-based menu items
 * Uses roleConfig.js to determine which navigation items to show for each role
 * Uses ModuleContext to determine which items are locked based on subscription
 */
function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const { effectiveRole, userRole, hasAnyPermission, viewAsRole, updateViewAsRole } = usePermissions();
  const { hasModule, getModule, loading: modulesLoading } = useModules();
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [selectedModule, setSelectedModule] = useState(null);

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
  const navItems = useMemo(() => {
    const items = getNavigationForRole(effectiveRole);
    return items.map(item => ({
      ...item,
      isLocked: !modulesLoading && item.module && !hasModule(item.module)
    }));
  }, [effectiveRole, hasModule, modulesLoading]);

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

  // Check if user is admin (can switch role views)
  const isAdmin = userRole === 'admin' || userRole === 'management';

  // Available roles for preview
  const previewRoles = [
    { value: 'default', label: 'Admin View' },
    { value: 'loan_officer', label: 'Loan Officer' },
    { value: 'processor', label: 'Processor' },
    { value: 'production_assistant', label: 'Production Assistant' },
    { value: 'concierge', label: 'Concierge' },
    { value: 'manager', label: 'Manager' },
  ];

  return (
    <>
      <nav className="navigation">
        <div className="nav-container">
          <div className="nav-links">
            {navItems.map((item) => (
              item.isLocked ? (
                <button
                  key={item.key}
                  className="nav-link locked"
                  onClick={(e) => handleLockedClick(e, item)}
                  title={`Upgrade to unlock ${item.label}`}
                >
                  {item.label}
                  <span className="upgrade-badge">Upgrade</span>
                </button>
              ) : (
                <Link
                  key={item.key}
                  to={item.path}
                  className={`nav-link ${isNavItemActive(item) ? 'active' : ''} ${item.adminOnly ? 'admin-link' : ''}`}
                  onMouseEnter={() => handleMouseEnter(item.path)}
                >
                  {item.label}
                  {renderBadge(item)}
                </Link>
              )
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
            {/* Role Preview Selector - admin only */}
            {isAdmin && (
              <div className={`role-preview-selector ${viewAsRole && viewAsRole !== 'default' ? 'active' : ''}`}>
                <select
                  value={viewAsRole || 'default'}
                  onChange={(e) => updateViewAsRole(e.target.value === 'default' ? null : e.target.value)}
                  title="Preview as different role"
                >
                  {previewRoles.map(role => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>
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
