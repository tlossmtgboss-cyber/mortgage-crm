import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import NotificationBell from './NotificationBell';
import './Navigation.css';

function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { userRole } = usePermissions();

  const isActive = (path) => location.pathname === path;

  const renderBadge = (count) => {
    if (!count || count === 0) return null;
    return <span className="nav-badge">({count})</span>;
  };

  const handleLogout = () => {
    if (window.confirm('Are you sure you want to log out?')) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      navigate('/login');
    }
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
            to="/admin/documents"
            className={`nav-link ${isActive('/admin/documents') ? 'active' : ''}`}
          >
            Documents {renderBadge(taskCounts.pendingDocs)}
          </Link>
          <Link
            to="/smart-docs"
            className={`nav-link ${isActive('/smart-docs') || location.pathname.startsWith('/smart-docs/') ? 'active' : ''}`}
          >
            Smart Docs
          </Link>
          <Link
            to="/reconciliation"
            className={`nav-link ${isActive('/reconciliation') ? 'active' : ''}`}
          >
            Reconciliation {renderBadge(taskCounts.reconciliation)}
          </Link>
          <Link
            to="/communication-intelligence"
            className={`nav-link ${isActive('/communication-intelligence') || isActive('/email-intelligence') ? 'active' : ''}`}
          >
            Communication
          </Link>
          <Link
            to="/ai-outreach"
            className={`nav-link ${isActive('/ai-outreach') ? 'active' : ''}`}
          >
            AI Outreach
          </Link>
          <Link
            to="/conversation-intelligence"
            className={`nav-link ${isActive('/conversation-intelligence') || location.pathname.startsWith('/conversation-intelligence/') ? 'active' : ''}`}
          >
            Call QA
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

          {/* Compliance Dashboard - Management/Admin only */}
          {(userRole === 'management' || userRole === 'admin') && (
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
          <Link
            to="/profitability"
            className={`nav-link ${isActive('/profitability') ? 'active' : ''}`}
          >
            Profitability
          </Link>
        </div>

        <div className="nav-actions">
          <NotificationBell />
          {/* My Profile and Permissions moved to Settings page */}
          {(userRole === 'manager' || userRole === 'management') && (
            <Link
              to="/team-members"
              className={`nav-link team-link ${isActive('/team-members') || location.pathname.startsWith('/team-members') ? 'active' : ''}`}
              title="Team Members"
            >
              👥 Team
            </Link>
          )}
          {(userRole === 'management' || userRole === 'admin') && (
            <Link
              to="/admin/settings"
              className={`nav-link ${isActive('/admin/settings') ? 'active' : ''}`}
              title="Admin Settings"
            >
              🔧 Admin
            </Link>
          )}
          {(userRole === 'management' || userRole === 'admin') && (
            <Link
              to="/admin/domains"
              className={`nav-link ${isActive('/admin/domains') ? 'active' : ''}`}
              title="Custom Domains"
            >
              🌐 Domains
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
