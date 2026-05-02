/**
 * BorrowerPortal Page
 *
 * Unified borrower portal with MUM/Active Loan toggle.
 * Features:
 * - PortalInfoBar with LO info and loan details
 * - View mode toggle (Active Loan / MUM Servicing)
 * - Two-column layout with sidebar
 * - Chevron-style tab navigation
 */

import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import BorrowerPortalDashboard, { MumPortalDashboard } from '../components/Portal/BorrowerPortalDashboard';
import { borrowerPortalApi } from '../services/portalApi';
import { PortalProvider, usePortal } from '../contexts/PortalContext';
import { MilestoneTimeline } from '../components/Portal';
import HomeValueIntelligence from '../components/Portal/HomeValueIntelligence';
import './BorrowerPortal.css';
import './PURLPortal.css';
import '../styles/borrower-theme.css';

// ============================================
// CONSTANTS
// ============================================

const TABS = {
  ACTIVE: [
    { id: 'overview', label: 'Overview' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'documents', label: 'Documents' },
    { id: 'activity', label: 'Activity' },
    { id: 'contacts', label: 'Team' },
  ],
  MUM: [
    { id: 'overview', label: 'Overview' },
    { id: 'home-value', label: 'Home Value' },
    { id: 'documents', label: 'Documents' },
    { id: 'activity', label: 'Activity' },
    { id: 'contacts', label: 'Team' },
  ],
};

// ============================================
// HELPER FUNCTIONS
// ============================================

const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatDate = (dateStr) => {
  if (!dateStr) return 'TBD';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

const formatAddress = (address) => {
  if (!address) return 'Address not available';
  if (typeof address === 'string') return address;
  const parts = [address.street, address.city, address.state, address.zip_code].filter(Boolean);
  return parts.join(', ') || 'Address not available';
};

const getRelativeTime = (dateStr) => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
};

// ============================================
// VIEW MODE TOGGLE
// ============================================

const ViewModeToggle = ({ viewMode, onToggle, isMumEligible }) => {
  if (!isMumEligible) return null;

  return (
    <div className="view-mode-toggle">
      <button
        className={`toggle-btn ${viewMode === 'active' ? 'active' : ''}`}
        onClick={() => onToggle('active')}
      >
        Active Loan
      </button>
      <button
        className={`toggle-btn ${viewMode === 'mum' ? 'active' : ''}`}
        onClick={() => onToggle('mum')}
      >
        Home Services
      </button>
    </div>
  );
};

// ============================================
// TAB BUTTON
// ============================================

const TabButton = ({ label, isActive, onClick, badgeCount, isFirst, isLast }) => (
  <button
    className={`purl-tab-btn ${isActive ? 'active' : ''} ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''}`}
    onClick={onClick}
  >
    <span className="tab-label">{label}</span>
    {badgeCount > 0 && <span className="tab-notification-badge">{badgeCount}</span>}
  </button>
);

// ============================================
// PORTAL INFO BAR (Simplified)
// ============================================

const PortalInfoBar = ({ loan, loanOfficer, propertyAddress }) => (
  <div className="portal-info-bar">
    <div className="info-bar-content">
      <div className="info-bar-left">
        <div className="lo-info-section">
          <div className="lo-name">{loanOfficer?.name || 'Your Loan Officer'}</div>
          <div className="lo-contact">
            {loanOfficer?.email && (
              <a href={`mailto:${loanOfficer.email}`} className="lo-email">
                ✉ {loanOfficer.email}
              </a>
            )}
            {loanOfficer?.phone && (
              <a href={`tel:${loanOfficer.phone}`} className="lo-phone">
                📞 {loanOfficer.phone}
              </a>
            )}
          </div>
        </div>
        <div className="property-info-section">
          <span className="property-address">{formatAddress(propertyAddress)}</span>
        </div>
      </div>
      <div className="info-bar-right">
        <div className="loan-detail-item">
          <span className="detail-label">Loan Type</span>
          <span className="detail-value">{loan?.loan_type || 'Conventional'}</span>
        </div>
        <div className="loan-detail-item">
          <span className="detail-label">Loan Amount</span>
          <span className="detail-value highlight">{formatCurrency(loan?.loan_amount)}</span>
        </div>
        <div className="loan-detail-item">
          <span className="detail-label">Interest Rate</span>
          <span className="detail-value">{loan?.interest_rate ? `${loan.interest_rate}%` : 'TBD'}</span>
        </div>
        <div className="loan-detail-item">
          <span className="detail-label">Est. Closing</span>
          <span className="detail-value">{formatDate(loan?.target_close_date)}</span>
        </div>
      </div>
    </div>
  </div>
);

