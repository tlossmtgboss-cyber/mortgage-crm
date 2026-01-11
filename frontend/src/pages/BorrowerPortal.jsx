/**
 * BorrowerPortal Page
 *
 * Public-facing borrower portal that displays loan progress,
 * milestones, documents, and timeline information.
 * Supports multi-loan switching for borrowers with multiple loans.
 *
 * Enhanced UI with:
 * - Tab navigation
 * - Enhanced header with loan info, milestone progress, days counter
 * - MUM features for closed loans
 */

import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import BorrowerPortalDashboard, { MumPortalDashboard } from '../components/Portal/BorrowerPortalDashboard';
import { borrowerPortalApi, closeOnTimeApi, lifecycleApi } from '../services/portalApi';
import { PortalProvider, usePortal } from '../contexts/PortalContext';
import {
  LoanSelector,
  PortalModeIndicator,
  EnhancedPortalHeader,
  PortalTabs,
  TabPanel,
  PORTAL_TABS,
  MilestoneTimeline,
} from '../components/Portal';
import HomeValueIntelligence from '../components/Portal/HomeValueIntelligence';
import './BorrowerPortal.css';

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
 * Enhanced Portal Content with Tabs
 */
function EnhancedPortalContent({ initialPortalData }) {
  const { currentLoan, portalMode, switching, hasMultipleLoans } = usePortal();
  const [activeTab, setActiveTab] = useState('overview');
  const [closeOnTimeData, setCloseOnTimeData] = useState(null);
  const [milestones, setMilestones] = useState([]);

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
      } catch (err) {
        console.error('Error loading additional portal data:', err);
      }
    };

    loadAdditionalData();
  }, [activeLoanId, isMumStage]);

  // Get tabs for current mode
  const tabs = getPortalTabs(isMumStage);

  // Prepare loan info for header
  const loanInfo = {
    loan_number: initialPortalData?.loan_number,
    property_address: initialPortalData?.property_address,
    loan_amount: initialPortalData?.loan_amount,
    loan_type: initialPortalData?.loan_type,
    target_close_date: closeOnTimeData?.target_close_date,
  };

  // Prepare milestone progress for header
  const milestoneProgress = {
    milestones: milestones,
    completed: initialPortalData?.progress?.completed_milestones || 0,
    total: initialPortalData?.progress?.total_milestones || 0,
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
    <>
      {/* Enhanced Header with loan info, progress bar, days counter */}
      <EnhancedPortalHeader
        borrowerName={borrowerName}
        loan={loanInfo}
        milestoneProgress={milestoneProgress}
        closeOnTimeData={closeOnTimeData}
        loanOfficer={initialPortalData?.loan_officer}
        stage={stage}
        showMultiLoanSelector={hasMultipleLoans}
      >
        {/* Multi-loan selector slot */}
        <LoanSelector className="portal-loan-selector" showModeIndicator={false} />
      </EnhancedPortalHeader>

      {/* Tab Navigation */}
      <PortalTabs
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        badges={{
          documents: initialPortalData?.documentSummary?.pending_review || 0,
          activity: initialPortalData?.recentActivity?.length || 0,
        }}
      />

      {/* Tab Content */}
      <div className="portal-container">
        <TabPanel id="overview" activeTab={activeTab}>
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
        </TabPanel>

        <TabPanel id="timeline" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Your Loan Journey</h2>
            <MilestoneTimeline loanId={activeLoanId} borrowerView={true} />
          </div>
        </TabPanel>

        <TabPanel id="documents" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Document Checklist</h2>
            <DocumentsSection loanId={activeLoanId} documentSummary={initialPortalData?.documentSummary} />
          </div>
        </TabPanel>

        <TabPanel id="activity" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Activity Feed</h2>
            <ActivitySection loanId={activeLoanId} />
          </div>
        </TabPanel>

        <TabPanel id="home-value" activeTab={activeTab}>
          <div className="portal-section">
            <HomeValueIntelligence loanId={activeLoanId} />
          </div>
        </TabPanel>

        <TabPanel id="equity" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Equity Tracker</h2>
            <EquitySection loanId={activeLoanId} />
          </div>
        </TabPanel>

        <TabPanel id="refinance" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Refinance Opportunities</h2>
            <RefinanceSection loanId={activeLoanId} />
          </div>
        </TabPanel>

        <TabPanel id="contacts" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Your Team</h2>
            <TeamContactsSection loanOfficer={initialPortalData?.loan_officer} />
          </div>
        </TabPanel>
      </div>
    </>
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
 */
function SingleLoanPortal({ portalData }) {
  const [activeTab, setActiveTab] = useState('overview');

  // Determine which mode to show based on lifecycle stage
  const isMumStage = portalData?.lifecycle?.stage === 'MUM' ||
                     portalData?.lifecycle?.stage === 'ANNUAL_REFRESH';

  const tabs = getPortalTabs(isMumStage);
  const stage = portalData?.lifecycle?.stage || 'ACTIVE';

  return (
    <>
      <EnhancedPortalHeader
        borrowerName={portalData?.borrower_name}
        loan={{
          loan_number: portalData?.loan_number,
          property_address: portalData?.property_address,
          loan_amount: portalData?.loan_amount,
          loan_type: portalData?.loan_type,
        }}
        milestoneProgress={{
          completed: portalData?.progress?.completed_milestones || 0,
          total: portalData?.progress?.total_milestones || 0,
        }}
        loanOfficer={portalData?.loan_officer}
        stage={stage}
        showMultiLoanSelector={false}
      />

      <PortalTabs
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      <div className="portal-container">
        <TabPanel id="overview" activeTab={activeTab}>
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
        </TabPanel>

        <TabPanel id="timeline" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Your Loan Journey</h2>
            <MilestoneTimeline loanId={portalData.loan_id} borrowerView={true} />
          </div>
        </TabPanel>

        <TabPanel id="documents" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Document Checklist</h2>
            <DocumentsSection loanId={portalData.loan_id} documentSummary={portalData?.documentSummary} />
          </div>
        </TabPanel>

        <TabPanel id="activity" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Activity Feed</h2>
            <ActivitySection loanId={portalData.loan_id} />
          </div>
        </TabPanel>

        <TabPanel id="contacts" activeTab={activeTab}>
          <div className="portal-section">
            <h2>Your Team</h2>
            <TeamContactsSection loanOfficer={portalData?.loan_officer} />
          </div>
        </TabPanel>
      </div>
    </>
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
