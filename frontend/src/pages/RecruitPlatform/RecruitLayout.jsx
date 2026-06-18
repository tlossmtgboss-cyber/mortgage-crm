import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useRecruitPlatform } from '../../contexts/RecruitPlatformContext';
import './RecruitingPlatform.css';

function NavIcon({ path }) {
  const icons = {
    dashboard: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
        <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
      </svg>
    ),
    jobs: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>
      </svg>
    ),
    interviews: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>
        <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
    ),
    settings: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
      </svg>
    ),
    website: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>
      </svg>
    ),
    kb: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
      </svg>
    ),
    chat: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
    ),
    embed: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
    ),
    license: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
        <polyline points="9 22 9 12 15 12 15 22"/>
      </svg>
    ),
    knowledgebase: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
      </svg>
    ),
    embed: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
    ),
    websitebuilder: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/>
      </svg>
    ),
  };
  return icons[path] || null;
}

export default function RecruitLayout() {
  const { recruitUser, isPlatformAdmin, logout } = useRecruitPlatform();
  const navigate = useNavigate();

  const orgName = isPlatformAdmin
    ? 'Platform Admin'
    : (recruitUser?.org_name || recruitUser?.org_slug || 'Recruiting');

  return (
    <div className="rp-layout">
      {/* Sidebar */}
      <div className="rp-sidebar">
        <div className="rp-sidebar-header">
          <div className="rp-logo-mark" />
          <div>
            <div className="rp-sidebar-title">Perennia Recruit</div>
            <div className="rp-sidebar-sub">{orgName}</div>
          </div>
        </div>

        <nav className="rp-nav">
          <NavLink to="/recruit/dashboard" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="dashboard" />
            Dashboard
          </NavLink>
          <NavLink to="/recruit/jobs" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="jobs" />
            Jobs
          </NavLink>
          <NavLink to="/recruit/interviews" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="interviews" />
            Interviews
          </NavLink>
          <NavLink to="/recruit/knowledge-base" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="knowledgebase" />
            Knowledge Base
          </NavLink>
          <NavLink to="/recruit/website-builder" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="websitebuilder" />
            Website Builder
          </NavLink>
          <NavLink to="/recruit/chat-widget" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="chat" />
            AI Chat Widget
          </NavLink>
          <NavLink to="/recruit/embed-settings" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
            <NavIcon path="embed" />
            Embed &amp; Share
          </NavLink>
          {isPlatformAdmin && (
            <NavLink to="/recruit/license-manager" className={({ isActive }) => `rp-nav-item${isActive ? ' active' : ''}`}>
              <NavIcon path="license" />
              License Manager
            </NavLink>
          )}
        </nav>

        <div className="rp-sidebar-footer">
          <div className="rp-user-info">
            <div className="rp-user-email">{recruitUser?.email || ''}</div>
          </div>
          <button className="rp-logout-btn" onClick={logout}>Sign out</button>
        </div>
      </div>

      {/* Main content */}
      <div className="rp-main">
        <Outlet />
      </div>
    </div>
  );
}
