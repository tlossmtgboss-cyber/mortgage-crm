import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
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
            Portfolio {renderBadge(taskCounts.portfolio)}
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
            to="/calendar"
            className={`nav-link ${isActive('/calendar') ? 'active' : ''}`}
          >
            Calendar
          </Link>

          {/* PHASE 4: Scorecard only visible to Management */}
          {userRole === 'management' && (
            <Link
              to="/scorecard"
              className={`nav-link ${isActive('/scorecard') ? 'active' : ''}`}
            >
              Scorecard
            </Link>
          )}

          {/* PHASE 4: Partners only visible to Management */}
          {userRole === 'management' && (
            <Link
              to="/referral-partners"
              className={`nav-link ${isActive('/referral-partners') ? 'active' : ''}`}
            >
              Partners {renderBadge(taskCounts.partners)}
            </Link>
          )}
          <Link
            to="/ai-underwriter"
            className={`nav-link ${isActive('/ai-underwriter') ? 'active' : ''}`}
          >
            AI Underwriter
          </Link>
          <Link
            to="/ai-receptionist-dashboard"
            className={`nav-link ${isActive('/ai-receptionist-dashboard') ? 'active' : ''}`}
          >
            AI Receptionist
          </Link>
        </div>

        <div className="nav-actions">
          <Link
            to="/apply"
            className={`nav-link application-link ${isActive('/apply') ? 'active' : ''}`}
            title="Buyer Application"
          >
            📝 Application
          </Link>
          <button
            className={`nav-link coach-link ${coachOpen ? 'active' : ''}`}
            onClick={onToggleCoach}
          >
            🏆 Coach
          </button>
          <Link
            to="/my-profile"
            className={`nav-link profile-link ${isActive('/my-profile') ? 'active' : ''}`}
            title="My Profile"
          >
            👤 My Profile
          </Link>
          <Link
            to="/my-permissions"
            className={`nav-link permissions-link ${isActive('/my-permissions') ? 'active' : ''}`}
            title="My Permissions"
          >
            🔐 My Permissions
          </Link>
          {(userRole === 'manager' || userRole === 'management') && (
            <Link
              to="/team-members"
              className={`nav-link team-link ${isActive('/team-members') || location.pathname.startsWith('/team-members') ? 'active' : ''}`}
              title="Team Members"
            >
              👥 Team
            </Link>
          )}
          <Link
            to="/settings"
            className={`settings-link ${isActive('/settings') ? 'active' : ''}`}
            title="Settings"
          >
            ⚙️
          </Link>
          <button
            className="logout-btn"
            onClick={handleLogout}
            title="Logout"
          >
            🚪 Logout
          </button>
        </div>
      </div>
    </nav>
  );
}

export default Navigation;
