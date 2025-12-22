/**
 * Partner Client Detail Page
 *
 * Comprehensive single-page view of a referred client for partner portal.
 * Features:
 * - Property address in header
 * - Visual milestone progress tracker
 * - Key dates based on current stage
 * - Loan summary, borrower info, property details, LO contact
 * - Collapsible outstanding items section
 * - Pre-approval letter generation button
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import MilestoneProgressTracker from '../components/MilestoneProgressTracker';
import PreApprovalLetterModal from '../components/PreApprovalLetterModal';
import { activitiesAPI } from '../services/api';
import './PartnerClientDetail.css';

// API base URL
const API_BASE = process.env.REACT_APP_API_URL || '';

// Activity type configuration for display
const ACTIVITY_CONFIG = {
  note: { label: 'Note', color: '#6366f1' },
  call: { label: 'Call', color: '#10b981' },
  email: { label: 'Email', color: '#3b82f6' },
  sms: { label: 'SMS', color: '#8b5cf6' },
  meeting: { label: 'Meeting', color: '#f59e0b' },
  task: { label: 'Task', color: '#ef4444' },
  document: { label: 'Document', color: '#06b6d4' },
  status_change: { label: 'Status Change', color: '#218D8D' },
  stage_change: { label: 'Stage Change', color: '#218D8D' },
};

// Format relative time for activities
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

// Status badge component
const StatusBadge = ({ status, size = 'normal' }) => {
  const statusConfig = {
    'New': { color: 'blue', label: 'New Lead' },
    'new': { color: 'blue', label: 'New Lead' },
    'lead': { color: 'blue', label: 'Lead' },
    'Attempted Contact': { color: 'yellow', label: 'Attempted Contact' },
    'attempted_contact': { color: 'yellow', label: 'Attempted Contact' },
    'Prospect': { color: 'purple', label: 'Prospect' },
    'prospect': { color: 'purple', label: 'Prospect' },
    'Application': { color: 'orange', label: 'Application' },
    'application': { color: 'orange', label: 'Application' },
    'processing': { color: 'cyan', label: 'Processing' },
    'submitted': { color: 'indigo', label: 'Submitted' },
    'underwriting': { color: 'violet', label: 'Underwriting' },
    'Pre-Qualified': { color: 'cyan', label: 'Pre-Qualified' },
    'pre_qualified': { color: 'cyan', label: 'Pre-Qualified' },
    'Pre-Approved': { color: 'green', label: 'Pre-Approved' },
    'pre_approved': { color: 'green', label: 'Pre-Approved' },
    'conditional_approval': { color: 'green', label: 'Conditional Approval' },
    'under_contract': { color: 'teal', label: 'Under Contract' },
    'clear_to_close': { color: 'emerald', label: 'Clear to Close' },
    'Completed': { color: 'emerald', label: 'Completed' },
    'funded': { color: 'emerald', label: 'Funded' },
    'Withdrawn': { color: 'gray', label: 'Withdrawn' },
    'denied': { color: 'red', label: 'Denied' },
  };

  const config = statusConfig[status] || { color: 'gray', label: status };

  return (
    <span className={`status-badge status-${config.color} ${size === 'large' ? 'badge-large' : ''}`}>
      {config.label}
    </span>
  );
};

// Format full property address
const formatAddress = (client) => {
  const parts = [];

  // Handle different data structures
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

// Key dates component based on stage
const KeyDates = ({ client, stage }) => {
  const getDatesForStage = () => {
    const dates = [];

    // Always show created date
    if (client?.created_at) {
      dates.push({
        label: 'Lead Created',
        date: client.created_at,
        completed: true
      });
    }

    // Application stage and beyond
    if (['application', 'Application', 'pre_qualified', 'Pre-Qualified', 'pre_approved', 'Pre-Approved',
         'under_contract', 'processing', 'submitted', 'underwriting', 'clear_to_close', 'funded', 'Completed'].includes(stage)) {
      if (client?.application_date || client?.application_submitted_at) {
        dates.push({
          label: 'Application Submitted',
          date: client.application_date || client.application_submitted_at,
          completed: true
        });
      }
    }

    // Pre-qualified stage and beyond
    if (['pre_qualified', 'Pre-Qualified', 'pre_approved', 'Pre-Approved', 'under_contract',
         'processing', 'submitted', 'underwriting', 'clear_to_close', 'funded', 'Completed'].includes(stage)) {
      if (client?.credit_pulled_at) {
        dates.push({
          label: 'Credit Pulled',
          date: client.credit_pulled_at,
          completed: true
        });
      }
    }

    // Pre-approved stage and beyond
    if (['pre_approved', 'Pre-Approved', 'under_contract', 'processing', 'submitted',
         'underwriting', 'clear_to_close', 'funded', 'Completed'].includes(stage)) {
      if (client?.preapproval_date || client?.pre_approval_date) {
        dates.push({
          label: 'Pre-Approval Issued',
          date: client.preapproval_date || client.pre_approval_date,
          completed: true
        });
      }
      if (client?.preapproval_expiration || client?.pre_approval_expiration) {
        dates.push({
          label: 'Pre-Approval Expires',
          date: client.preapproval_expiration || client.pre_approval_expiration,
          completed: false,
          isDeadline: true
        });
      }
    }

    // Under contract and beyond
    if (['under_contract', 'processing', 'submitted', 'underwriting', 'clear_to_close', 'funded', 'Completed'].includes(stage)) {
      if (client?.contract_date) {
        dates.push({
          label: 'Contract Date',
          date: client.contract_date,
          completed: true
        });
      }
    }

    // Expected close always shown if available
    if (client?.expected_close_date || client?.closing_date) {
      dates.push({
        label: 'Expected Close',
        date: client.expected_close_date || client.closing_date,
        completed: stage === 'funded' || stage === 'Completed',
        isTarget: true
      });
    }

    // Funded date
    if ((stage === 'funded' || stage === 'Completed') && client?.funded_at) {
      dates.push({
        label: 'Funded',
        date: client.funded_at,
        completed: true
      });
    }

    return dates;
  };

  const formatDateDisplay = (dateStr) => {
    if (!dateStr) return 'TBD';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    } catch {
      return dateStr;
    }
  };

  const dates = getDatesForStage();

  if (dates.length === 0) {
    return null;
  }

  return (
    <div className="key-dates-section">
      <h3 className="section-title">Key Dates</h3>
      <div className="dates-grid">
        {dates.map((item, idx) => (
          <div
            key={idx}
            className={`date-card ${item.completed ? 'completed' : ''} ${item.isDeadline ? 'deadline' : ''} ${item.isTarget ? 'target' : ''}`}
          >
            <span className="date-label">{item.label}</span>
            <span className="date-value">{formatDateDisplay(item.date)}</span>
            {item.completed && <span className="date-check">&#10003;</span>}
          </div>
        ))}
      </div>
    </div>
  );
};

// Collapsible section component
const CollapsibleSection = ({ title, count, children, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`collapsible-section ${isOpen ? 'open' : ''}`}>
      <button
        className="collapsible-header"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="collapsible-title">
          {title}
          {count !== undefined && count > 0 && (
            <span className="count-badge">{count}</span>
          )}
        </span>
        <span className={`chevron ${isOpen ? 'open' : ''}`}>&#9660;</span>
      </button>
      {isOpen && (
        <div className="collapsible-content">
          {children}
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

  useEffect(() => {
    loadClientData();
  }, [clientId]);

  // Fetch activities and stage history after client data is loaded
  useEffect(() => {
    if (clientData?.client?.id) {
      loadActivities();
      loadStageHistory();
    }
  }, [clientData?.client?.id]);

  const loadActivities = async () => {
    try {
      const jwtToken = localStorage.getItem('token');
      if (!jwtToken) return; // Only fetch if CRM user is logged in

      const activitiesData = await activitiesAPI.getAll({ lead_id: clientId });
      setActivities(activitiesData || []);
    } catch (err) {
      console.error('Error loading activities:', err);
      // Don't show error to user - activities are supplementary
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

  // Combine activities and stage history into unified timeline
  const getCombinedTimeline = () => {
    const timeline = [];

    // Add activities
    activities.forEach(activity => {
      timeline.push({
        id: `activity-${activity.id}`,
        type: activity.type?.toLowerCase() || 'note',
        content: activity.content,
        created_at: activity.created_at,
        source: 'activity',
      });
    });

    // Add stage changes
    stageHistory.forEach(history => {
      timeline.push({
        id: `stage-${history.id}`,
        type: 'stage_change',
        content: `Status changed from "${history.from_stage || 'New'}" to "${history.to_stage}"`,
        created_at: history.changed_at,
        from_stage: history.from_stage,
        to_stage: history.to_stage,
        source: 'stage_history',
      });
    });

    // Sort by date (newest first)
    timeline.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    return timeline;
  };

  const loadClientData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Check for CRM JWT token first (internal user), then partner token (external partner)
      const jwtToken = localStorage.getItem('token');
      const partnerToken = localStorage.getItem('partnerToken') || new URLSearchParams(window.location.search).get('token');

      let response;

      // Try CRM authentication first if token exists
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
            // Transform lead data to match expected client data format
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
                application_date: leadData.application_date,
                // Employment info
                employer: leadData.employer,
                job_title: leadData.job_title,
                annual_income: leadData.annual_income,
                // LO info
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
                received_count: 0
              },
              milestones: [],
              conversations: []
            });
            return;
          } else if (response.status === 404) {
            throw new Error('Lead not found');
          } else if (response.status === 401) {
            console.log('JWT expired, trying partner token...');
          } else {
            throw new Error(`Failed to load lead: ${response.status}`);
          }
        } catch (jwtError) {
          console.error('JWT auth failed:', jwtError);
          if (jwtError.message && !jwtError.message.includes('401')) {
            throw jwtError;
          }
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
        if (response.status === 401) {
          throw new Error('Session expired. Please log in again.');
        }
        if (response.status === 403) {
          throw new Error('You do not have access to this client.');
        }
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
    if (!amount) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const formatPhone = (phone) => {
    if (!phone) return 'N/A';
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
    }
    return phone;
  };

  const handleGeneratePreApproval = () => {
    setShowPreApprovalModal(true);
  };

  const handleContactLO = () => {
    if (clientData?.client?.loan_officer?.email) {
      window.location.href = `mailto:${clientData.client.loan_officer.email}`;
    }
  };

  if (loading) {
    return (
      <div className="partner-client-detail loading">
        <div className="loading-spinner" />
        <p>Loading client details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="partner-client-detail error">
        <div className="error-content">
          <h2>Error</h2>
          <p>{error}</p>
          <button onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  if (!clientData) {
    return (
      <div className="partner-client-detail not-found">
        <h2>Client Not Found</h2>
        <button onClick={() => navigate(-1)}>Go Back</button>
      </div>
    );
  }

  const { client, documents, milestones, third_party_orders, conversation_log } = clientData;
  const currentStage = client?.status || client?.stage || 'new';

  return (
    <div className="partner-client-detail single-page">
      {/* Header with Property Address */}
      <header className="client-header-new">
        <button className="back-btn" onClick={() => navigate(-1)}>
          &#8592; Back to Portal
        </button>

        <div className="header-property">
          <span className="property-icon">&#127968;</span>
          <h1 className="property-address">{formatAddress(client)}</h1>
        </div>

        <div className="header-details">
          <span className="borrower-name">{client?.borrower_name || client?.name || 'Unknown Borrower'}</span>
          <span className="separator">&#8226;</span>
          <span className="loan-number">Loan #{client?.loan_number || client?.id}</span>
          <span className="separator">&#8226;</span>
          <span className="loan-info">{client?.loan_type || 'Loan Type TBD'} {formatCurrency(client?.loan_amount)}</span>
        </div>

        <div className="header-actions">
          <button className="btn-primary" onClick={handleGeneratePreApproval}>
            Generate Pre-Approval Letter
          </button>
          <button className="btn-secondary" onClick={handleContactLO}>
            Contact Loan Officer
          </button>
        </div>
      </header>

      {/* Milestone Progress Tracker */}
      <section className="milestone-section">
        <MilestoneProgressTracker currentStatus={currentStage} />
      </section>

      {/* Key Dates */}
      <KeyDates client={client} stage={currentStage} />

      {/* Main Content Grid */}
      <div className="content-grid">
        {/* Loan Summary Card */}
        <section className="info-card loan-summary">
          <h3 className="card-title">Loan Summary</h3>
          <div className="info-grid">
            <div className="info-item">
              <label>Loan Amount</label>
              <span className="value-large">{formatCurrency(client?.loan_amount)}</span>
            </div>
            <div className="info-item">
              <label>Loan Type</label>
              <span>{client?.loan_type || 'TBD'}</span>
            </div>
            <div className="info-item">
              <label>Interest Rate</label>
              <span>{client?.interest_rate ? `${client.interest_rate}%` : 'TBD'}</span>
            </div>
            <div className="info-item">
              <label>Loan Term</label>
              <span>{client?.loan_term ? `${client.loan_term} years` : 'TBD'}</span>
            </div>
            <div className="info-item">
              <label>LTV</label>
              <span>{client?.ltv_ratio ? `${client.ltv_ratio}%` : 'TBD'}</span>
            </div>
            <div className="info-item">
              <label>Down Payment</label>
              <span>{formatCurrency(client?.down_payment) || 'TBD'}</span>
            </div>
          </div>
          <div className="card-status">
            <StatusBadge status={currentStage} size="large" />
          </div>
        </section>

        {/* Borrower Information */}
        <section className="info-card borrower-info">
          <h3 className="card-title">Borrower Information</h3>
          <div className="info-grid">
            <div className="info-item">
              <label>Name</label>
              <span>{client?.borrower_name || client?.name || 'N/A'}</span>
            </div>
            <div className="info-item">
              <label>Email</label>
              <span className="email-link">
                {client?.email ? (
                  <a href={`mailto:${client.email}`}>{client.email}</a>
                ) : 'N/A'}
              </span>
            </div>
            <div className="info-item">
              <label>Phone</label>
              <span>{formatPhone(client?.phone)}</span>
            </div>
            <div className="info-item">
              <label>Credit Score</label>
              <span className={client?.credit_score >= 700 ? 'score-good' : client?.credit_score >= 620 ? 'score-fair' : 'score-low'}>
                {client?.credit_score || 'N/A'}
              </span>
            </div>
            {client?.employer && (
              <div className="info-item">
                <label>Employer</label>
                <span>{client.employer}</span>
              </div>
            )}
            {client?.annual_income && (
              <div className="info-item">
                <label>Annual Income</label>
                <span>{formatCurrency(client.annual_income)}</span>
              </div>
            )}
          </div>
        </section>

        {/* Property Details */}
        <section className="info-card property-details">
          <h3 className="card-title">Property Details</h3>
          <div className="info-grid">
            <div className="info-item full-width">
              <label>Address</label>
              <span>{formatAddress(client)}</span>
            </div>
            <div className="info-item">
              <label>Property Type</label>
              <span>{client?.property_type || 'TBD'}</span>
            </div>
            <div className="info-item">
              <label>Purchase Price</label>
              <span>{formatCurrency(client?.purchase_price || client?.property_value)}</span>
            </div>
          </div>
        </section>

        {/* Loan Officer Contact */}
        <section className="info-card lo-contact">
          <h3 className="card-title">Your Loan Officer</h3>
          {client?.loan_officer ? (
            <div className="lo-card-content">
              <div className="lo-avatar">
                {client.loan_officer.name?.charAt(0) || 'L'}
              </div>
              <div className="lo-details">
                <h4>{client.loan_officer.name || 'Assigned LO'}</h4>
                {client.loan_officer.email && (
                  <p><a href={`mailto:${client.loan_officer.email}`}>{client.loan_officer.email}</a></p>
                )}
                {client.loan_officer.phone && (
                  <p><a href={`tel:${client.loan_officer.phone}`}>{formatPhone(client.loan_officer.phone)}</a></p>
                )}
              </div>
            </div>
          ) : (
            <p className="no-data">Loan officer not yet assigned</p>
          )}
        </section>
      </div>

      {/* Outstanding Items - Collapsible */}
      {documents && (documents.outstanding_count > 0 || documents.outstanding?.length > 0) && (
        <CollapsibleSection
          title="Outstanding Items"
          count={documents.outstanding_count || documents.outstanding?.length}
          defaultOpen={false}
        >
          <div className="outstanding-items">
            {documents.outstanding?.length > 0 ? (
              documents.outstanding.map((doc, idx) => (
                <div key={idx} className="outstanding-item">
                  <span className={`priority-indicator priority-${doc.priority?.toLowerCase() || 'normal'}`} />
                  <div className="item-info">
                    <span className="item-title">{doc.title || doc.type}</span>
                    {doc.due_date && <span className="item-due">Due: {doc.due_date}</span>}
                  </div>
                  <span className={`item-status status-${doc.status?.toLowerCase() || 'pending'}`}>
                    {doc.status === 'OPEN' ? 'Needed' : doc.status}
                  </span>
                </div>
              ))
            ) : (
              <p className="no-items">No outstanding documents</p>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Activity Timeline - Collapsible */}
      <CollapsibleSection title="Recent Activity" defaultOpen={true} count={getCombinedTimeline().length}>
        <div className="activity-timeline">
          {(() => {
            const timeline = getCombinedTimeline();
            // Fall back to conversation_log if no activities from API
            const displayItems = timeline.length > 0 ? timeline : (conversation_log || []);

            if (displayItems.length === 0) {
              return <p className="no-data">No recent activity</p>;
            }

            return displayItems.slice(0, 10).map((item, idx) => {
              const activityConfig = ACTIVITY_CONFIG[item.type] || { label: item.type || 'Update', color: '#6b7280' };

              return (
                <div key={item.id || idx} className="activity-item">
                  <div
                    className="activity-dot"
                    style={{ backgroundColor: activityConfig.color }}
                  />
                  <div className="activity-content">
                    <div className="activity-header">
                      <span
                        className="activity-type-badge"
                        style={{ backgroundColor: `${activityConfig.color}15`, color: activityConfig.color }}
                      >
                        {activityConfig.label}
                      </span>
                      <span className="activity-time">{formatRelativeTime(item.created_at)}</span>
                    </div>
                    <span className="activity-text">
                      {item.content || item.description || 'Activity logged'}
                    </span>
                  </div>
                </div>
              );
            });
          })()}
        </div>
      </CollapsibleSection>

      {/* Third-Party Orders - Collapsible */}
      {third_party_orders && (
        <CollapsibleSection title="Third-Party Orders" defaultOpen={false}>
          <div className="orders-summary">
            <div className={`order-item ${third_party_orders.appraisal?.received_date ? 'complete' : ''}`}>
              <span className="order-icon">&#127968;</span>
              <span className="order-name">Appraisal</span>
              <span className="order-status">
                {third_party_orders.appraisal?.received_date ? 'Complete' :
                 third_party_orders.appraisal?.ordered_date ? 'In Progress' : 'Not Ordered'}
              </span>
            </div>
            <div className={`order-item ${third_party_orders.title?.received_date ? 'complete' : ''}`}>
              <span className="order-icon">&#128203;</span>
              <span className="order-name">Title</span>
              <span className="order-status">
                {third_party_orders.title?.received_date ? 'Complete' :
                 third_party_orders.title?.ordered_date ? 'In Progress' : 'Not Ordered'}
              </span>
            </div>
            <div className={`order-item ${third_party_orders.homeowners_insurance?.received_date ? 'complete' : ''}`}>
              <span className="order-icon">&#128737;</span>
              <span className="order-name">Insurance</span>
              <span className="order-status">
                {third_party_orders.homeowners_insurance?.received_date ? 'Complete' :
                 third_party_orders.homeowners_insurance?.ordered_date ? 'In Progress' : 'Not Ordered'}
              </span>
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* Pre-Approval Letter Modal */}
      <PreApprovalLetterModal
        isOpen={showPreApprovalModal}
        onClose={() => setShowPreApprovalModal(false)}
        clientData={clientData}
        partnerId={partnerId}
        onLetterGenerated={(data) => {
          console.log('Letter generated:', data);
        }}
      />
    </div>
  );
}
