import React from 'react';

import type { ApplicationResponse } from '../types';
import { AskAriaButton } from './AskAriaButton';

export interface POSSidebarProps {
  application: ApplicationResponse | null;
  onAskAria: () => void;
  documentCount?: number;
  onDocumentsClick?: () => void;
  activeNav?: 'application' | 'documents';
}

export const POSSidebar: React.FC<POSSidebarProps> = ({ application, onAskAria, documentCount = 0, onDocumentsClick, activeNav = 'application' }) => {
  const pct = application?.completion_pct ?? 0;

  return (
    <aside className="pos-sidebar">
      <div className="pos-sidebar__content">
        {/* Loan file summary card */}
        <div className="pos-loan-card">
          <div className="pos-loan-card__header">
            <span className="pos-loan-card__label">Loan File</span>
            <span className="pos-chip pos-chip--gold" style={{ fontSize: '10.5px', padding: '2px 8px' }}>
              In progress
            </span>
          </div>
          <div className="pos-loan-card__title">Purchase · Primary</div>
          <div className="pos-loan-card__id">
            {application?.id ? `PRN-${application.id.slice(0, 10).toUpperCase()}` : '—'}
          </div>
          <div className="pos-loan-card__progress">
            <div className="pos-loan-card__progress-header">
              <span className="pos-loan-card__progress-label">Application</span>
              <span className="pos-loan-card__progress-pct">{pct}%</span>
            </div>
            <div className="pos-progress-track">
              <div className="pos-progress-fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>

        {/* Ask Aria CTA */}
        <div style={{ marginBottom: 20 }}>
          <AskAriaButton onClick={onAskAria} />
        </div>

        {/* Navigation */}
        <nav className="pos-nav">
          <span className="pos-nav__section-title">Your Loan</span>
          <NavItem icon={<HomeIcon />} label="Home" />
          <NavItem icon={<FormIcon />} label="Application" active={activeNav === 'application'} />
          <NavItem icon={<UploadIcon />} label="Documents" badge={documentCount || undefined} onClick={onDocumentsClick} active={activeNav === 'documents'} />
          <NavItem icon={<ChecklistIcon />} label="Tasks" count={5} />
          <NavItem icon={<ChatIcon />} label="Messages" dot />
          <NavItem icon={<BookIcon />} label="Disclosures" />

          <span className="pos-nav__section-title">Tools</span>
          <NavItem icon={<CalcIcon />} label="Calculators" />
          <NavItem icon={<TimelineIcon />} label="Loan timeline" />
          <NavItem icon={<HelpIcon />} label="Help & support" />
        </nav>
      </div>
    </aside>
  );
};

const NavItem: React.FC<{
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  badge?: number;
  count?: number;
  dot?: boolean;
  onClick?: () => void;
}> = ({ icon, label, active, badge, count, dot, onClick }) => (
  <button
    type="button"
    className={`pos-nav__item${active ? ' pos-nav__item--active' : ''}`}
    onClick={onClick}
  >
    <span className="pos-nav__icon">{icon}</span>
    <span>{label}</span>
    {badge != null && <span className="pos-nav__badge">{badge}</span>}
    {count != null && <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--bt-text-muted)' }}>{count}</span>}
    {dot && <span className="pos-nav__dot" />}
  </button>
);

// ---- Icons (18×18, stroke-based) ----

const HomeIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
  </svg>
);

const FormIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
  </svg>
);

const UploadIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const ChecklistIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M9 11l3 3L22 4" />
    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
  </svg>
);

const ChatIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const BookIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);

const CalcIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <line x1="8" y1="6" x2="16" y2="6" />
    <line x1="8" y1="10" x2="10" y2="10" /><line x1="14" y1="10" x2="16" y2="10" />
    <line x1="8" y1="14" x2="10" y2="14" /><line x1="14" y1="14" x2="16" y2="14" />
    <line x1="8" y1="18" x2="10" y2="18" /><line x1="14" y1="18" x2="16" y2="18" />
  </svg>
);

const TimelineIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const HelpIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