// ============================================
// DAYS COUNTER CARD
// ============================================

const DaysCounterCard = ({ closeDate, estimatedCloseDate }) => {
  const targetDate = closeDate || estimatedCloseDate;
  if (!targetDate) return null;

  const today = new Date();
  const close = new Date(targetDate);
  const daysLeft = Math.ceil((close - today) / (1000 * 60 * 60 * 24));
  const displayDays = Math.max(0, daysLeft);
  const digit1 = Math.floor(displayDays / 10);
  const digit2 = displayDays % 10;

  return (
    <div className="days-counter-card">
      <div className="days-counter-header">Days Until Closing</div>
      <div className="days-counter-display">
        <div className="days-digit">{digit1}</div>
        <div className="days-digit">{digit2}</div>
      </div>
      <div className="days-counter-label">
        {daysLeft <= 0 ? 'Closing Soon!' : daysLeft === 1 ? 'Day remaining' : 'Days remaining'}
      </div>
      <div className="days-counter-subtext">
        {closeDate ? 'Scheduled' : 'Estimated'}: {formatDate(targetDate)}
      </div>
    </div>
  );
};

// ============================================
// RECENT ACTIVITY SIDEBAR
// ============================================

const RecentActivitySidebar = ({ activities = [], onViewAll }) => (
  <div className="recent-activity-card">
    <div className="activity-card-header">
      <h3>Recent Activity</h3>
      {activities.length > 3 && (
        <button className="activity-view-all" onClick={onViewAll}>View All</button>
      )}
    </div>
    <div className="activity-list">
      {activities.length === 0 ? (
        <div className="activity-empty">No recent activity</div>
      ) : (
        activities.slice(0, 5).map((event, idx) => (
          <div key={event.id || idx} className="activity-item">
            <div className="activity-icon">●</div>
            <div className="activity-content">
              <div className="activity-title">{event.title || event.description}</div>
              <div className="activity-time">{getRelativeTime(event.created_at)}</div>
            </div>
          </div>
        ))
      )}
    </div>
  </div>
);

// ============================================
// TAB CONTENT SECTIONS
// ============================================

