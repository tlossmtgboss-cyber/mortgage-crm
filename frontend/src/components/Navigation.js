import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import './Navigation.css';

function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const navigate = useNavigate();

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
            Tasks {renderBadge(taskCounts.tasks)}
          </Link>
          <Link
            to="/calendar"
            className={`nav-link ${isActive('/calendar') ? 'active' : ''}`}
          >
            Calendar
          </Link>
          <Link
            to="/scorecard"
            className={`nav-link ${isActive('/scorecard') ? 'active' : ''}`}
          >
            Scorecard
          </Link>
          <Link
            to="/referral-partners"
            className={`nav-link ${isActive('/referral-partners') ? 'active' : ''}`}
          >
            Partners {renderBadge(taskCounts.partners)}
          </Link>
          <Link
            to="/ai-underwriter"
            className={`nav-link ${isActive('/ai-underwriter') ? 'active' : ''}`}
          >
            AI Underwriter
          </Link>
          <button
            className={`nav-link coach-link ${coachOpen ? 'active' : ''}`}
            onClick={onToggleCoach}
          >
            🏆 Coach
          </button>
        </div>

        <div className="nav-actions">
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
