import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import NotificationBell from './NotificationBell';
import './Navigation.css';

function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const { userRole, hasPermission, hasAnyPermission } = usePermissions();

  const isActive = (path) => location.pathname === path;
  const startsWithPath = (path) => location.pathname.startsWith(path);

  const renderBadge = (count) => {
    if (!count || count === 0) return null;
    return <span className="nav-badge">({count})</span>;
  };

  return (
    <nav className="navigation">
      <div className="nav-container">
        <div className="nav-links">
          <Link
            to="/dashboard"
            className={`nav-link ${isActive('/dashboard') ? 'active' : ''}`}
          >
            Dashboard
          </Link>
          <Link
            to="/leads"
            className={`nav-link ${isActive('/leads') ? 'active' : ''}`}
          >
            Leads {renderBadge(taskCounts.leads)}
          </Link>
          <Link
            to="/loans"
            className={`nav-link ${isActive('/loans') ? 'active' : ''}`}
          >
            Active Loans {renderBadge(taskCounts.loans)}
          </Link>
          <Link
            to="/portfolio"
            className={`nav-link ${isActive('/portfolio') ? 'active' : ''}`}
          >
            Portfolio
          </Link>
          <Link
            to="/tasks"
            className={`nav-link ${isActive('/tasks') ? 'active' : ''}`}
          >
            Tasks {taskCounts.urgentTasks > 0 && <span className="nav-badge urgent">({taskCounts.urgentTasks})</span>}
          </Link>
          <Link
            to="/reconciliation"
            className={`nav-link ${isActive('/reconciliation') ? 'active' : ''}`}
          >
            Reconciliation {renderBadge(taskCounts.reconciliation)}
          </Link>
          <Link
            to="/smart-docs"
            className={`nav-link ${isActive('/smart-docs') || location.pathname.startsWith('/smart-docs/') ? 'active' : ''}`}
          >
            Smart Docs
          </Link>

          <Link
            to="/marketing"
            className={`nav-link ${startsWithPath('/marketing') ? 'active' : ''}`}
          >
            Marketing
          </Link>

          <Link
            to="/calendar"
            className={`nav-link ${isActive('/calendar') ? 'active' : ''}`}
          >
            Calendar
          </Link>

          {/* Scorecard visible to all users */}
          <Link
            to="/scorecard"
            className={`nav-link ${isActive('/scorecard') ? 'active' : ''}`}
          >
            Scorecard
          </Link>

          {/* Referral Partners - visible to all users */}
          <Link
            to="/referral-partners"
            className={`nav-link ${isActive('/referral-partners') ? 'active' : ''}`}
          >
            Partners {renderBadge(taskCounts.partners)}
          </Link>

          {/* Compliance Dashboard - requires compliance.view or management role */}
          {(hasPermission('compliance.view') || userRole === 'management' || userRole === 'admin') && (
            <Link
              to="/compliance"
              className={`nav-link ${isActive('/compliance') ? 'active' : ''}`}
            >
              Compliance
            </Link>
          )}

          <Link
            to="/ai-underwriter"
            className={`nav-link ${isActive('/ai-underwriter') ? 'active' : ''}`}
          >
            AI Underwriter
          </Link>
          <Link
            to="/market"
            className={`nav-link ${isActive('/market') ? 'active' : ''}`}
          >
            Market
          </Link>
          {/* Profitability - requires reports.profitability or management/admin role */}
          {(hasPermission('reports.profitability') || userRole === 'management' || userRole === 'admin') && (
            <Link
              to="/profitability"
              className={`nav-link ${isActive('/profitability') ? 'active' : ''}`}
            >
              Profitability
            </Link>
          )}

          {/* Master Manager - Capacity & Talent OS - requires team.view_all or management/admin */}
          {(hasAnyPermission(['team.view_all', 'team.manage_permissions', 'capacity.view']) || userRole === 'management' || userRole === 'admin') && (
            <>
              <Link
                to="/master-manager"
                className={`nav-link ${isActive('/master-manager') && !isActive('/master-manager/recruiting') ? 'active' : ''}`}
              >
                Capacity
              </Link>
              <Link
                to="/master-manager/recruiting"
                className={`nav-link ${isActive('/master-manager/recruiting') ? 'active' : ''}`}
              >
                Recruiting
              </Link>
              <Link
                to="/partner-recruiting"
                className={`nav-link ${isActive('/partner-recruiting') || location.pathname.startsWith('/partner-recruiting/') ? 'active' : ''}`}
              >
                Partner Recruiting
              </Link>
            </>
          )}
        </div>

        <div className="nav-actions">
          <NotificationBell />
          {/* Team Members - requires team.view_all, team.view_team, or management/admin role */}
          {(hasAnyPermission(['team.view_all', 'team.view_team', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin') && (
            <Link
              to="/team-members"
              className={`nav-link team-link ${isActive('/team-members') || location.pathname.startsWith('/team-members') ? 'active' : ''}`}
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
            ⚙️
          </Link>
        </div>
      </div>
    </nav>
  );
}

export default Navigation;
