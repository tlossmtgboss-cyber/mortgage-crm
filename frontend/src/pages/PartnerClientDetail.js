/**
 * Partner Client Detail Page - Redesigned
 *
 * Clean, focused view for partners to track their referred clients.
 * Features:
 * - Document collection progress with percentage
 * - Activity/Notes timeline for client communications
 * - Clean milestone progress tracker
 * - Key loan details without redundancy
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import MilestoneProgressTracker from '../components/MilestoneProgressTracker';
import PreApprovalLetterModal from '../components/PreApprovalLetterModal';
import { activitiesAPI } from '../services/api';
import './PartnerClientDetail.css';

// API base URL
const API_BASE = process.env.REACT_APP_API_URL || '';

// Activity type configuration
const ACTIVITY_CONFIG = {
  note: { label: 'Note', icon: '📝', color: '#6366f1' },
  call: { label: 'Call', icon: '📞', color: '#10b981' },
  email: { label: 'Email', icon: '✉️', color: '#3b82f6' },
  sms: { label: 'SMS', icon: '💬', color: '#8b5cf6' },
  meeting: { label: 'Meeting', icon: '🤝', color: '#f59e0b' },
  task: { label: 'Task', icon: '✓', color: '#ef4444' },
  document: { label: 'Document', icon: '📄', color: '#06b6d4' },
  status_change: { label: 'Status Update', icon: '🔄', color: '#218D8D' },
  stage_change: { label: 'Stage Change', icon: '📊', color: '#218D8D' },
};

// Format relative time
const formatRelativeTime = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Format full property address
const formatAddress = (client) => {
  const parts = [];
  const address = client?.property_address || client?.property?.address || client?.address;
  const city = client?.property_city || client?.property?.city || client?.city;
  const state = client?.property_state || client?.property?.state || client?.state;
  const zip = client?.property_zip || client?.property?.zip || client?.zip_code;

  if (address) parts.push(address);
  if (city) parts.push(city);
  if (state && zip) {
    parts.push(`${state} ${zip}`);
  } else if (state) {
    parts.push(state);
  } else if (zip) {
    parts.push(zip);
  }

  return parts.join(', ') || 'Property Address TBD';
};

// Document Progress Component
const DocumentProgress = ({ documents, loanId }) => {
  const navigate = useNavigate();
  const total = documents?.total || documents?.requested_count || 0;
  const received = documents?.received_count || 0;
  const outstanding = documents?.outstanding_count || 0;
  const percentage = total > 0 ? Math.round((received / total) * 100) : 0;

  // Get color based on percentage
  const getProgressColor = () => {
    if (percentage >= 80) return '#10b981'; // Green
    if (percentage >= 50) return '#f59e0b'; // Amber
    return '#ef4444'; // Red
  };

  return (
    <div className="document-progress-card">
      <div className="progress-header">
        <h3>Document Collection</h3>
        <span className="progress-percentage" style={{ color: getProgressColor() }}>
          {percentage}%
        </span>
      </div>

      <div className="progress-bar-container">
        <div
          className="progress-bar-fill"
          style={{
            width: `${percentage}%`,
            background: `linear-gradient(90deg, ${getProgressColor()} 0%, ${getProgressColor()}dd 100%)`
          }}
        />
      </div>

      <div className="progress-stats">
        <div className="progress-stat">
          <span className="stat-number received">{received}</span>
          <span className="stat-label">Received</span>
        </div>
        <div className="progress-divider">/</div>
        <div className="progress-stat">
          <span className="stat-number total">{outstanding}</span>
          <span className="stat-label">Requested</span>
        </div>
      </div>

      {documents?.outstanding?.length > 0 && (
        <div className="outstanding-docs">
          <h4>Still Needed:</h4>
          <ul>
            {documents.outstanding.slice(0, 4).map((doc, idx) => (
              <li key={doc.id || idx}>
                <span className="doc-bullet">•</span>
                {doc.title || doc.type || doc.name}
              </li>
            ))}
            {documents.outstanding.length > 4 && (
              <li className="more-docs">+{documents.outstanding.length - 4} more</li>
            )}
          </ul>
        </div>
      )}

      {loanId && (
        <button
          className="btn-view-docs"
          onClick={() => navigate(`/smart-docs/client/${loanId}`)}
        >
          View Documents →
        </button>
      )}
    </div>
  );
};

// Notes & Activity Timeline Component
const ActivityTimeline = ({ activities, stageHistory, conversationLog }) => {
  // Combine all activities into unified timeline
  const getTimeline = () => {
    const timeline = [];

    // Add activities
    (activities || []).forEach(activity => {
      timeline.push({
        id: `activity-${activity.id}`,
        type: activity.type?.toLowerCase() || 'note',
        content: activity.content || activity.notes || activity.description,
        created_at: activity.created_at,
        user: activity.user_name || activity.created_by,
      });
    });

    // Add stage changes
    (stageHistory || []).forEach(history => {
      timeline.push({
        id: `stage-${history.id}`,
        type: 'stage_change',
        content: `Status changed from "${history.from_stage || 'New'}" to "${history.to_stage}"`,
        created_at: history.changed_at,
      });
    });

    // Add conversation log
    (conversationLog || []).forEach((log, idx) => {
      timeline.push({
        id: `conv-${idx}`,
        type: log.type || 'note',
        content: log.content || log.message || log.description,
        created_at: log.timestamp || log.created_at,
        user: log.user,
      });
    });

    // Sort by date (newest first)
    timeline.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    return timeline;
  };

  const timeline = getTimeline();

  return (
    <div className="activity-timeline-card">
      <div className="timeline-header">
        <h3>Notes & Activity</h3>
        <span className="timeline-count">{timeline.length} updates</span>
      </div>

      {timeline.length === 0 ? (
        <div className="empty-timeline">
          <span className="empty-icon">📋</span>
          <p>No activity recorded yet</p>
        </div>
      ) : (
        <div className="timeline-list">
          {timeline.slice(0, 10).map((item) => {
            const config = ACTIVITY_CONFIG[item.type] || { label: 'Update', icon: '📌', color: '#6b7280' };

            return (
              <div key={item.id} className="timeline-item">
                <div className="timeline-icon" style={{ background: `${config.color}15`, color: config.color }}>
                  {config.icon}
                </div>
                <div className="timeline-content">
                  <div className="timeline-meta">
                    <span className="timeline-type">{config.label}</span>
                    <span className="timeline-time">{formatRelativeTime(item.created_at)}</span>
                  </div>
                  <p className="timeline-text">{item.content}</p>
                  {item.user && <span className="timeline-user">by {item.user}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default function PartnerClientDetail() {
  const { partnerId, clientId } = useParams();
  const navigate = useNavigate();
  const [clientData, setClientData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showPreApprovalModal, setShowPreApprovalModal] = useState(false);
  const [activities, setActivities] = useState([]);
  const [stageHistory, setStageHistory] = useState([]);
  const [smartDocsData, setSmartDocsData] = useState(null);

  useEffect(() => {
    loadClientData();
  }, [clientId]);

  useEffect(() => {
    if (clientData?.client?.id) {
      loadActivities();
      loadStageHistory();
      loadSmartDocsData();
    }
  }, [clientData?.client?.id]);

  const loadActivities = async () => {
    try {
      const jwtToken = localStorage.getItem('token');
      if (!jwtToken) return;
      const data = await activitiesAPI.getAll({ lead_id: clientId });
      setActivities(data || []);
    } catch (err) {
      console.error('Error loading activities:', err);
    }
  };

  const loadStageHistory = async () => {
    try {
      const jwtToken = localStorage.getItem('token');
      if (!jwtToken) return;

      const response = await fetch(
        `${API_BASE}/api/v1/leads/${clientId}/stage-history`,
        {
          headers: {
            'Authorization': `Bearer ${jwtToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setStageHistory(data.stage_history || []);
      }
    } catch (err) {
      console.error('Error loading stage history:', err);
    }
  };

  // Load Smart Docs data for document progress
  const loadSmartDocsData = async () => {
    try {
      const jwtToken = localStorage.getItem('token');
      if (!jwtToken) return;

      // First, try to find a linked loan for this lead
      // Try by lead's loan_id if available, or search by email
      const leadEmail = clientData?.client?.email;
      const leadId = clientData?.client?.id;

      // Try to get Smart Docs queue data which includes all loans
      const queueResponse = await fetch(
        `${API_BASE}/api/v1/smart-docs/queue`,
        {
          headers: {
            'Authorization': `Bearer ${jwtToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (queueResponse.ok) {
        const queueData = await queueResponse.json();
        // Find matching loan by borrower name or email
        const borrowerName = clientData?.client?.borrower_name || clientData?.client?.name;
        const matchingLoan = queueData.find(loan =>
          (leadEmail && loan.borrower_email?.toLowerCase() === leadEmail.toLowerCase()) ||
          (borrowerName && loan.borrower_name?.toLowerCase().includes(borrowerName.toLowerCase()))
        );

        if (matchingLoan) {
          // Fetch detailed needs list for this loan
          const needsListResponse = await fetch(
            `${API_BASE}/api/v1/smart-docs/needs-list/${matchingLoan.loan_id}`,
            {
              headers: {
                'Authorization': `Bearer ${jwtToken}`,
                'Content-Type': 'application/json'
              }
            }
          );

          if (needsListResponse.ok) {
            const needsListData = await needsListResponse.json();
            const requests = needsListData.all_requests || [];

            // Count by status
            const outstanding = requests.filter(r => r.status === 'REQUESTED' || r.status === 'PENDING');
            const received = requests.filter(r => r.status === 'PENDING_REVIEW' || r.status === 'UPLOADED');
            const completed = requests.filter(r => r.status === 'ACCEPTED' || r.status === 'WAIVED');

            setSmartDocsData({
              loanId: matchingLoan.loan_id,
              outstanding: outstanding,
              received: received,
              completed: completed,
              outstanding_count: outstanding.length,
              received_count: received.length + completed.length,
              requested_count: requests.length,
              total: requests.length
            });
            return;
          }
        }
      }

      // Fallback: try to fetch by lead's conditions endpoint
      const conditionsResponse = await fetch(
        `${API_BASE}/api/v1/leads/${leadId}/conditions`,
        {
          headers: {
            'Authorization': `Bearer ${jwtToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (conditionsResponse.ok) {
        const conditionsData = await conditionsResponse.json();
        const docConditions = (conditionsData.conditions || []).filter(c => c.source === 'smart_docs');

        if (docConditions.length > 0) {
          const outstanding = docConditions.filter(c => c.status === 'pending');
          const received = docConditions.filter(c => c.status === 'received' || c.status === 'approved');

          setSmartDocsData({
            loanId: docConditions[0]?.loan_id,
            outstanding: outstanding,
            received: received,
            completed: [],
            outstanding_count: outstanding.length,
            received_count: received.length,
            requested_count: docConditions.length,
            total: docConditions.length
          });
        }
      }
    } catch (err) {
      console.error('Error loading Smart Docs data:', err);
    }
  };

  const loadClientData = async () => {
    try {
      setLoading(true);
      setError(null);

      const jwtToken = localStorage.getItem('token');
      const partnerToken = localStorage.getItem('partnerToken') || new URLSearchParams(window.location.search).get('token');

      let response;

      // Try CRM authentication first
      if (jwtToken) {
        try {
          response = await fetch(
            `${API_BASE}/api/v1/leads/${clientId}`,
            {
              headers: {
                'Authorization': `Bearer ${jwtToken}`,
                'Content-Type': 'application/json'
              }
            }
          );

          if (response.ok) {
            const leadData = await response.json();
            setClientData({
              success: true,
              client: {
                id: leadData.id,
                name: leadData.name,
                borrower_name: leadData.name,
                first_name: leadData.first_name,
                last_name: leadData.last_name,
                email: leadData.email,
                phone: leadData.phone,
                status: leadData.stage,
                stage: leadData.stage,
                loan_amount: leadData.loan_amount,
                loan_number: leadData.loan_number || leadData.id,
                property_address: leadData.address,
                property_city: leadData.city,
                property_state: leadData.state,
                property_zip: leadData.zip_code,
                property_type: leadData.property_type,
                loan_type: leadData.loan_type,
                credit_score: leadData.credit_score,
                down_payment: leadData.down_payment,
                ltv_ratio: leadData.ltv,
                interest_rate: leadData.interest_rate,
                loan_term: leadData.loan_term,
                created_at: leadData.created_at,
                updated_at: leadData.updated_at,
                expected_close_date: leadData.expected_close_date,
                purchase_price: leadData.purchase_price || leadData.property_value,
                loan_officer: leadData.assigned_user ? {
                  name: leadData.assigned_user.name,
                  email: leadData.assigned_user.email,
                  phone: leadData.assigned_user.phone
                } : null
              },
              documents: {
                outstanding: [],
                received: [],
                outstanding_count: 0,
                received_count: 0,
                requested_count: 8
              },
              conversations: []
            });
            return;
          }
        } catch (jwtError) {
          console.error('JWT auth failed:', jwtError);
        }
      }

      // Fall back to partner portal token
      if (!partnerToken) {
        setError('Authentication required. Please log in.');
        return;
      }

      response = await fetch(
        `${API_BASE}/api/v1/realtor-portal/clients/${clientId}/full-details?token=${partnerToken}`
      );

      if (!response.ok) {
        if (response.status === 401) throw new Error('Session expired. Please log in again.');
        if (response.status === 403) throw new Error('You do not have access to this client.');
        throw new Error('Failed to load client details');
      }

      const data = await response.json();
      if (data.success) {
        setClientData(data);
      } else {
        throw new Error(data.error || 'Failed to load client details');
      }
    } catch (err) {
      console.error('Error loading client:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    if (!amount) return 'TBD';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const formatPhone = (phone) => {
    if (!phone) return null;
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
    }
    return phone;
  };

  if (loading) {
    return (
      <div className="partner-client-detail-v2 loading-state">
        <div className="loading-spinner" />
        <p>Loading client details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="partner-client-detail-v2 error-state">
        <div className="error-content">
          <span className="error-icon">⚠️</span>
          <h2>Unable to Load</h2>
          <p>{error}</p>
          <button className="btn-back" onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  if (!clientData) {
    return (
      <div className="partner-client-detail-v2 error-state">
        <h2>Client Not Found</h2>
        <button className="btn-back" onClick={() => navigate(-1)}>Go Back</button>
      </div>
    );
  }

  const { client, documents, conversation_log } = clientData;
  const currentStage = client?.status || client?.stage || 'new';

  return (
    <div className="partner-client-detail-v2">
      {/* Top Navigation */}
      <nav className="top-nav">
        <button className="back-btn" onClick={() => navigate(-1)}>
          ← Back to Dashboard
        </button>
      </nav>

      {/* Client Header */}
      <header className="client-header">
        <div className="header-left">
          <div className="client-avatar">
            {(client?.first_name || client?.borrower_name || 'C').charAt(0).toUpperCase()}
          </div>
          <div className="client-info">
            <h1>{client?.borrower_name || client?.name || 'Client'}</h1>
            <p className="property-address">
              📍 {formatAddress(client)}
            </p>
          </div>
        </div>
        <div className="header-actions">
          <button className="btn-primary" onClick={() => setShowPreApprovalModal(true)}>
            📄 Pre-Approval Letter
          </button>
        </div>
      </header>

      {/* Progress Tracker */}
      <section className="progress-section">
        <MilestoneProgressTracker currentStatus={currentStage} />
      </section>

      {/* Main Grid Layout */}
      <div className="content-grid">
        {/* Left Column - Key Info */}
        <div className="left-column">
          {/* Loan Summary Card */}
          <div className="info-card">
            <h3>Loan Summary</h3>
            <div className="summary-grid">
              <div className="summary-item highlight">
                <span className="label">Loan Amount</span>
                <span className="value large">{formatCurrency(client?.loan_amount)}</span>
              </div>
              <div className="summary-item">
                <span className="label">Loan Type</span>
                <span className="value">{client?.loan_type || 'Conventional'}</span>
              </div>
              <div className="summary-item">
                <span className="label">Purchase Price</span>
                <span className="value">{formatCurrency(client?.purchase_price)}</span>
              </div>
              <div className="summary-item">
                <span className="label">Down Payment</span>
                <span className="value">{formatCurrency(client?.down_payment)}</span>
              </div>
              <div className="summary-item">
                <span className="label">LTV</span>
                <span className="value">{client?.ltv_ratio ? `${client.ltv_ratio}%` : 'TBD'}</span>
              </div>
              <div className="summary-item">
                <span className="label">Interest Rate</span>
                <span className="value">{client?.interest_rate ? `${client.interest_rate}%` : 'TBD'}</span>
              </div>
            </div>
          </div>

          {/* Borrower Card */}
          <div className="info-card">
            <h3>Borrower</h3>
            <div className="borrower-details">
              <div className="detail-row">
                <span className="icon">👤</span>
                <span>{client?.borrower_name || client?.name}</span>
              </div>
              {client?.email && (
                <div className="detail-row">
                  <span className="icon">✉️</span>
                  <a href={`mailto:${client.email}`}>{client.email}</a>
                </div>
              )}
              {client?.phone && (
                <div className="detail-row">
                  <span className="icon">📱</span>
                  <a href={`tel:${client.phone}`}>{formatPhone(client.phone)}</a>
                </div>
              )}
              {client?.credit_score > 0 && (
                <div className="detail-row">
                  <span className="icon">📊</span>
                  <span className={`credit-score ${client.credit_score >= 700 ? 'good' : client.credit_score >= 620 ? 'fair' : 'low'}`}>
                    Credit Score: {client.credit_score}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Loan Officer Card */}
          <div className="info-card lo-card">
            <h3>Your Loan Officer</h3>
            {client?.loan_officer ? (
              <div className="lo-details">
                <div className="lo-avatar">
                  {client.loan_officer.name?.charAt(0) || 'L'}
                </div>
                <div className="lo-info">
                  <strong>{client.loan_officer.name}</strong>
                  {client.loan_officer.email && (
                    <a href={`mailto:${client.loan_officer.email}`}>
                      ✉️ {client.loan_officer.email}
                    </a>
                  )}
                  {client.loan_officer.phone && (
                    <a href={`tel:${client.loan_officer.phone}`}>
                      📞 {formatPhone(client.loan_officer.phone)}
                    </a>
                  )}
                </div>
              </div>
            ) : (
              <p className="no-lo">Loan officer will be assigned soon</p>
            )}
          </div>
        </div>

        {/* Right Column - Progress & Activity */}
        <div className="right-column">
          {/* Document Progress */}
          <DocumentProgress documents={smartDocsData || documents} loanId={smartDocsData?.loanId} />

          {/* Activity Timeline */}
          <ActivityTimeline
            activities={activities}
            stageHistory={stageHistory}
            conversationLog={conversation_log}
          />
        </div>
      </div>

      {/* Pre-Approval Modal */}
      <PreApprovalLetterModal
        isOpen={showPreApprovalModal}
        onClose={() => setShowPreApprovalModal(false)}
        clientData={clientData}
        partnerId={partnerId}
        onLetterGenerated={(data) => console.log('Letter generated:', data)}
      />
    </div>
  );
}
