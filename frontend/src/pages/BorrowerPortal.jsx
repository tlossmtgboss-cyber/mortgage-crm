/**
 * BorrowerPortal Page
 *
 * Public-facing borrower portal that displays loan progress,
 * milestones, documents, and timeline information.
 * Supports multi-loan switching for borrowers with multiple loans.
 *
 * Enhanced UI with:
 * - PortalInfoBar with LO info and loan details (mirrors ActiveLoanPortal)
 * - HeaderMilestoneProgress step indicators
 * - Two-column layout with sidebar (DaysCounterCard, RecentActivitySidebar)
 * - Chevron-style tab navigation
 * - MUM features for closed loans
 */

import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import BorrowerPortalDashboard, { MumPortalDashboard } from '../components/Portal/BorrowerPortalDashboard';
import { borrowerPortalApi, closeOnTimeApi, lifecycleApi } from '../services/portalApi';
import { PortalProvider, usePortal } from '../contexts/PortalContext';
import {
  LoanSelector,
  PortalModeIndicator,
  TabPanel,
  PORTAL_TABS,
  MilestoneTimeline,
} from '../components/Portal';
import HomeValueIntelligence from '../components/Portal/HomeValueIntelligence';
import './BorrowerPortal.css';
import './PURLPortal.css'; // Import ActiveLoanPortal styles

// ============================================
// HELPER FUNCTIONS
// ============================================

/**
 * Format currency
 */
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

/**
 * Format date
 */
