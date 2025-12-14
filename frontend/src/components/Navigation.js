import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import NotificationBell from './NotificationBell';
import './Navigation.css';

function Navigation({ onToggleAssistant, onToggleCoach, assistantOpen, coachOpen, taskCounts = {} }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { userRole } = usePermissions();
  const [agentDropdownOpen, setAgentDropdownOpen] = useState(false);
  const agentDropdownRef = useRef(null);

  const isActive = (path) => location.pathname === path;
  const isAgentGovernanceActive = () => {
    return ['/agent-dashboard', '/voice-os-dashboard', '/ai-receptionist-dashboard'].some(
      path => location.pathname === path || location.pathname.startsWith(path)
    );
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (agentDropdownRef.current && !agentDropdownRef.current.contains(event.target)) {
        setAgentDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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

          {/* Agent Governance Dropdown */}
          <div className="nav-dropdown" ref={agentDropdownRef}>
            <button
              className={`nav-link nav-dropdown-trigger ${isAgentGovernanceActive() ? 'active' : ''}`}
              onClick={() => setAgentDropdownOpen(!agentDropdownOpen)}
            >
              Agent Governance
              <span className={`dropdown-arrow ${agentDropdownOpen ? 'open' : ''}`}>▾</span>
            </button>
            {agentDropdownOpen && (
              <div className="nav-dropdown-menu">
                <Link
                  to="/agent-dashboard"
                  className={`nav-dropdown-item ${isActive('/agent-dashboard') ? 'active' : ''}`}
                  onClick={() => setAgentDropdownOpen(false)}
                >
                  Dashboard
                </Link>
                <Link
                  to="/voice-os-dashboard"
                  className={`nav-dropdown-item ${isActive('/voice-os-dashboard') ? 'active' : ''}`}
                  onClick={() => setAgentDropdownOpen(false)}
                >
                  Voice OS
                </Link>
                <Link
                  to="/ai-receptionist-dashboard"
                  className={`nav-dropdown-item ${isActive('/ai-receptionist-dashboard') ? 'active' : ''}`}
                  onClick={() => setAgentDropdownOpen(false)}
                >
                  AI Receptionist
                </Link>
              </div>
            )}
          </div>
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
