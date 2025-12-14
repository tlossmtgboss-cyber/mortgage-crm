/**
 * PartnerPortalView Component
 *
 * Partner/Realtor portal with magic link access (no login required).
 * Features:
 * - Filtered timeline (hides sensitive milestones)
 * - Critical dates display
 * - Risk flags visibility
 * - Loan officer contact info
 * - Read-only access badge
 * - Real-time updates via WebSocket
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import CloseOnTimeArrowTimeline from './CloseOnTimeArrowTimeline';
import MilestoneTimeline from './MilestoneTimeline';
import { partnerPortalApi } from '../../services/portalApi';
import './PartnerPortalView.css';

// Stages that show Close On Time arrow timeline (S3-S5)
const CLOSE_ON_TIME_STAGES = ['UNDER_CONTRACT', 'PROCESSING', 'CLEAR_TO_CLOSE'];

// WebSocket status
const WS_STATUS = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
};

export default function PartnerPortalView() {
  const { token } = useParams();
  const [portalData, setPortalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wsStatus, setWsStatus] = useState(WS_STATUS.DISCONNECTED);
  const [lastUpdate, setLastUpdate] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Fetch portal data
  const fetchPortalData = useCallback(async () => {
    try {
      const data = await partnerPortalApi.getPortalByToken(token);
      setPortalData(data);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      console.error('Failed to load partner portal:', err);
      setError(err.message || 'Failed to load portal. Please check your access link.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  // WebSocket connection for real-time updates
  const connectWebSocket = useCallback(() => {
    if (!portalData?.loan_id) return;

    const wsUrl = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';
    const enableWs = process.env.REACT_APP_ENABLE_WEBSOCKET !== 'false';

    if (!enableWs) return;

    try {
      setWsStatus(WS_STATUS.CONNECTING);
      wsRef.current = new WebSocket(`${wsUrl}/ws/loan/${portalData.loan_id}`);

      wsRef.current.onopen = () => {
        console.log('Partner portal WebSocket connected');
        setWsStatus(WS_STATUS.CONNECTED);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (['MILESTONE_UPDATE', 'LIFECYCLE_CHANGE'].includes(message.type)) {
            fetchPortalData();
          }
        } catch (err) {
          console.error('WebSocket message error:', err);
        }
      };

      wsRef.current.onclose = () => {
        setWsStatus(WS_STATUS.DISCONNECTED);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
      };

      wsRef.current.onerror = () => {
        setWsStatus(WS_STATUS.DISCONNECTED);
      };
    } catch (err) {
      console.error('WebSocket connection failed:', err);
    }
  }, [portalData?.loan_id, fetchPortalData]);

  // Initial load
  useEffect(() => {
    fetchPortalData();
  }, [fetchPortalData]);

  // Connect WebSocket after data loads
  useEffect(() => {
    if (portalData?.loan_id) {
      connectWebSocket();
    }

    // Polling fallback
    const pollInterval = setInterval(() => {
      if (wsStatus !== WS_STATUS.CONNECTED) {
        fetchPortalData();
      }
    }, 60000); // Poll every minute for partners

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      clearInterval(pollInterval);
    };
  }, [portalData?.loan_id, connectWebSocket, wsStatus, fetchPortalData]);

  if (loading) {
    return <PartnerPortalSkeleton />;
  }

  if (error) {
    return (
      <div className="partner-portal-error">
        <div className="error-card">
          <span className="error-icon">🔒</span>
          <h1>Access Error</h1>
          <p>{error}</p>
          <p className="help-text">
            If you received this link from your loan officer, please contact them to verify your access.
          </p>
        </div>
      </div>
    );
  }

  const stage = portalData?.lifecycle?.stage;
  const showCloseOnTime = CLOSE_ON_TIME_STAGES.includes(stage);

  return (
    <div className="partner-portal">
      {/* Header */}
      <header className="partner-header">
        <div className="header-content">
          <div className="header-top">
            <div className="partner-badge">
              <span className="badge-icon">👁️</span>
              <span>Partner View</span>
              <span className="read-only">Read Only</span>
            </div>
            {wsStatus === WS_STATUS.CONNECTED && (
              <div className="live-badge">
                <span className="live-dot" />
                Live
              </div>
            )}
          </div>

          <h1>Loan Status</h1>

          <div className="loan-summary">
            <div className="summary-item">
              <span className="label">Borrower</span>
              <span className="value">{portalData.borrower_name || 'N/A'}</span>
            </div>
            <div className="summary-item">
              <span className="label">Property</span>
              <span className="value">{portalData.property_address || 'TBD'}</span>
            </div>
            <div className="summary-item">
              <span className="label">Status</span>
              <span className={`stage-badge ${stage?.toLowerCase()}`}>
                {formatStageName(stage)}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="partner-content">
        {/* Close On Time Timeline (Partner View) */}
        {showCloseOnTime && portalData.closeOnTime?.has_schedule && (
          <section className="partner-section">
            <CloseOnTimeArrowTimeline
              loanId={portalData.loan_id}
              milestones={portalData.closeOnTime?.milestones || []}
              targetCloseDate={portalData.closeOnTime?.target_close_date}
              businessDaysRemaining={portalData.closeOnTime?.business_days_remaining}
              isPartnerView={true}
            />
          </section>
        )}

        {/* Critical Dates */}
        <section className="partner-section">
          <h2>Critical Dates</h2>
          <CriticalDatesCard dates={portalData.criticalDates} />
        </section>

        {/* Risk Flags (if any) */}
        {portalData.riskFlags?.length > 0 && (
          <section className="partner-section risk-section">
            <h2>
              <span className="warning-icon">⚠️</span>
              Items Needing Attention
            </h2>
            <RiskFlagsList flags={portalData.riskFlags} />
          </section>
        )}

        {/* Milestone Progress (for non-close-on-time stages) */}
        {!showCloseOnTime && (
          <section className="partner-section">
            <h2>Loan Progress</h2>
            <MilestoneTimeline
              loanId={portalData.loan_id}
              borrowerView={true}
              partnerView={true}
            />
          </section>
        )}

        {/* Loan Officer Contact */}
        <section className="partner-section contact-section">
          <h2>Your Loan Officer</h2>
          <LoanOfficerCard loanOfficer={portalData.loanOfficer} />
        </section>
      </main>

      {/* Footer */}
      <footer className="partner-footer">
        <p>
          Last updated: {lastUpdate ? formatDateTime(lastUpdate) : 'Just now'}
        </p>
        <p className="powered-by">Powered by Perennia AI</p>
      </footer>
    </div>
  );
}