const DocumentsSection = ({ documentSummary }) => (
  <div className="documents-section">
    <div className="doc-progress-large">
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${documentSummary?.completion_rate || 0}%` }} />
      </div>
      <span className="progress-text">{documentSummary?.completion_rate || 0}% Complete</span>
    </div>
    <div className="doc-stats-grid">
      <div className="doc-stat-card approved">
        <span className="stat-value">{documentSummary?.by_status?.approved || 0}</span>
        <span className="stat-label">Approved</span>
      </div>
      <div className="doc-stat-card pending">
        <span className="stat-value">{documentSummary?.pending_review || 0}</span>
        <span className="stat-label">Pending</span>
      </div>
      <div className="doc-stat-card action">
        <span className="stat-value">{documentSummary?.needs_reupload || 0}</span>
        <span className="stat-label">Needs Action</span>
      </div>
    </div>
  </div>
);

const ActivitySection = ({ loanId }) => {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (loanId) {
      borrowerPortalApi.getRecentActivity(loanId, 20)
        .then(data => setActivities(data || []))
        .catch(() => setActivities([]))
        .finally(() => setLoading(false));
    }
  }, [loanId]);

  if (loading) return <div className="loading-placeholder">Loading activities...</div>;
  if (!activities.length) return <div className="empty-state">No activity yet</div>;

  return (
    <ul className="activity-feed">
      {activities.map((activity, idx) => (
        <li key={activity.id || idx} className="activity-item">
          <div className="activity-content">
            <p className="activity-description">{activity.description}</p>
            <span className="activity-time">{getRelativeTime(activity.created_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
};

const TeamContactsSection = ({ loanOfficer }) => {
  if (!loanOfficer) return <div className="empty-state">No team contacts available</div>;

  return (
    <div className="team-contacts">
      <div className="contact-card primary">
        <div className="contact-photo">
          <div className="contact-initials">
            {loanOfficer.name?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
          </div>
        </div>
        <div className="contact-info">
          <h4 className="contact-name">{loanOfficer.name}</h4>
          <p className="contact-title">{loanOfficer.title || 'Loan Officer'}</p>
        </div>
        <div className="contact-actions">
          {loanOfficer.phone && (
            <a href={`tel:${loanOfficer.phone}`} className="action-btn call">📞 Call</a>
          )}
          {loanOfficer.email && (
            <a href={`mailto:${loanOfficer.email}`} className="action-btn email">✉ Email</a>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================
// UNIFIED PORTAL CONTENT
// ============================================

function PortalContent({ portalData, hasMultiLoanContext = false }) {
  // Always call the hook unconditionally to satisfy React's rules of hooks
  const portalContext = usePortal();
  const [searchParams] = useSearchParams();
  // Only use the context values if we have multi-loan context
  const { currentLoan, switching } = hasMultiLoanContext ? portalContext : {};

  // Test mode support - allows ?testStage=MUM to test MUM view
  const testStage = searchParams.get('testStage');
  const effectiveStage = testStage || portalData?.lifecycle?.stage || 'ACTIVE';

  const [activeTab, setActiveTab] = useState('overview');
  const [activities, setActivities] = useState([]);
  const [viewMode, setViewMode] = useState(() => {
    // Default to MUM if in MUM stage, otherwise active
    return (effectiveStage === 'MUM' || effectiveStage === 'ANNUAL_REFRESH' || effectiveStage === 'FUNDED') ? 'mum' : 'active';
  });

  const loanId = currentLoan?.id || portalData?.loan_id;
  const stage = effectiveStage;

  // Check if MUM view is available (funded loans can toggle)
  const isMumEligible = ['MUM', 'ANNUAL_REFRESH', 'FUNDED'].includes(stage);
  const showMumView = viewMode === 'mum';

  // Get tabs based on view mode
  const tabs = showMumView ? TABS.MUM : TABS.ACTIVE;

  // Load activities
  useEffect(() => {
    if (loanId) {
      borrowerPortalApi.getRecentActivity(loanId, 10)
        .then(data => setActivities(data || []))
        .catch(() => setActivities([]));
    }
  }, [loanId]);

  // Prepare loan info
  const loanInfo = useMemo(() => ({
    loan_number: portalData?.loan_number,
    loan_amount: portalData?.loan_amount,
    loan_type: portalData?.loan_type,
    interest_rate: portalData?.interest_rate,
    target_close_date: portalData?.target_close_date,
    closing_date: portalData?.closing_date,
  }), [portalData]);

  // Loading state when switching loans
  if (switching) {
    return (
      <div className="portal-container">
        <div className="portal-switching-overlay">
          <div className="loader-spinner" />
          <p>Switching loan...</p>
        </div>
      </div>
    );
  }

  // Count new activities for badge
  const newActivityCount = activities.filter(a => {
    const date = new Date(a.created_at);
    return (new Date() - date) < 86400000;
  }).length;

  return (
    <div className="purl-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="header-content">
          <PortalInfoBar
            loan={loanInfo}
            loanOfficer={portalData?.loan_officer}
            propertyAddress={portalData?.property_address}
          />

          {/* View Mode Toggle */}
          <ViewModeToggle
            viewMode={viewMode}
            onToggle={setViewMode}
            isMumEligible={isMumEligible}
          />
        </div>
      </header>

      {/* Tabs */}
      <nav className="portal-nav chevron-tabs">
        {tabs.map((tab, idx) => (
          <TabButton
            key={tab.id}
            label={tab.label}
            isActive={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            badgeCount={
              tab.id === 'documents' ? (portalData?.documentSummary?.pending_review || 0) :
              tab.id === 'activity' ? newActivityCount : 0
            }
            isFirst={idx === 0}
            isLast={idx === tabs.length - 1}
          />
        ))}
      </nav>

      {/* Content */}
      <main className="portal-content">
        {activeTab === 'overview' && (
          <div className="tab-content overview-tab">
            <div className="portal-dashboard-layout">
              <div className="portal-main-content">
                {showMumView ? (
                  <MumPortalDashboard loanId={loanId} borrowerName={portalData?.borrower_name} />
                ) : (
                  <BorrowerPortalDashboard loanId={loanId} borrowerName={portalData?.borrower_name} />
                )}
              </div>
              <div className="portal-sidebar">
                {!showMumView && (
                  <DaysCounterCard
                    closeDate={loanInfo.closing_date}
                    estimatedCloseDate={loanInfo.target_close_date}
                  />
                )}
                <RecentActivitySidebar activities={activities} onViewAll={() => setActiveTab('activity')} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-content">
            <div className="portal-container">
              <MilestoneTimeline loanId={loanId} borrowerView={true} />
            </div>
          </div>
        )}

        {activeTab === 'documents' && (
          <div className="tab-content">
            <div className="portal-container">
              <DocumentsSection documentSummary={portalData?.documentSummary} />
            </div>
          </div>
        )}

        {activeTab === 'activity' && (
          <div className="tab-content">
            <div className="portal-container">
              <ActivitySection loanId={loanId} />
            </div>
          </div>
        )}

        {activeTab === 'home-value' && (
          <div className="tab-content">
            <div className="portal-container">
              <HomeValueIntelligence loanId={loanId} />
            </div>
          </div>
        )}

        {activeTab === 'contacts' && (
          <div className="tab-content">
            <div className="portal-container">
              <TeamContactsSection loanOfficer={portalData?.loan_officer} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// ============================================
// MAIN EXPORT
// ============================================

export default function BorrowerPortal() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const [portalData, setPortalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadPortal = async () => {
      try {
        setLoading(true);
        if (token) {
          const data = await borrowerPortalApi.getPortalByToken(token);
          setPortalData(data);
        } else {
          const loanId = searchParams.get('loan_id');
          if (loanId) {
            const data = await borrowerPortalApi.getDashboard(loanId);
            setPortalData(data);
          } else {
            setError('No portal access token or loan ID provided');
          }
        }
      } catch (err) {
        console.error('Portal load error:', err);
        setError(err.message || 'Failed to load portal');
      } finally {
        setLoading(false);
      }
    };
    loadPortal();
  }, [token, searchParams]);

  if (loading) {
    return (
      <div className="portal-page loading">
        <div className="portal-loader">
          <div className="loader-spinner" />
          <p>Loading your portal...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="portal-page error">
        <div className="portal-error-card">
          <span className="error-icon">🔒</span>
          <h1>Portal Access Error</h1>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const purlToken = portalData?.purl_token || token;
  const hasMultiLoanContext = !!purlToken;

  return (
    <div className="portal-page borrower-theme">
      {hasMultiLoanContext ? (
        <PortalProvider token={purlToken}>
          <PortalContent portalData={portalData} hasMultiLoanContext={true} />
        </PortalProvider>
      ) : (
        <PortalContent portalData={portalData} hasMultiLoanContext={false} />
      )}

      <footer className="portal-footer">
        <p>Powered by Perennia AI</p>
      </footer>
    </div>
  );
}
