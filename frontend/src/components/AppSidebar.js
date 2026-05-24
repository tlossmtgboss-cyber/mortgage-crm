import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useModules } from '../contexts/ModuleContext';
import { getNavigationForRole } from '../config/roleConfig';
import { getUserData } from '../utils/tokenStore';
import './AppSidebar.css';

const SECTION_MAP = {
  pipeline: ['dashboard', 'leads', 'activeLoans', 'portfolio', 'rateMonitor'],
  workflow: ['tasks', 'workflowFlowchart', 'smartDocs', 'marketing', 'calendar'],
  intelligence: ['briefing', 'scorecard', 'goalTracker', 'partners', 'aiUnderwriter', 'market', 'profitability'],
  aiAgents: ['missionControl', 'agentDashboard', 'agentGym', 'opsManager', 'usageIntelligence'],
};

const SECTION_LABELS = {
  pipeline: null,
  workflow: 'Workflow',
  intelligence: 'Intelligence',
  aiAgents: 'AI Agents',
};

const ICONS = {
  dashboard: '■',
  leads: '●',
  activeLoans: '◆',
  portfolio: '★',
  rateMonitor: '↗',
  tasks: '✓',
  workflowFlowchart: '⬡',
  smartDocs: '☰',
  marketing: '★',
  calendar: '☷',
  briefing: '☼',
  scorecard: '⚞',
  goalTracker: '▲',
  partners: '◆',
  aiUnderwriter: '⚛',
  market: '◈',
  profitability: '$',
  missionControl: '⚙',
  agentDashboard: '⚛',
  agentGym: '⏣',
  opsManager: '⊞',
  usageIntelligence: '⟐',
};

const BADGE_CLASSES = {
  leads: 'green',
  activeLoans: 'primary',
  tasks: 'red',
  smartDocs: 'amber',
};

const ROLE_LABELS = {
  loan_officer: 'Loan Officer',
  admin: 'Admin',
  site_admin: 'Site Admin',
  processor: 'Processor',
  production_assistant: 'Production Asst.',
  concierge: 'Concierge',
  underwriter: 'Underwriter',
  closer: 'Closer',
  manager: 'Manager',
  executive: 'Executive',
};

function AppSidebar({ taskCounts = {} }) {
  const location = useLocation();
  const { effectiveRole } = usePermissions();
  const { hasModule } = useModules();
  const userData = getUserData();

  const roleNavKeys = useMemo(() => {
    const navItems = getNavigationForRole(effectiveRole || 'loan_officer');
    return navItems.map(item => item.key || Object.keys(item)[0]);
  }, [effectiveRole]);

  const isActive = (item) => {
    if (!item) return false;
    const path = item.path;
    if (path === '/dashboard') return location.pathname === '/dashboard' || location.pathname === '/';
    if (item.matchPaths) return item.matchPaths.some(mp => location.pathname.startsWith(mp));
    return location.pathname.startsWith(path);
  };

  const sections = useMemo(() => {
    const result = [];
    for (const [sectionKey, itemKeys] of Object.entries(SECTION_MAP)) {
      const items = itemKeys.filter(key => roleNavKeys.includes(key));
      if (items.length > 0) result.push({ key: sectionKey, label: SECTION_LABELS[sectionKey], items });
    }
    return result;
  }, [roleNavKeys]);

  const initials = userData
    ? `${(userData.first_name || '')[0] || ''}${(userData.last_name || '')[0] || ''}`.toUpperCase()
    : 'LO';

  const displayName = userData
    ? `${userData.first_name || ''} ${userData.last_name || ''}`.trim() || 'Loan Officer'
    : 'Loan Officer';

  const roleLabel = ROLE_LABELS[effectiveRole] || effectiveRole || 'Loan Officer';
  const roleBadge = (effectiveRole || 'loan_officer') === 'loan_officer' ? 'LO'
    : (effectiveRole || '').substring(0, 3).toUpperCase();

  return (
    <aside className="app-sidebar">
      <Link to="/aria-mobile" className="s-head" style={{ textDecoration: 'none', color: 'inherit' }}>
        <span className="s-logo">Aria</span>
        <span className="s-version">{roleBadge}</span>
      </Link>

      <nav className="s-nav">
        {sections.map((section) => (
          <div key={section.key}>
            {section.label && <div className="s-section">{section.label}</div>}
            {section.items.map((key) => {
              const navItems = getNavigationForRole(effectiveRole || 'loan_officer');
              const item = navItems.find(n => (n.key || Object.keys(n)[0]) === key);
              if (!item) return null;

              const badgeValue = taskCounts[item.badgeKey];
              const badgeClass = BADGE_CLASSES[key] || 'primary';
              const active = isActive(item);

              return (
                <Link
                  key={key}
                  to={item.path}
                  className={`s-item${active ? ' active' : ''}`}
                >
                  <span className="s-icon">{ICONS[key] || '●'}</span>
                  {item.label}
                  {badgeValue > 0 && (
                    <span className={`s-badge ${badgeClass}`}>{badgeValue}</span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="s-spacer" />

      <Link to="/settings" className="s-user" style={{ textDecoration: 'none', color: 'inherit' }}>
        <div className="s-av">{initials}</div>
        <div>
          <div style={{ fontWeight: 600, color: 'var(--bt-text-primary, #1A1F1B)' }}>{displayName}</div>
          <div style={{ fontSize: 11, color: 'var(--bt-text-muted, #8B8A7E)' }}>{roleLabel}</div>
        </div>
      </Link>
    </aside>
  );
}

export default AppSidebar;
