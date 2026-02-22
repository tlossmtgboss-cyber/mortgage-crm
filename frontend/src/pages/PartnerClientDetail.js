/**
 * Partner Client Detail Page - Redesigned v3
 *
 * Modern card-based view matching the Client Portal UX.
 * Features:
 * - Welcome header with prominent stage badge
 * - Circular loan progress indicator
 * - Document collection with visual stats
 * - Activity timeline
 * - Key dates display
 * - Loan officer contact
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import MilestoneProgressTracker from '../components/MilestoneProgressTracker';
import PreApprovalLetterModal from '../components/PreApprovalLetterModal';
import { activitiesAPI } from '../services/api';
import './PartnerClientDetail.css';
import { toast } from '../utils/toast';

// API base URL
const API_BASE = process.env.REACT_APP_API_URL || '';

// Lifecycle stages with colors
const LIFECYCLE_STAGES = {
  // Main pipeline stages
  new: { label: 'New', color: '#3b82f6', icon: '✨' },
  new_lead: { label: 'New', color: '#3b82f6', icon: '✨' },
  attempted_contact: { label: 'Attempted Contact', color: '#8b5cf6', icon: '📞' },
  contacted: { label: 'Attempted Contact', color: '#8b5cf6', icon: '📞' },
  prospect: { label: 'Prospect', color: '#06b6d4', icon: '👤' },
  application: { label: 'Application', color: '#0ea5e9', icon: '📋' },
  pre_qualified: { label: 'Pre-Qualified', color: '#14b8a6', icon: '✅' },
  prequalified: { label: 'Pre-Qualified', color: '#14b8a6', icon: '✅' },
  qualified: { label: 'Pre-Qualified', color: '#14b8a6', icon: '✅' },
  pre_approved: { label: 'Pre-Approved', color: '#10b981', icon: '🎯' },
  preapproval: { label: 'Pre-Approved', color: '#10b981', icon: '🎯' },
  preapproved: { label: 'Pre-Approved', color: '#10b981', icon: '🎯' },

  // Exit stages
  nurture: { label: 'Nurture', color: '#f59e0b', icon: '🌱' },
  withdrawn: { label: 'Withdrawn', color: '#ef4444', icon: '🚫' },
  does_not_qualify: { label: 'Does Not Qualify', color: '#6b7280', icon: '❌' },
  dnq: { label: 'Does Not Qualify', color: '#6b7280', icon: '❌' },
};

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
  sarah_ai_user: { label: 'Client Message', icon: '👤', color: '#64748b' },
  sarah_ai_assistant: { label: 'Sarah AI', icon: '🤖', color: '#218D8D' },
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

// Format address
const formatAddress = (client) => {
  const parts = [];
  const address = client?.property_address || client?.property?.address || client?.address;
  const city = client?.property_city || client?.property?.city || client?.city;
  const state = client?.property_state || client?.property?.state || client?.state;

  if (address) parts.push(address);
  if (city) parts.push(city);
  if (state) parts.push(state);

  return parts.join(', ') || 'Property Address TBD';
};

// Format currency
const formatCurrency = (amount) => {
  if (!amount) return 'TBD';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0
  }).format(amount);
};

// Format phone
const formatPhone = (phone) => {
  if (!phone) return null;
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
};

// Calculate loan progress percentage based on stage
const calculateProgress = (stage) => {
  const stageOrder = ['new', 'new_lead', 'contacted', 'qualified', 'pre_approved', 'preapproval', 'under_contract', 'processing', 'clear_to_close', 'funded', 'closed'];
  const normalizedStage = (stage || 'new').toLowerCase().replace(/-/g, '_');
  const index = stageOrder.indexOf(normalizedStage);
  if (index === -1) return 10;
  return Math.round(((index + 1) / stageOrder.length) * 100);
};

// Progress Circle Component
const ProgressCircle = ({ percentage }) => {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className="progress-circle-container">
      <svg viewBox="0 0 100 100" className="progress-circle-svg">
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="8"
        />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#218D8D"
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
          className="progress-circle-fill"
        />
      </svg>
      <span className="progress-circle-value">{percentage}%</span>
    </div>
  );
};

// Document Stats Card - with circular progress like Loan Progress
const DocumentStatsCard = ({ documents, loanId, navigate }) => {
  const total = documents?.total || documents?.requested_count || 0;
  const received = documents?.received_count || 0;
  const outstanding = documents?.outstanding_count || 0;
  const percentage = total > 0 ? Math.round((received / total) * 100) : 0;

  return (
    <div className="dashboard-card documents-card">
      <h2>Document Progress</h2>
      <div className="progress-overview-content">
        <ProgressCircle percentage={percentage} />
        <div className="progress-stats">
          <div className="stat-item">
            <span className="stat-value">{received}/{total}</span>
            <span className="stat-label">Received</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{outstanding}</span>
            <span className="stat-label">Outstanding</span>
          </div>
        </div>
      </div>
      {documents?.outstanding?.length > 0 && (
        <div className="outstanding-list">
          <h4>Still Needed:</h4>
          <ul>
            {documents.outstanding.slice(0, 3).map((doc, idx) => (
              <li key={doc.id || idx}>
                {doc.title || doc.type || doc.name}
              </li>
            ))}
            {documents.outstanding.length > 3 && (
              <li className="more-count">+{documents.outstanding.length - 3} more</li>
            )}
          </ul>
        </div>
      )}
      {loanId && (
        <button
          className="view-all-btn"
          onClick={() => navigate(`/smart-docs/client/${loanId}`)}
        >
          View All Documents
        </button>
      )}
    </div>
  );
};

// Activity Timeline Card
const ActivityTimelineCard = ({ activities, stageHistory, chatMessages, clientId, onNoteAdded }) => {
  const [noteText, setNoteText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmitNote = async (e) => {
    e.preventDefault();
    if (!noteText.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      // Use the partner notes endpoint which sends email notifications
      const response = await fetch(
        `${process.env.REACT_APP_API_URL || ''}/api/v1/realtor-portal/clients/${clientId}/notes`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          },
          body: JSON.stringify({ content: noteText.trim() })
        }
      );

      if (!response.ok) {
        throw new Error('Failed to add note');
      }

      const data = await response.json();
      setNoteText('');
      if (onNoteAdded) onNoteAdded();

      // Show success message with notification count
      if (data.notifications_sent > 0) {
        console.log(`Note added. ${data.notifications_sent} team member(s) notified.`);
      }
    } catch (error) {
      console.error('Failed to add note:', error);
      toast.error('Failed to add note. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getTimeline = useCallback(() => {
    const timeline = [];

    (activities || []).forEach(activity => {
      timeline.push({
        id: `activity-${activity.id}`,
        type: activity.type?.toLowerCase() || 'note',
        content: activity.content || activity.notes || activity.description,
        created_at: activity.created_at,
        user: activity.user_name || activity.created_by,
      });
    });

    (stageHistory || []).forEach(history => {
      timeline.push({
        id: `stage-${history.id}`,
        type: 'stage_change',
        content: `Stage changed to "${history.to_stage}"`,
        created_at: history.changed_at,
      });
    });

    // Add Sarah AI chat messages
    (chatMessages || []).forEach(msg => {
      const isUser = msg.role === 'user';
      timeline.push({
        id: `chat-${msg.id}`,
        type: isUser ? 'sarah_ai_user' : 'sarah_ai_assistant',
        content: msg.content?.length > 150 ? msg.content.substring(0, 150) + '...' : msg.content,
        created_at: msg.created_at,
        user: isUser ? (msg.contact_name || 'Client') : 'Sarah AI',
      });
    });

    timeline.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    return timeline;
  }, [activities, stageHistory, chatMessages]);

  const timeline = getTimeline();

  return (
    <div className="dashboard-card activity-card full-width">
      <div className="card-header-with-badge">
        <h2>Conversation Log</h2>
        <span className="activity-badge">{timeline.length} updates</span>
      </div>

      {/* Add Note Form */}
      <form className="add-note-form" onSubmit={handleSubmitNote}>
        <input
          type="text"
          className="note-input"
          placeholder="Add a note..."
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
          disabled={isSubmitting}
        />
        <button
          type="submit"
          className="add-note-btn"
          disabled={!noteText.trim() || isSubmitting}
        >
          {isSubmitting ? 'Adding...' : 'Add Note'}
        </button>
      </form>

      {timeline.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">💬</span>
          <p>No conversations yet</p>
        </div>
      ) : (
        <ul className="activity-list">
          {timeline.slice(0, 8).map((item) => {
            const config = ACTIVITY_CONFIG[item.type] || { label: 'Update', icon: '📌', color: '#6b7280' };
            const isChatMessage = item.type?.startsWith('sarah_ai_');
            return (
              <li key={item.id} className="activity-item">
                <span
                  className="activity-icon"
                  style={{ background: `${config.color}15`, color: config.color }}
                >
                  {config.icon}
                </span>
                <div className="activity-content">
                  {isChatMessage && item.user && (
                    <span className="activity-user" style={{ color: config.color, fontWeight: 600 }}>
                      {item.user}:
                    </span>
                  )}
                  <p className="activity-description">{item.content}</p>
                  <span className="activity-time">{formatRelativeTime(item.created_at)}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

// Loan Summary Card
const LoanSummaryCard = ({ client }) => (
  <div className="dashboard-card loan-summary-card">
    <h2>Loan Summary</h2>
    <div className="loan-amount-highlight">
      <span className="loan-label">Loan Amount</span>
      <span className="loan-value">{formatCurrency(client?.loan_amount)}</span>
    </div>
    <div className="loan-details-grid">
      <div className="loan-detail">
        <span className="detail-label">Loan Type</span>
        <span className="detail-value">{client?.loan_type || 'Conventional'}</span>
      </div>
      <div className="loan-detail">
        <span className="detail-label">Purchase Price</span>
        <span className="detail-value">{formatCurrency(client?.purchase_price)}</span>
      </div>
      <div className="loan-detail">
        <span className="detail-label">Down Payment</span>
        <span className="detail-value">{formatCurrency(client?.down_payment)}</span>
      </div>
      <div className="loan-detail">
        <span className="detail-label">LTV</span>
        <span className="detail-value">{client?.ltv_ratio ? `${client.ltv_ratio}%` : 'TBD'}</span>
      </div>
      <div className="loan-detail">
        <span className="detail-label">Interest Rate</span>
        <span className="detail-value">{client?.interest_rate ? `${client.interest_rate}%` : 'TBD'}</span>
      </div>
      <div className="loan-detail">
        <span className="detail-label">Term</span>
        <span className="detail-value">{client?.loan_term ? `${client.loan_term} years` : '30 years'}</span>
      </div>
    </div>
  </div>
);

// Contact Card
const ContactCard = ({ client, loanOfficer }) => (
  <div className="dashboard-card contact-card">
    <h2>Contact Information</h2>

    {/* Borrower Info */}
    <div className="contact-section">
      <h3>Borrower</h3>
      <div className="contact-info">
        <div className="contact-row">
          <span className="contact-icon">👤</span>
          <span>{client?.borrower_name || client?.name}</span>
        </div>
        {client?.email && (
          <div className="contact-row">
            <span className="contact-icon">✉️</span>
            <a href={`mailto:${client.email}`}>{client.email}</a>
          </div>
        )}
        {client?.phone && (
          <div className="contact-row">
            <span className="contact-icon">📱</span>
            <a href={`tel:${client.phone}`}>{formatPhone(client.phone)}</a>
          </div>
        )}
      </div>
    </div>

    {/* Loan Officer Info */}
    <div className="contact-section lo-section">
      <h3>Loan Officer</h3>
      {loanOfficer ? (
        <div className="lo-info-card">
          <div className="lo-avatar">
            {loanOfficer.name?.charAt(0) || 'L'}
          </div>
          <div className="lo-details">
            <strong>{loanOfficer.name}</strong>
            {loanOfficer.email && (
              <a href={`mailto:${loanOfficer.email}`}>
                ✉️ {loanOfficer.email}
              </a>
            )}
            {loanOfficer.phone && (
              <a href={`tel:${loanOfficer.phone}`}>
                📞 {formatPhone(loanOfficer.phone)}
              </a>
            )}
          </div>
        </div>
      ) : (
        <p className="no-lo">Loan officer will be assigned soon</p>
      )}
    </div>
  </div>
);

// Important Dates Card - Shows key dates from the pre-approval process
const ImportantDatesCard = ({ client, stageHistory }) => {
  // Build list of important dates from stage history and client data
  const formatDate = (dateValue) => {
    if (!dateValue) return null;
    return new Date(dateValue).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Get stage-specific dates from history
  const getStageDate = (stageName) => {
    const entry = stageHistory?.find(h =>
      h.to_stage?.toLowerCase().replace(/[_-]/g, '') === stageName.toLowerCase().replace(/[_-]/g, '')
    );
    return entry?.changed_at;
  };

  const importantDates = [
    { label: 'Application Started', value: client?.created_at, icon: '📝' },
    { label: 'Pre-Qualified', value: getStageDate('qualified'), icon: '✓' },
    { label: 'Pre-Approved', value: getStageDate('pre_approved') || getStageDate('preapproval'), icon: '🎯' },
    { label: 'Under Contract', value: getStageDate('under_contract'), icon: '📋' },
    { label: 'Clear to Close', value: getStageDate('clear_to_close'), icon: '🏁' },
    { label: 'Expected Close', value: client?.expected_close_date, icon: '📅' },
  ].filter(d => d.value);

  return (
    <div className="dashboard-card important-dates-card">
      <h2>Important Dates</h2>
      {importantDates.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">📅</span>
          <p>No milestone dates recorded yet</p>
        </div>
      ) : (
        <div className="important-dates-list">
          {importantDates.map((date, idx) => (
            <div key={idx} className="important-date-item">
              <span className="date-icon">{date.icon}</span>
              <div className="date-info">
                <span className="date-label">{date.label}</span>
                <span className="date-value">{formatDate(date.value)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Main Component
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
  const [chatMessages, setChatMessages] = useState([]);

  useEffect(() => {
    loadClientData();
  }, [clientId]);

  useEffect(() => {
    if (clientData?.client?.id) {
      loadActivities();
      loadStageHistory();
      loadSmartDocsData();
      loadChatMessages();
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

  const loadChatMessages = async () => {
    try {
      const jwtToken = localStorage.getItem('token');
      if (!jwtToken) return;

      const response = await fetch(
        `${API_BASE}/api/v1/leads/${clientId}/chat-messages?limit=20`,
        {
          headers: {
            'Authorization': `Bearer ${jwtToken}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setChatMessages(data.messages || []);
      }
    } catch (err) {
      console.error('Error loading chat messages:', err);
    }
  };

  const loadSmartDocsData = async () => {
    try {
      const jwtToken = localStorage.getItem('token');
      if (!jwtToken) return;

      const leadEmail = clientData?.client?.email;
      const leadId = clientData?.client?.id;

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
        const borrowerName = clientData?.client?.borrower_name || clientData?.client?.name;
        const matchingLoan = queueData.find(loan =>
          (leadEmail && loan.borrower_email?.toLowerCase() === leadEmail.toLowerCase()) ||
          (borrowerName && loan.borrower_name?.toLowerCase().includes(borrowerName.toLowerCase()))
        );

        if (matchingLoan) {
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

      // Fallback
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
                requested_count: 0
              },
              conversations: []
            });
            return;
          } else {
            // Handle JWT auth errors with specific messages
            if (response.status === 401) {
              throw new Error('Session expired. Please log in again.');
            } else if (response.status === 403) {
              throw new Error('You do not have permission to view this client.');
            } else if (response.status === 404) {
              throw new Error('Client not found.');
            }
            // For other errors, fall through to try partner token auth
          }
        } catch (jwtError) {
          console.error('JWT auth failed:', jwtError);
          // If we have a specific error message, show it instead of falling through
          if (jwtError.message && jwtError.message !== 'Failed to fetch') {
            setError(jwtError.message);
            setLoading(false);
            return;
          }
        }
      }

      if (!partnerToken) {
        setError('Authentication required. Please log in to view this client.');
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

  if (loading) {
    return (
      <div className="partner-client-detail-v3 loading-state">
        <div className="loading-spinner" />
        <p>Loading client details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="partner-client-detail-v3 error-state">
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
      <div className="partner-client-detail-v3 error-state">
        <h2>Client Not Found</h2>
        <button className="btn-back" onClick={() => navigate(-1)}>Go Back</button>
      </div>
    );
  }

  const { client, documents } = clientData;
  const currentStage = (client?.status || client?.stage || 'new').toLowerCase().replace(/-/g, '_');
  const stageInfo = LIFECYCLE_STAGES[currentStage] || LIFECYCLE_STAGES.new;
  const progressPercent = calculateProgress(currentStage);

  return (
    <div className="partner-client-detail-v3">
      {/* Top Navigation */}
      <nav className="top-nav">
        <button className="back-btn" onClick={() => navigate(-1)}>
          ← Back to Dashboard
        </button>
      </nav>

      {/* Welcome Header */}
      <header className="welcome-header">
        <div className="header-content">
          <div className="client-identity">
            <div className="client-avatar-large">
              {(client?.first_name || client?.borrower_name || 'C').charAt(0).toUpperCase()}
            </div>
            <div className="client-info">
              <h1>{client?.borrower_name || client?.name || 'Client'}</h1>
              <p className="property-address">📍 {formatAddress(client)}</p>
            </div>
          </div>

          {/* Loan Summary - Centered */}
          <div className="header-loan-summary">
            <div className="summary-item">
              <span className="summary-value highlight">{formatCurrency(client?.loan_amount)}</span>
              <span className="summary-label">Loan Amount</span>
            </div>
            <div className="summary-divider"></div>
            <div className="summary-item">
              <span className="summary-value">{client?.loan_type || 'Conventional'}</span>
              <span className="summary-label">Loan Type</span>
            </div>
            <div className="summary-divider"></div>
            <div className="summary-item">
              <span className="summary-value">{stageInfo.label}</span>
              <span className="summary-label">Current Stage</span>
            </div>
          </div>

          <div className="header-right">
            <button className="btn-primary" onClick={() => setShowPreApprovalModal(true)}>
              Pre-Approval Letter
            </button>
          </div>
        </div>
      </header>

      {/* Progress Section */}
      <section className="progress-section">
        <MilestoneProgressTracker currentStatus={currentStage} />
      </section>

      {/* Main Dashboard Grid */}
      <div className="dashboard-grid">
        {/* Important Dates Card */}
        <ImportantDatesCard client={client} stageHistory={stageHistory} />

        {/* Documents */}
        <DocumentStatsCard
          documents={smartDocsData || documents}
          loanId={smartDocsData?.loanId}
          navigate={navigate}
        />

        {/* Contact Information - Next to Document Progress */}
        <ContactCard client={client} loanOfficer={client?.loan_officer} />

        {/* Activity Timeline */}
        <ActivityTimelineCard
          activities={activities}
          stageHistory={stageHistory}
          chatMessages={chatMessages}
          clientId={parseInt(clientId)}
          onNoteAdded={loadActivities}
        />
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
