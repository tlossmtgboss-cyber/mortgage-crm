import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import './Navigation.css';

function Navigation({ onToggleAssistant, assistantOpen }) {
  const location = useLocation();

  const isActive = (path) => location.pathname === path;

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
            Leads
          </Link>
          <Link
            to="/loans"
            className={`nav-link ${isActive('/loans') ? 'active' : ''}`}
          >
            Active Loans
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
            Tasks
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
            Partners
          </Link>
          <Link
            to="/ai-underwriter"
            className={`nav-link ${isActive('/ai-underwriter') ? 'active' : ''}`}
          >
            AI Underwriter
          </Link>
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
            className={`ai-assistant-toggle ${assistantOpen ? 'active' : ''}`}
            onClick={onToggleAssistant}
            title="Toggle AI Assistant"
          >
            AI Assistant
          </button>
        </div>
      </div>
    </nav>
  );
}

export default Navigation;