const formatDate = (dateStr) => {
  if (!dateStr) return 'TBD';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

/**
 * Format address
 */
const formatAddress = (address) => {
  if (!address) return 'Address not available';
  if (typeof address === 'string') return address;
  const parts = [address.street, address.city, address.state, address.zip_code].filter(Boolean);
  return parts.join(', ') || 'Address not available';
};

/**
 * Calculate days until close
 */
const daysUntilClose = (closeDate) => {
  if (!closeDate) return null;
  const today = new Date();
  const close = new Date(closeDate);
  const diffTime = close - today;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays;
};

/**
 * Get relative time string
 */
const getRelativeTime = (dateStr) => {
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
// CHEVRON TAB BUTTON (mirrors ActiveLoanPortal)
// ============================================
const TabButton = ({ label, isActive, onClick, hasNotification, badgeCount, isFirst, isLast }) => (
  <button
    className={`purl-tab-btn ${isActive ? 'active' : ''} ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''}`}
    onClick={onClick}
  >
    <span className="tab-label">{label}</span>
    {badgeCount > 0 ? (
      <span className="tab-notification-badge">{badgeCount}</span>
    ) : (
      hasNotification && <span className="tab-notification-dot" />
    )}
  </button>
);

// ============================================
// PORTAL INFO BAR (LO Info + Loan Details)
// ============================================
const PortalInfoBar = ({ loan, loanOfficer, propertyAddress }) => {
  const loName = loanOfficer?.name || 'Your Loan Officer';
  const loEmail = loanOfficer?.email || '';
  const loPhone = loanOfficer?.phone || '';

  return (
    <div className="portal-info-bar">
      <div className="info-bar-content">
        {/* Left Side - Loan Officer Info */}
        <div className="info-bar-left">
          <div className="lo-info-section">
            <div className="lo-name">{loName}</div>
            <div className="lo-contact">
              {loEmail && (
                <a href={`mailto:${loEmail}`} className="lo-email">
                  <span className="contact-icon">✉</span> {loEmail}
                </a>
              )}
              {loPhone && (
                <a href={`tel:${loPhone}`} className="lo-phone">
                  <span className="contact-icon">📞</span> {loPhone}
                </a>
              )}
            </div>
          </div>
          <div className="property-info-section">
            <span className="property-address">{formatAddress(propertyAddress)}</span>
          </div>
        </div>

        {/* Right Side - Loan Details */}
        <div className="info-bar-right">
          <div className="loan-detail-item">
            <span className="detail-label">Purpose</span>
            <span className="detail-value">{loan?.loan_purpose || 'Purchase'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Loan Type</span>
            <span className="detail-value">{loan?.loan_type || 'Conventional'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Term</span>
            <span className="detail-value">{loan?.loan_term || '30'} Years</span>
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
            <span className="detail-label">Rate Lock</span>
            <span className="detail-value">{loan?.rate_lock_date ? formatDate(loan.rate_lock_date) : 'Not Locked'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Est. Closing</span>
            <span className="detail-value">{formatDate(loan?.target_close_date)}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Scheduled</span>
            <span className="detail-value">{loan?.closing_date ? formatDate(loan.closing_date) : 'TBD'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================
// HEADER MILESTONE PROGRESS (Step Indicators)
// ============================================
const HeaderMilestoneProgress = ({ stage, leadStage }) => {
  const crmStage = leadStage?.toLowerCase() || '';
  const currentStage = stage?.toLowerCase() || '';

  // Check if we're in the lead stage (pre-approval journey)
  const isLeadStage = ['prospect', 'lead', 'preapproval', 'pre_approval'].includes(currentStage) ||
    (crmStage && !['under_contract', 'won', 'lost'].includes(crmStage));

  // Define lead journey milestones
  const leadStages = [
    { id: 'app_completed', label: 'Application', shortLabel: 'App Completed' },
    { id: 'docs_requested', label: 'Docs Requested', shortLabel: 'Docs Requested' },
    { id: 'docs_approved', label: 'Docs Approved', shortLabel: 'Docs Approved' },
    { id: 'pre_approved', label: 'Pre-Approved', shortLabel: 'Pre Approved' },
  ];

  // Define full loan journey stages
  const loanStages = [
    { id: 'processing', label: 'Processing', shortLabel: 'Processing' },
    { id: 'underwriting', label: 'Underwriting', shortLabel: 'Underwriting' },
    { id: 'approval', label: 'Approval', shortLabel: 'Approved' },
    { id: 'clear_to_close', label: 'Clear to Close', shortLabel: 'Clear to Close' },
    { id: 'closing', label: 'Closing', shortLabel: 'Closing' },
  ];

  const stages = isLeadStage ? leadStages : loanStages;

  // Determine current stage index
  const getCurrentStageIndex = () => {
    if (isLeadStage) {
      const stageMap = {
        'prospect': 0, 'lead': 0, 'new': 1, 'contacted': 1,
        'qualified': 2, 'nurturing': 2, 'pre_qualified': 3, 'pre_approved': 4,
      };
      return stageMap[crmStage] ?? stageMap[currentStage] ?? 1;
    } else {
      const stageMap = {
        'processing': 1, 'underwriting': 2,
        'conditional_approval': 3, 'approved': 3, 'approval': 3,
        'clear_to_close': 4, 'ctc': 4,
        'closing': 5, 'docs_out': 5, 'docs_back': 5, 'funded': 5,
      };
      return stageMap[currentStage] ?? 0;
    }
  };

  const currentIndex = getCurrentStageIndex();

  return (
    <div className="header-milestone-progress">
      <div className="milestone-steps">
        {stages.map((stageItem, index) => {
          const isComplete = index < currentIndex;
          const isCurrent = index === currentIndex;
          const isPending = index > currentIndex;

          return (
            <div
              key={stageItem.id}
              className={`milestone-step ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} ${isPending ? 'pending' : ''}`}
            >
              <div className="step-indicator">
                {isComplete ? (
                  <span className="step-check">✓</span>
                ) : (
                  <span className="step-number">{index + 1}</span>
                )}
              </div>
              <span className="step-label">{stageItem.shortLabel}</span>
              {index < stages.length - 1 && (
                <div className={`step-connector ${isComplete ? 'complete' : ''}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ============================================
// DAYS COUNTER CARD (Sidebar)
// ============================================
const DaysCounterCard = ({ closeDate, estimatedCloseDate }) => {
  const targetDate = closeDate || estimatedCloseDate;
  const daysLeft = daysUntilClose(targetDate);

  const displayDays = daysLeft !== null && daysLeft >= 0 ? daysLeft : 0;
  const digit1 = Math.floor(displayDays / 10);
  const digit2 = displayDays % 10;

  return (
    <div className="days-counter-card">
      <div className="days-counter-header">Days Until Closing</div>
      <div className="days-counter-display">
        <div className="days-digit animated">{digit1}</div>
        <div className="days-digit animated">{digit2}</div>
      </div>
      <div className="days-counter-label">
        {daysLeft === null ? 'Closing date TBD' :
         daysLeft === 0 ? 'Closing Today!' :
         daysLeft < 0 ? 'Past closing date' :
         daysLeft === 1 ? 'Day remaining' : 'Days remaining'}
      </div>
      {targetDate && (
        <div className="days-counter-subtext">
          {closeDate ? 'Scheduled' : 'Estimated'}: {formatDate(targetDate)}
        </div>
      )}
    </div>
  );
};

// ============================================
// RECENT ACTIVITY SIDEBAR
// ============================================
const RecentActivitySidebar = ({ activities, onViewAll }) => {
  const typeIcons = {
    document: '📄', task: '✓', milestone: '🏆',
    message: '💬', status: '📊', application: '📝'
  };

  const getIconClass = (type) => {
    const typeMap = {
      document: 'document', task: 'task', milestone: 'milestone',
      message: 'message', status: 'status', application: 'document'
    };
    return typeMap[type] || 'status';
  };

  const isNew = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    return (now - date) < 86400000;
  };

  return (
    <div className="recent-activity-card">
      <div className="activity-card-header">
        <h3>Recent Activity</h3>
        {activities.length > 5 && (
          <button className="activity-view-all" onClick={onViewAll}>
            View All
          </button>
        )}
      </div>
      <div className="activity-list">
        {activities.length === 0 ? (
          <div className="activity-empty">No recent activity</div>
        ) : (
          activities.slice(0, 5).map((event, index) => (
            <div key={event.id || index} className="activity-item">
              <div className={`activity-icon ${getIconClass(event.activity_type || event.event_type)}`}>
                {typeIcons[event.activity_type || event.event_type] || '●'}
              </div>
              <div className="activity-content">
                <div className="activity-title">
                  {event.title || event.description}
                  {isNew(event.created_at) && (
                    <span className="activity-new-badge">New</span>
                  )}
                </div>
                {event.description && event.title && (
                  <div className="activity-description">{event.description}</div>
                )}
                <div className="activity-time">{getRelativeTime(event.created_at)}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// ============================================
// CONTACT LO CARD
// ============================================
const ContactLOCard = ({ onSchedule }) => (
  <div className="contact-lo-card">
    <div className="contact-lo-content">
      <h3>Questions about your loan?</h3>
      <p>Your loan officer is here to help guide you through the process.</p>
    </div>
    <button className="schedule-call-btn" onClick={onSchedule}>
      <span className="btn-icon">📅</span>
      Schedule a Call
    </button>
  </div>
);

/**
 * Get tabs based on portal stage
 */
function getPortalTabs(isMumStage) {
  if (isMumStage) {
    return PORTAL_TABS.SERVICING;
  }
  return PORTAL_TABS.TRANSACTION;
}

/**
 * Enhanced Portal Content with Two-Column Layout
 * Mirrors the ActiveLoanPortal design
 */
function EnhancedPortalContent({ initialPortalData }) {
  const { currentLoan, portalMode, switching, hasMultipleLoans } = usePortal();
  const [activeTab, setActiveTab] = useState('overview');
  const [closeOnTimeData, setCloseOnTimeData] = useState(null);
  const [milestones, setMilestones] = useState([]);
  const [activities, setActivities] = useState([]);

  // Use currentLoan from context if available, otherwise use initial data
  const activeLoanId = currentLoan?.id || initialPortalData?.loan_id;
  const borrowerName = initialPortalData?.borrower_name;

  // Determine which mode to show based on lifecycle stage or portal mode
  const isMumStage = initialPortalData?.lifecycle?.stage === 'MUM' ||
                     initialPortalData?.lifecycle?.stage === 'ANNUAL_REFRESH' ||
                     portalMode === 'servicing';

  // Get stage info
  const stage = initialPortalData?.lifecycle?.stage || 'ACTIVE';

  // Load additional data
  useEffect(() => {
    const loadAdditionalData = async () => {
      if (!activeLoanId) return;

      try {
        // Load close on time data for timeline stages
        if (!isMumStage) {
          const cotData = await closeOnTimeApi.getCloseCountdown(activeLoanId).catch(() => null);
          setCloseOnTimeData(cotData);
        }

        // Load milestones
        const milestoneData = await lifecycleApi.getMilestones(activeLoanId).catch(() => ({ milestones: [] }));
        setMilestones(milestoneData.milestones || []);

        // Load recent activity
        const activityData = await borrowerPortalApi.getActivities(activeLoanId, 10).catch(() => []);
        setActivities(activityData || []);
      } catch (err) {
        console.error('Error loading additional portal data:', err);
      }
    };

    loadAdditionalData();
  }, [activeLoanId, isMumStage]);

  // Get tabs for current mode
  const tabs = getPortalTabs(isMumStage);

  // Prepare loan info
  const loanInfo = {
    loan_number: initialPortalData?.loan_number,
    property_address: initialPortalData?.property_address,
    loan_amount: initialPortalData?.loan_amount,
    loan_type: initialPortalData?.loan_type,
    loan_purpose: initialPortalData?.loan_purpose || 'Purchase',
    loan_term: initialPortalData?.loan_term || 30,
    interest_rate: initialPortalData?.interest_rate,
    rate_lock_date: initialPortalData?.rate_lock_date,
    target_close_date: closeOnTimeData?.target_close_date || initialPortalData?.target_close_date,
    closing_date: initialPortalData?.closing_date,
  };

  // Show loading overlay when switching loans
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

  return (
    <div className="purl-portal">
      {/* Header Section */}
      <header className="portal-header">
        <div className="header-content">
          {/* Info Bar with LO Info (left) and Loan Details (right) */}
          <PortalInfoBar
            loan={loanInfo}
            loanOfficer={initialPortalData?.loan_officer}
            propertyAddress={initialPortalData?.property_address}
          />

          {/* Milestone Progress Indicator */}
          <HeaderMilestoneProgress
            stage={stage}
            leadStage={initialPortalData?.lead_stage}
          />
        </div>
      </header>

      {/* Navigation Tabs - Chevron style */}
      <nav className="portal-nav chevron-tabs">
        {tabs.map((tab, index) => (
          <TabButton
            key={tab.id}
            label={tab.label}
            isActive={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            badgeCount={
              tab.id === 'documents' ? (initialPortalData?.documentSummary?.pending_review || 0) :
              tab.id === 'activity' ? activities.filter(a => {
                const date = new Date(a.created_at);
                const now = new Date();
                return (now - date) < 86400000;
              }).length : 0
            }
            isFirst={index === 0}
            isLast={index === tabs.length - 1}
          />
        ))}
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {/* Overview Tab with Two-Column Layout */}
        {activeTab === 'overview' && (
          <div className="tab-content overview-tab">
            <div className="portal-dashboard-layout">
              {/* Main Content Area */}
              <div className="portal-main-content">
                {/* Contact Your Loan Officer Card */}
                <ContactLOCard onSchedule={() => {
                  // TODO: Open schedule modal
                  console.log('Schedule call clicked');
                }} />

                {/* Dashboard Content */}
                {isMumStage ? (
                  <MumPortalDashboard
                    loanId={activeLoanId}
                    borrowerName={borrowerName}
                  />
                ) : (
                  <BorrowerPortalDashboard
                    loanId={activeLoanId}
                    borrowerName={borrowerName}
                  />
                )}
              </div>

              {/* Sidebar */}
              <div className="portal-sidebar">
                {/* Days Until Closing Counter */}
                {!isMumStage && (
                  <DaysCounterCard
                    closeDate={loanInfo.closing_date}
                    estimatedCloseDate={loanInfo.target_close_date}
                  />
                )}

                {/* Recent Activity */}
                <RecentActivitySidebar
                  activities={activities}
                  onViewAll={() => setActiveTab('activity')}
                />
              </div>
            </div>
          </div>
        )}

        {/* Timeline Tab */}
        {activeTab === 'timeline' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Your Loan Journey</h2>
                <MilestoneTimeline loanId={activeLoanId} borrowerView={true} />
              </div>
            </div>
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Document Checklist</h2>
                <DocumentsSection loanId={activeLoanId} documentSummary={initialPortalData?.documentSummary} />
              </div>
            </div>
          </div>
        )}

        {/* Activity Tab */}
        {activeTab === 'activity' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Activity Feed</h2>
                <ActivitySection loanId={activeLoanId} />
              </div>
            </div>
          </div>
        )}

        {/* Home Value Tab (MUM) */}
        {activeTab === 'home-value' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <HomeValueIntelligence loanId={activeLoanId} />
              </div>
            </div>
          </div>
        )}

        {/* Equity Tab (MUM) */}
        {activeTab === 'equity' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Equity Tracker</h2>
                <EquitySection loanId={activeLoanId} />
              </div>
            </div>
          </div>
        )}

        {/* Refinance Tab (MUM) */}
        {activeTab === 'refinance' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Refinance Opportunities</h2>
                <RefinanceSection loanId={activeLoanId} />
              </div>
            </div>
          </div>
        )}

        {/* Contacts Tab */}
        {activeTab === 'contacts' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Your Team</h2>
                <TeamContactsSection loanOfficer={initialPortalData?.loan_officer} />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/**
 * Documents Section Component
 */
function DocumentsSection({ loanId, documentSummary }) {
  return (
    <div className="documents-section">
      <div className="doc-progress-large">
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${documentSummary?.completion_rate || 0}%` }}
          />
        </div>
        <span className="progress-text">{documentSummary?.completion_rate || 0}% Complete</span>
      </div>

      <div className="doc-stats-grid">
        <div className="doc-stat-card approved">
          <span className="stat-icon">✅</span>
          <span className="stat-value">{documentSummary?.by_status?.approved || 0}</span>
          <span className="stat-label">Approved</span>
        </div>
        <div className="doc-stat-card pending">
          <span className="stat-icon">⏳</span>
          <span className="stat-value">{documentSummary?.pending_review || 0}</span>
          <span className="stat-label">Pending Review</span>
        </div>
        <div className="doc-stat-card action">
          <span className="stat-icon">⚠️</span>
          <span className="stat-value">{documentSummary?.needs_reupload || 0}</span>
          <span className="stat-label">Needs Action</span>
        </div>
      </div>

      <div className="doc-actions">
        <button className="upload-btn">
          <span>📤</span> Upload Document
        </button>
      </div>
    </div>
  );
}

/**
 * Activity Section Component
 */
function ActivitySection({ loanId }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadActivities = async () => {
      try {
        const data = await borrowerPortalApi.getActivities(loanId, 20);
        setActivities(data || []);
      } catch (err) {
        console.error('Error loading activities:', err);
      } finally {
        setLoading(false);
      }
    };

    if (loanId) {
      loadActivities();
    }
  }, [loanId]);

  if (loading) {
    return <div className="loading-placeholder">Loading activities...</div>;
  }

  if (!activities.length) {
    return (
      <div className="empty-state">
        <span className="empty-icon">📋</span>
        <p>No activity yet</p>
      </div>
    );
  }

  return (
    <ul className="activity-feed">
      {activities.map((activity, idx) => (
        <li key={activity.id || idx} className="activity-item">
          <span className="activity-icon">{getActivityIcon(activity.activity_type)}</span>
          <div className="activity-content">
            <p className="activity-description">{activity.description}</p>
            <span className="activity-time">{formatTimeAgo(activity.created_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * Equity Section Component (MUM)
 */
function EquitySection({ loanId }) {
  return (
    <div className="equity-section">
      <div className="coming-soon">
        <span className="icon">💰</span>
        <h3>Equity Tracker Coming Soon</h3>
        <p>Track your home equity growth over time</p>
      </div>
    </div>
  );
}

/**
 * Refinance Section Component (MUM)
 */
function RefinanceSection({ loanId }) {
  return (
    <div className="refinance-section">
      <div className="coming-soon">
        <span className="icon">✨</span>
        <h3>Refinance Opportunities Coming Soon</h3>
        <p>We'll notify you when refinancing could save you money</p>
      </div>
    </div>
  );
}

/**
 * Team Contacts Section Component
 */
function TeamContactsSection({ loanOfficer }) {
  if (!loanOfficer) {
    return (
      <div className="empty-state">
        <span className="empty-icon">👥</span>
        <p>No team contacts available</p>
      </div>
    );
  }

  return (
    <div className="team-contacts">
      <div className="contact-card primary">
        <div className="contact-photo">
          {loanOfficer.photo_url ? (
            <img src={loanOfficer.photo_url} alt={loanOfficer.name} />
          ) : (
            <div className="contact-initials">
              {loanOfficer.name?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
            </div>
          )}
        </div>
        <div className="contact-info">
          <h4 className="contact-name">{loanOfficer.name}</h4>
          <p className="contact-title">{loanOfficer.title || 'Loan Officer'}</p>
          {loanOfficer.nmls && <p className="contact-nmls">NMLS# {loanOfficer.nmls}</p>}
        </div>
        <div className="contact-actions">
          {loanOfficer.phone && (
            <a href={`tel:${loanOfficer.phone}`} className="action-btn call">
              <span>📞</span> Call
            </a>
          )}
          {loanOfficer.email && (
            <a href={`mailto:${loanOfficer.email}`} className="action-btn email">
              <span>✉️</span> Email
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Helper: Get activity icon
 */
function getActivityIcon(type) {
  const icons = {
    stage_transition: '🔄',
    milestone_update: '✅',
    milestone_completed: '🎉',
    document_uploaded: '📄',
    document_status_changed: '📋',
    task_completed: '✓',
    message_sent: '💬',
    application_submitted: '📝',
    reminder: '🔔',
  };
  return icons[type] || '📌';
}

/**
 * Helper: Format time ago
 */
function formatTimeAgo(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;

  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Legacy Portal Header with Multi-Loan Support (kept for backward compatibility)
 */
function LegacyPortalHeader({ borrowerName }) {
  const { hasMultipleLoans, currentLoan } = usePortal();

  return (
    <div className="portal-top-header legacy">
      <div className="portal-branding">
        <h2 className="portal-title">Borrower Portal</h2>
        {borrowerName && <span className="portal-user">Welcome, {borrowerName}</span>}
      </div>

      <div className="portal-header-controls">
        {hasMultipleLoans && (
          <LoanSelector className="portal-loan-selector" showModeIndicator={false} />
        )}
        {currentLoan && (
          <PortalModeIndicator size="small" showCounts={false} />
        )}
      </div>
    </div>
  );
}

/**
 * Portal wrapper without multi-loan context (fallback for single loan access)
 * Uses same two-column layout as EnhancedPortalContent
 */
function SingleLoanPortal({ portalData }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [activities, setActivities] = useState([]);

  // Determine which mode to show based on lifecycle stage
  const isMumStage = portalData?.lifecycle?.stage === 'MUM' ||
                     portalData?.lifecycle?.stage === 'ANNUAL_REFRESH';

  const tabs = getPortalTabs(isMumStage);
  const stage = portalData?.lifecycle?.stage || 'ACTIVE';

  // Load activities
  useEffect(() => {
    const loadActivities = async () => {
      if (!portalData?.loan_id) return;
      try {
        const data = await borrowerPortalApi.getActivities(portalData.loan_id, 10).catch(() => []);
        setActivities(data || []);
      } catch (err) {
        console.error('Error loading activities:', err);
      }
    };
    loadActivities();
  }, [portalData?.loan_id]);

  // Prepare loan info
  const loanInfo = {
    loan_number: portalData?.loan_number,
    property_address: portalData?.property_address,
    loan_amount: portalData?.loan_amount,
    loan_type: portalData?.loan_type,
    loan_purpose: portalData?.loan_purpose || 'Purchase',
    loan_term: portalData?.loan_term || 30,
    interest_rate: portalData?.interest_rate,
    rate_lock_date: portalData?.rate_lock_date,
    target_close_date: portalData?.target_close_date,
    closing_date: portalData?.closing_date,
  };

  return (
    <div className="purl-portal">
      {/* Header Section */}
      <header className="portal-header">
        <div className="header-content">
          {/* Info Bar with LO Info (left) and Loan Details (right) */}
          <PortalInfoBar
            loan={loanInfo}
            loanOfficer={portalData?.loan_officer}
            propertyAddress={portalData?.property_address}
          />

          {/* Milestone Progress Indicator */}
          <HeaderMilestoneProgress
            stage={stage}
            leadStage={portalData?.lead_stage}
          />
        </div>
      </header>

      {/* Navigation Tabs - Chevron style */}
      <nav className="portal-nav chevron-tabs">
        {tabs.map((tab, index) => (
          <TabButton
            key={tab.id}
            label={tab.label}
            isActive={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            badgeCount={
              tab.id === 'documents' ? (portalData?.documentSummary?.pending_review || 0) :
              tab.id === 'activity' ? activities.filter(a => {
                const date = new Date(a.created_at);
                const now = new Date();
                return (now - date) < 86400000;
              }).length : 0
            }
            isFirst={index === 0}
            isLast={index === tabs.length - 1}
          />
        ))}
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {/* Overview Tab with Two-Column Layout */}
        {activeTab === 'overview' && (
          <div className="tab-content overview-tab">
            <div className="portal-dashboard-layout">
              {/* Main Content Area */}
              <div className="portal-main-content">
                {/* Contact Your Loan Officer Card */}
                <ContactLOCard onSchedule={() => console.log('Schedule call clicked')} />

                {/* Dashboard Content */}
                {isMumStage ? (
                  <MumPortalDashboard
                    loanId={portalData.loan_id}
                    borrowerName={portalData.borrower_name}
                  />
                ) : (
                  <BorrowerPortalDashboard
                    loanId={portalData.loan_id}
                    borrowerName={portalData.borrower_name}
                  />
                )}
              </div>

              {/* Sidebar */}
              <div className="portal-sidebar">
                {/* Days Until Closing Counter */}
                {!isMumStage && (
                  <DaysCounterCard
                    closeDate={loanInfo.closing_date}
                    estimatedCloseDate={loanInfo.target_close_date}
                  />
                )}

                {/* Recent Activity */}
                <RecentActivitySidebar
                  activities={activities}
                  onViewAll={() => setActiveTab('activity')}
                />
              </div>
            </div>
          </div>
        )}

        {/* Timeline Tab */}
        {activeTab === 'timeline' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Your Loan Journey</h2>
                <MilestoneTimeline loanId={portalData.loan_id} borrowerView={true} />
              </div>
            </div>
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Document Checklist</h2>
                <DocumentsSection loanId={portalData.loan_id} documentSummary={portalData?.documentSummary} />
              </div>
            </div>
          </div>
        )}

        {/* Activity Tab */}
        {activeTab === 'activity' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Activity Feed</h2>
                <ActivitySection loanId={portalData.loan_id} />
              </div>
            </div>
          </div>
        )}

        {/* Contacts Tab */}
        {activeTab === 'contacts' && (
          <div className="tab-content">
            <div className="portal-container">
              <div className="portal-section">
                <h2>Your Team</h2>
                <TeamContactsSection loanOfficer={portalData?.loan_officer} />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

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

        // Try token-based access first (magic link)
        if (token) {
          const data = await borrowerPortalApi.getPortalByToken(token);
          setPortalData(data);
        } else {
          // Fall back to loan_id from query params (authenticated access)
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
          <p className="help-text">
            If you received a link to access your portal, please make sure you're using the complete link.
            Contact your loan officer if you need assistance.
          </p>
        </div>
      </div>
    );
  }

  // Get PURL token for multi-loan context authentication
  // The token can come from URL params (magic link) or portal data
  const purlToken = portalData?.purl_token || token;

  // Check if we have multi-loan context (need a PURL token for authenticated API calls)
  const hasMultiLoanContext = !!purlToken;

  return (
    <div className="portal-page">
      {hasMultiLoanContext ? (
        <PortalProvider token={purlToken}>
          <EnhancedPortalContent initialPortalData={portalData} />
        </PortalProvider>
      ) : (
        <SingleLoanPortal portalData={portalData} />
      )}

      {/* Portal Footer */}
      <footer className="portal-footer">
        <p>Powered by Perennia AI</p>
        <p className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <span className="divider">|</span>
          <a href="/terms">Terms of Service</a>
        </p>
      </footer>
    </div>
  );
}
