import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import './RecruitingPlatform.css';

const NAV_ITEMS = [
  { path: '/recruiting', label: 'Pipeline', icon: '⬡', exact: true },
  { path: '/recruiting/interviews', label: 'Interviews', icon: '⬡' },
  { path: '/recruiting/milestones', label: 'Milestones', icon: '⬡' },
  { path: '/recruiting/analytics', label: 'Analytics', icon: '⬡' },
];

export default function RecruitingPlatformLayout({ children }) {
  const navigate = useNavigate();

  return (
    <div className="rp-layout">
      <aside className="rp-sidebar">
        <div className="rp-sidebar-header">
          <span className="rp-logo-mark" />
          <div>
            <div className="rp-sidebar-title">Recruiting</div>
            <div className="rp-sidebar-sub">Platform</div>
          </div>
        </div>

        <nav className="rp-nav">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.exact}
              className={({ isActive }) =>
                `rp-nav-item${isActive ? ' rp-nav-item--active' : ''}`
              }
            >
              <span className="rp-nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="rp-sidebar-footer">
          <button
            className="rp-nav-item rp-nav-item--ghost"
            onClick={() => navigate('/master-manager')}
          >
            <span className="rp-nav-icon">←</span>
            Back to CRM
          </button>
        </div>
      </aside>

      <main className="rp-main">{children}</main>
    </div>
  );
}