/**
 * Critical Dates Card
 */
function CriticalDatesCard({ dates }) {
  const criticalDates = [
    { key: 'target_close', label: 'Target Close Date', icon: '🎯' },
    { key: 'appraisal_due', label: 'Appraisal Due', icon: '🏠' },
    { key: 'inspection_deadline', label: 'Inspection Deadline', icon: '🔍' },
    { key: 'financing_contingency', label: 'Financing Contingency', icon: '💰' },
    { key: 'earnest_money_due', label: 'Earnest Money Due', icon: '💵' },
  ];

  const hasAnyDate = dates && Object.values(dates).some(d => d);

  if (!hasAnyDate) {
    return (
      <div className="empty-dates">
        <p>No critical dates set yet</p>
      </div>
    );
  }

  return (
    <div className="critical-dates-grid">
      {criticalDates.map(({ key, label, icon }) => {
        const dateValue = dates?.[key];
        if (!dateValue) return null;

        const date = new Date(dateValue);
        const isPast = date < new Date();
        const isNear = !isPast && (date - new Date()) < 7 * 24 * 60 * 60 * 1000; // Within 7 days

        return (
          <div
            key={key}
            className={`date-card ${isPast ? 'past' : ''} ${isNear ? 'near' : ''}`}
          >
            <span className="date-icon">{icon}</span>
            <span className="date-label">{label}</span>
            <span className="date-value">
              {date.toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
              })}
            </span>
            {isNear && <span className="near-badge">Soon</span>}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Risk Flags List
 */
function RiskFlagsList({ flags }) {
  return (
    <ul className="risk-flags-list">
      {flags.map((flag, idx) => (
        <li key={idx} className={`risk-flag ${flag.severity}`}>
          <div className="flag-content">
            <span className="flag-title">{flag.title}</span>
            {flag.description && (
              <span className="flag-description">{flag.description}</span>
            )}
          </div>
          <span className={`severity-badge ${flag.severity}`}>
            {flag.severity}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Loan Officer Contact Card
 */
function LoanOfficerCard({ loanOfficer }) {
  if (!loanOfficer) {
    return (
      <div className="lo-card empty">
        <p>Loan officer information not available</p>
      </div>
    );
  }

  return (
    <div className="lo-card">
      <div className="lo-avatar">
        {loanOfficer.avatar_url ? (
          <img src={loanOfficer.avatar_url} alt={loanOfficer.name} />
        ) : (
          <span className="avatar-initials">
            {getInitials(loanOfficer.name)}
          </span>
        )}
      </div>
      <div className="lo-info">
        <h3>{loanOfficer.name}</h3>
        <p className="lo-title">{loanOfficer.title || 'Loan Officer'}</p>
        <p className="lo-nmls">NMLS# {loanOfficer.nmls_id || 'N/A'}</p>
      </div>
      <div className="lo-contact">
        {loanOfficer.phone && (
          <a href={`tel:${loanOfficer.phone}`} className="contact-btn phone">
            <span className="icon">📞</span>
            <span>{formatPhoneNumber(loanOfficer.phone)}</span>
          </a>
        )}
        {loanOfficer.email && (
          <a href={`mailto:${loanOfficer.email}`} className="contact-btn email">
            <span className="icon">📧</span>
            <span>Email</span>
          </a>
        )}
      </div>
    </div>
  );
}

/**
 * Skeleton Loader
 */
function PartnerPortalSkeleton() {
  return (
    <div className="partner-portal skeleton">
      <header className="partner-header">
        <div className="header-content">
          <div className="skeleton-badge" />
          <div className="skeleton-title" />
          <div className="skeleton-summary" />
        </div>
      </header>
      <main className="partner-content">
        {[1, 2, 3].map(i => (
          <div key={i} className="partner-section skeleton-section">
            <div className="skeleton-section-title" />
            <div className="skeleton-section-content" />
          </div>
        ))}
      </main>
    </div>
  );
}

/**
 * Helper: Format stage name
 */
function formatStageName(stage) {
  const names = {
    PROSPECT: 'Prospect',
    LEAD: 'Lead',
    PREAPPROVAL: 'Pre-Approval',
    UNDER_CONTRACT: 'Under Contract',
    PROCESSING: 'Processing',
    CLEAR_TO_CLOSE: 'Clear to Close',
    FUNDED: 'Funded',
    MUM: 'Servicing',
  };
  return names[stage] || stage || 'Unknown';
}

/**
 * Helper: Format date time
 */
function formatDateTime(date) {
  return new Date(date).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * Helper: Get initials from name
 */
function getInitials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Helper: Format phone number
 */
function formatPhoneNumber(phone) {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
}
