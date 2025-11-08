import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, aiAPI, activitiesAPI } from '../services/api';
import './LeadDetail.css';

function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [chatMessage, setChatMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    loadLeadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadLeadData = async () => {
    try {
      setLoading(true);
      const [leadData, activitiesData] = await Promise.all([
        leadsAPI.getById(id),
        activitiesAPI.getAll({ lead_id: id })
      ]);
      setLead(leadData);
      setActivities(activitiesData || []);
    } catch (error) {
      console.error('Failed to load lead:', error);
      alert('Failed to load lead details');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim()) return;

    try {
      setChatLoading(true);
      const response = await aiAPI.chat(chatMessage, { lead_id: id });

      // Add user message and AI response to activities
      const newActivity = {
        type: 'ai_chat',
        description: `User: ${chatMessage}\nAI: ${response.message}`,
        lead_id: id,
        timestamp: new Date().toISOString()
      };

      await activitiesAPI.create(newActivity);
      setChatMessage('');
      loadLeadData(); // Reload to get updated activities
    } catch (error) {
      console.error('Failed to send message:', error);
      alert('Failed to send message');
    } finally {
      setChatLoading(false);
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

  const formatDateTime = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);

    const isToday = date.toDateString() === now.toDateString();
    const isYesterday = date.toDateString() === yesterday.toDateString();

    const timeStr = date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });

    if (isToday) {
      return `Today at ${timeStr}`;
    } else if (isYesterday) {
      return `Yesterday at ${timeStr}`;
    } else {
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      });
    }
  };

  if (loading) {
    return (
      <div className="lead-detail-container">
        <div className="loading">Loading lead details...</div>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="lead-detail-container">
        <div className="error">Lead not found</div>
      </div>
    );
  }

  return (
    <div className="lead-detail-container">
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/leads')}>
          ← Back to Leads
        </button>
        <h1>{lead.name}</h1>
      </div>

      <div className="detail-grid">
        {/* Personal Information */}
        <div className="info-card">
          <h2>Personal Information</h2>
          <div className="info-rows">
            <div className="info-row">
              <span className="label">Full Name</span>
              <span className="value">{lead.name}</span>
            </div>
            <div className="info-row">
              <span className="label">Email</span>
              <span className="value">{lead.email || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="label">Phone</span>
              <span className="value">{lead.phone || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="label">Status</span>
              <span className={`status-badge status-${lead.stage?.toLowerCase().replace(/\s+/g, '-')}`}>
                {lead.stage}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Source</span>
              <span className="value">{lead.source || 'N/A'}</span>
            </div>
            {lead.employment_status && (
              <div className="info-row">
                <span className="label">Employment</span>
                <span className="value">{lead.employment_status}</span>
              </div>
            )}
            {lead.annual_income && (
              <div className="info-row">
                <span className="label">Annual Income</span>
                <span className="value">{formatCurrency(lead.annual_income)}</span>
              </div>
            )}
            {lead.first_time_buyer !== null && lead.first_time_buyer !== undefined && (
              <div className="info-row">
                <span className="label">First-Time Buyer</span>
                <span className="value">{lead.first_time_buyer ? 'Yes' : 'No'}</span>
              </div>
            )}
          </div>
        </div>

        {/* Loan Information */}
        <div className="info-card">
          <h2>Loan Information</h2>
          <div className="info-rows">
            {lead.preapproval_amount && (
              <div className="info-row">
                <span className="label">Loan Amount</span>
                <span className="value">{formatCurrency(lead.preapproval_amount)}</span>
              </div>
            )}
            {lead.address && (
              <div className="info-row">
                <span className="label">Property Address</span>
                <span className="value">
                  {lead.address}
                  {lead.city && lead.state && `, ${lead.city}, ${lead.state} ${lead.zip_code || ''}`}
                </span>
              </div>
            )}
            {lead.loan_type && (
              <div className="info-row">
                <span className="label">Loan Type</span>
                <span className="value">{lead.loan_type}</span>
              </div>
            )}
            {lead.credit_score && (
              <div className="info-row">
                <span className="label">Credit Score</span>
                <span className="value">{lead.credit_score}</span>
              </div>
            )}
            {lead.property_type && (
              <div className="info-row">
                <span className="label">Property Type</span>
                <span className="value">{lead.property_type}</span>
              </div>
            )}
            {lead.property_value && (
              <div className="info-row">
                <span className="label">Property Value</span>
                <span className="value">{formatCurrency(lead.property_value)}</span>
              </div>
            )}
            {lead.down_payment && (
              <div className="info-row">
                <span className="label">Down Payment</span>
                <span className="value">{formatCurrency(lead.down_payment)}</span>
              </div>
            )}
            {lead.monthly_debts && (
              <div className="info-row">
                <span className="label">Monthly Debts</span>
                <span className="value">{formatCurrency(lead.monthly_debts)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Conversation Log */}
      <div className="conversation-section">
        <h2>Conversation Log</h2>
        <div className="conversation-log">
          {activities.length > 0 ? (
            activities.map((activity, index) => (
              <div key={index} className="activity-entry">
                <div className="activity-time">
                  {formatDateTime(activity.created_at || activity.timestamp)} - {activity.type === 'ai_chat' ? 'AI Assistant' : 'System'}
                </div>
                <div className="activity-description">
                  {activity.description || activity.notes}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-activities">
              No activity yet for this lead.
            </div>
          )}
        </div>
      </div>

      {/* AI Chat Assistant */}
      <div className="ai-chat-section">
        <h2>AI Chat Assistant</h2>
        <div className="ai-greeting">
          Hello! I'm your AI assistant for this client. I can answer questions about their loan status, complete tasks, or help you with next steps. What would you like to know?
        </div>
        <form onSubmit={handleSendMessage} className="chat-form">
          <textarea
            value={chatMessage}
            onChange={(e) => setChatMessage(e.target.value)}
            placeholder="Ask about this client or request an action..."
            rows="3"
            disabled={chatLoading}
          />
          <button
            type="submit"
            className="btn-send-message"
            disabled={chatLoading || !chatMessage.trim()}
          >
            {chatLoading ? 'Sending...' : 'Send Message'}
          </button>
        </form>
      </div>

      {/* Notes Section */}
      {lead.notes && (
        <div className="notes-section">
          <h2>Notes</h2>
          <div className="notes-content">
            {lead.notes}
          </div>
        </div>
      )}
    </div>
  );
}

export default LeadDetail;
