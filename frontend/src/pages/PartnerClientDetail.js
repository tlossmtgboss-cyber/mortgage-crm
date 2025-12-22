/**
 * Partner Client Detail Page
 *
 * Comprehensive view of a referred client for partner portal.
 * Shows all loan information, documents, milestones, third-party orders,
 * and conversation history.
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './PartnerClientDetail.css';

// API base URL
const API_BASE = process.env.REACT_APP_API_URL || '';

// Status badge component
const StatusBadge = ({ status, size = 'normal' }) => {
  const statusConfig = {
    'New': { color: 'blue', label: 'New Lead' },
    'lead': { color: 'blue', label: 'Lead' },
    'Attempted Contact': { color: 'yellow', label: 'Attempted Contact' },
    'Prospect': { color: 'purple', label: 'Prospect' },
    'Application': { color: 'orange', label: 'Application' },
    'application': { color: 'orange', label: 'Application' },
    'processing': { color: 'cyan', label: 'Processing' },
    'submitted': { color: 'indigo', label: 'Submitted' },
    'underwriting': { color: 'violet', label: 'Underwriting' },
    'Pre-Qualified': { color: 'cyan', label: 'Pre-Qualified' },
    'Pre-Approved': { color: 'green', label: 'Pre-Approved' },
    'conditional_approval': { color: 'green', label: 'Conditional Approval' },
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

// Priority indicator
const PriorityDot = ({ priority }) => {
  const colors = {
    'CRITICAL': '#ef4444',
    'HIGH': '#f97316',
    'NORMAL': '#3b82f6',
    'LOW': '#6b7280'
  };
  return (
    <span
      className="priority-dot"
      style={{ backgroundColor: colors[priority] || colors.NORMAL }}
      title={priority}
    />
  );
};

// Document status badge
const DocStatusBadge = ({ status }) => {
  const config = {
    'OPEN': { color: 'yellow', label: 'Needed' },
    'PENDING_REVIEW': { color: 'blue', label: 'Under Review' },
    'ACCEPTED': { color: 'green', label: 'Accepted' },
    'REJECTED': { color: 'red', label: 'Rejected' },
    'WAIVED': { color: 'gray', label: 'Waived' }
  };
  const c = config[status] || { color: 'gray', label: status };
  return <span className={`doc-status-badge doc-status-${c.color}`}>{c.label}</span>;
};

// Order status component
const OrderStatus = ({ order, type, icon }) => {
  if (!order) {
    return (
      <div className="order-card order-pending">
        <div className="order-icon">{icon}</div>
        <div className="order-content">
          <h4>{type}</h4>
          <p className="order-status">Not Ordered</p>
        </div>
      </div>
    );
  }

  const isReceived = order.received_date;
  const isOrdered = order.ordered_date;

  return (
    <div className={`order-card ${isReceived ? 'order-complete' : 'order-in-progress'}`}>
      <div className="order-icon">{icon}</div>
      <div className="order-content">
        <h4>{type}</h4>
        <p className="order-vendor">{order.vendor || 'Vendor TBD'}</p>
        <div className="order-dates">
          {isOrdered && (
            <div className="date-row">
              <span className="date-label">Ordered:</span>
              <span className="date-value">{order.ordered_date}</span>
            </div>
          )}
          {order.due_date && !isReceived && (
            <div className="date-row">
              <span className="date-label">Due:</span>
              <span className="date-value">{order.due_date}</span>
            </div>
          )}
          {isReceived && (
            <div className="date-row received">
              <span className="date-label">Received:</span>
              <span className="date-value">{order.received_date}</span>
            </div>
          )}
        </div>
        <p className={`order-status ${isReceived ? 'complete' : ''}`}>
          {isReceived ? '✓ Complete' : order.status || 'In Progress'}
        </p>
      </div>
    </div>
  );
};

// Milestone timeline component
const MilestoneTimeline = ({ milestones }) => {
  if (!milestones || milestones.length === 0) {
    return <p className="no-data">No milestones available</p>;
  }

  return (
    <div className="milestone-timeline">
      {milestones.map((milestone, index) => (
        <div
          key={milestone.id || index}
          className={`milestone-item ${milestone.is_completed ? 'completed' : ''}`}
        >
          <div className="milestone-indicator">
            {milestone.is_completed ? '✓' : (index + 1)}
          </div>
          <div className="milestone-content">
            <h4>{milestone.name}</h4>
            {milestone.target_date && (
              <p className="milestone-date">
                {milestone.is_completed ? 'Completed' : 'Target'}: {milestone.is_completed ? milestone.completed_at : milestone.target_date}
              </p>
            )}
            {milestone.notes && <p className="milestone-notes">{milestone.notes}</p>}
          </div>
        </div>
      ))}
    </div>
  );
};

// Conversation log component
const ConversationLog = ({ conversations }) => {
  if (!conversations || conversations.length === 0) {
    return <p className="no-data">No conversation history</p>;
  }

  return (
    <div className="conversation-log">
      {conversations.map((conv, index) => (
        <div
          key={conv.id || index}
          className={`conversation-item ${conv.direction === 'inbound' ? 'inbound' : 'outbound'}`}
        >
          <div className="conv-header">
            <span className="conv-channel">{conv.channel}</span>
            <span className="conv-time">{conv.created_at}</span>
          </div>
          <p className="conv-content">{conv.content}</p>
        </div>
      ))}
    </div>
  );
};

export default function PartnerClientDetail() {
  const { partnerId, clientId } = useParams();
  const navigate = useNavigate();
  const [clientData, setClientData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    loadClientData();
  }, [clientId]);

  const loadClientData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Check for CRM JWT token first (internal user), then partner token (external partner)
      const jwtToken = localStorage.getItem('token');
      const partnerToken = localStorage.getItem('partnerToken') || new URLSearchParams(window.location.search).get('token');

      let response;

      if (jwtToken) {
        // Internal CRM user - use leads API with JWT auth
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
              email: leadData.email,
              phone: leadData.phone,
              status: leadData.stage,
              loan_amount: leadData.loan_amount,
              property_address: leadData.address,
              property_city: leadData.city,
              property_state: leadData.state,
              property_zip: leadData.zip_code,
              property_type: leadData.property_type,
              loan_type: leadData.loan_type,
              credit_score: leadData.credit_score,
              created_at: leadData.created_at,
              updated_at: leadData.updated_at
            },
            milestones: [],
            documents: [],
            conversations: []
          });
          return;
        }
      }

      // Fall back to partner portal token
      if (!partnerToken) {
        setError('Authentication required');
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

  const { client, documents, milestones, third_party_orders, conversation_log, important_dates } = clientData;

  return (
    <div className="partner-client-detail">
      {/* Header */}
      <header className="client-header">
        <button className="back-btn" onClick={() => navigate(-1)}>
          ← Back to Portal
        </button>
        <div className="header-main">
          <div className="client-avatar">
            {client.borrower_name?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div className="client-info">
            <h1>{client.borrower_name || 'Unknown Client'}</h1>
            <p className="loan-number">Loan #{client.loan_number || client.loan_id}</p>
          </div>
          <StatusBadge status={client.status} size="large" />
        </div>
      </header>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <span className="summary-label">Loan Amount</span>
          <span className="summary-value">{formatCurrency(client.loan_amount)}</span>
        </div>
        <div className="summary-card">
          <span className="summary-label">Loan Type</span>
          <span className="summary-value">{client.loan_type || 'N/A'}</span>
        </div>
        <div className="summary-card">
          <span className="summary-label">Interest Rate</span>
          <span className="summary-value">
            {client.interest_rate ? `${client.interest_rate}%` : 'TBD'}
          </span>
        </div>
        <div className="summary-card">
          <span className="summary-label">Expected Close</span>
          <span className="summary-value">{client.expected_close_date || 'TBD'}</span>
        </div>
      </div>

      {/* Tab Navigation */}
      <nav className="tab-nav">
        {['overview', 'documents', 'milestones', 'orders', 'messages'].map(tab => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
            {tab === 'documents' && documents.outstanding_count > 0 && (
              <span className="tab-badge">{documents.outstanding_count}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            {/* Property Info */}
            <section className="detail-section">
              <h3>Property Information</h3>
              <div className="info-grid">
                <div className="info-item">
                  <label>Address</label>
                  <span>{client.property?.address || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>City</label>
                  <span>{client.property?.city || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>State</label>
                  <span>{client.property?.state || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>ZIP</label>
                  <span>{client.property?.zip || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>Property Type</label>
                  <span>{client.property?.type || 'N/A'}</span>
                </div>
              </div>
            </section>

            {/* Loan Officer Info */}
            <section className="detail-section">
              <h3>Loan Officer</h3>
              <div className="lo-card">
                <div className="lo-avatar">
                  {client.loan_officer?.name?.charAt(0) || 'L'}
                </div>
                <div className="lo-info">
                  <h4>{client.loan_officer?.name || 'Assigned LO'}</h4>
                  <p>{client.loan_officer?.email}</p>
                  <p>{client.loan_officer?.phone}</p>
                </div>
              </div>
            </section>

            {/* Financials */}
            <section className="detail-section">
              <h3>Financial Details</h3>
              <div className="info-grid">
                <div className="info-item">
                  <label>Credit Score</label>
                  <span>{client.financials?.credit_score || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>DTI Ratio</label>
                  <span>{client.financials?.dti_ratio ? `${client.financials.dti_ratio}%` : 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>LTV Ratio</label>
                  <span>{client.financials?.ltv_ratio ? `${client.financials.ltv_ratio}%` : 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>Loan Term</label>
                  <span>{client.loan_term ? `${client.loan_term} years` : 'N/A'}</span>
                </div>
              </div>
            </section>

            {/* Important Dates */}
            {important_dates && important_dates.length > 0 && (
              <section className="detail-section">
                <h3>Important Dates</h3>
                <div className="dates-list">
                  {important_dates.map((date, idx) => (
                    <div key={idx} className={`date-item ${date.is_completed ? 'completed' : ''}`}>
                      <span className="date-type">{date.type}</span>
                      <span className="date-value">{date.date}</span>
                      {date.is_completed && <span className="date-check">✓</span>}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {activeTab === 'documents' && (
          <div className="documents-tab">
            {/* Outstanding Documents */}
            <section className="detail-section">
              <h3>
                Outstanding Documents
                <span className="section-count">{documents.outstanding_count}</span>
              </h3>
              {documents.outstanding.length === 0 ? (
                <p className="no-data success">All documents received!</p>
              ) : (
                <div className="doc-list">
                  {documents.outstanding.map((doc, idx) => (
                    <div key={idx} className="doc-item outstanding">
                      <PriorityDot priority={doc.priority} />
                      <div className="doc-info">
                        <h4>{doc.title || doc.type}</h4>
                        <p className="doc-type">{doc.type}</p>
                        {doc.due_date && (
                          <p className="doc-due">Due: {doc.due_date}</p>
                        )}
                        {doc.applies_to && (
                          <span className="doc-applies">{doc.applies_to}</span>
                        )}
                      </div>
                      <DocStatusBadge status={doc.status} />
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Received Documents */}
            <section className="detail-section">
              <h3>
                Received Documents
                <span className="section-count">{documents.received_count}</span>
              </h3>
              {documents.received.length === 0 ? (
                <p className="no-data">No documents received yet</p>
              ) : (
                <div className="doc-list">
                  {documents.received.map((doc, idx) => (
                    <div key={idx} className="doc-item received">
                      <div className="doc-info">
                        <h4>{doc.title || doc.type}</h4>
                        <p className="doc-type">{doc.type}</p>
                        {doc.received_date && (
                          <p className="doc-received">Received: {doc.received_date}</p>
                        )}
                      </div>
                      <DocStatusBadge status={doc.status} />
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {activeTab === 'milestones' && (
          <div className="milestones-tab">
            <section className="detail-section">
              <h3>Loan Progress</h3>
              <MilestoneTimeline milestones={milestones} />
            </section>
          </div>
        )}

        {activeTab === 'orders' && (
          <div className="orders-tab">
            <section className="detail-section">
              <h3>Third-Party Orders</h3>
              <div className="orders-grid">
                <OrderStatus
                  order={third_party_orders?.appraisal}
                  type="Appraisal"
                  icon="🏠"
                />
                <OrderStatus
                  order={third_party_orders?.title}
                  type="Title"
                  icon="📋"
                />
                <OrderStatus
                  order={third_party_orders?.homeowners_insurance}
                  type="Homeowners Insurance"
                  icon="🛡️"
                />
              </div>
              {third_party_orders?.other && third_party_orders.other.length > 0 && (
                <div className="other-orders">
                  <h4>Other Orders</h4>
                  {third_party_orders.other.map((order, idx) => (
                    <OrderStatus
                      key={idx}
                      order={order}
                      type={order.type}
                      icon="📦"
                    />
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {activeTab === 'messages' && (
          <div className="messages-tab">
            <section className="detail-section">
              <h3>Conversation History</h3>
              <ConversationLog conversations={conversation_log} />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
