import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import NotificationBell from './NotificationBell';
import './Navigation.css';

function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const { userRole } = usePermissions();
  const [marketingOpen, setMarketingOpen] = useState(false);
  const marketingRef = useRef(null);

  const isActive = (path) => location.pathname === path;

  // Marketing dropdown paths
  const marketingPaths = [
    '/ai-outreach',
    '/avatar-studio',
    '/communication-intelligence',
    '/email-intelligence',
    '/acquisition',
    '/conversation-intelligence'
  ];

  const isMarketingActive = marketingPaths.some(path =>
    location.pathname === path || location.pathname.startsWith(path + '/')
  );

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (marketingRef.current && !marketingRef.current.contains(event.target)) {
        setMarketingOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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

          {/* Marketing Dropdown */}
          <div className="nav-dropdown" ref={marketingRef}>
            <button
              className={`nav-link nav-dropdown-trigger ${isMarketingActive ? 'active' : ''}`}
              onClick={() => setMarketingOpen(!marketingOpen)}
            >
              Marketing
              <span className={`dropdown-arrow ${marketingOpen ? 'open' : ''}`}>▼</span>
            </button>
            {marketingOpen && (
              <div className="nav-dropdown-menu">
                <Link
                  to="/ai-outreach"
                  className={`nav-dropdown-item ${isActive('/ai-outreach') ? 'active' : ''}`}
                  onClick={() => setMarketingOpen(false)}
                >
                  AI Outreach
                </Link>
                <Link
                  to="/avatar-studio"
                  className={`nav-dropdown-item ${isActive('/avatar-studio') ? 'active' : ''}`}
                  onClick={() => setMarketingOpen(false)}
                >
                  Avatar Studio
                </Link>
                <Link
                  to="/communication-intelligence"
                  className={`nav-dropdown-item ${isActive('/communication-intelligence') || isActive('/email-intelligence') ? 'active' : ''}`}
                  onClick={() => setMarketingOpen(false)}
                >
                  Communication
                </Link>
                <Link
                  to="/acquisition"
                  className={`nav-dropdown-item ${isActive('/acquisition') ? 'active' : ''}`}
                  onClick={() => setMarketingOpen(false)}
                >
                  Acquisition
                </Link>
                <Link
                  to="/conversation-intelligence"
                  className={`nav-dropdown-item ${isActive('/conversation-intelligence') || location.pathname.startsWith('/conversation-intelligence/') ? 'active' : ''}`}
                  onClick={() => setMarketingOpen(false)}
                >
                  Call QA
                </Link>
              </div>
            )}
          </div>

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

          {/* Master Manager - Capacity & Talent OS */}
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
