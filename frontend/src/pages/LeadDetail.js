import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, aiAPI } from '../services/api';
import './LeadDetail.css';

function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [chatMessage, setChatMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState({});
  const [emails, setEmails] = useState([]);

  useEffect(() => {
    loadLeadData();
    loadEmails();
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
      setFormData(leadData);
      setActivities(activitiesData || []);
    } catch (error) {
      console.error('Failed to load lead data:', error);
      alert('Failed to load lead details');
    } finally {
      setLoading(false);
    }
  };

  const loadEmails = async () => {
    try {
      const emailActivities = await activitiesAPI.getAll({
        lead_id: id,
        type: 'email'
      });
      setEmails(emailActivities || []);
    } catch (error) {
      console.error('Failed to load emails:', error);
    }
  };

  const handleSave = async () => {
    try {
      await leadsAPI.update(id, formData);
      setLead(formData);
      setEditing(false);
      alert('Lead updated successfully!');
    } catch (error) {
      console.error('Failed to update lead:', error);
      alert('Failed to update lead');
    }
  };

  const handleCancel = () => {
    setFormData(lead);
    setEditing(false);
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim()) return;

    try {
      setChatLoading(true);
      const response = await aiAPI.chat(chatMessage, { lead_id: id });

      await activitiesAPI.create({
        type: 'ai_chat',
        description: `User: ${chatMessage}\nAI: ${response.message}`,
        lead_id: id
      });

      setChatMessage('');
      loadLeadData();
    } catch (error) {
      console.error('Failed to send AI message:', error);
      alert('Failed to send message');
    } finally {
      setChatLoading(false);
    }
  };

  const handleAction = async (action) => {
    switch(action) {
      case 'sms':
        window.open(`sms:${lead.phone}`, '_blank');
        break;
      case 'email':
        window.open(`mailto:${lead.email}`, '_blank');
        break;
      case 'task':
        navigate('/tasks');
        break;
      case 'calendar':
        navigate('/calendar');
        break;
      default:
        break;
    }
  };

  if (loading) {
    return (
      <div className="lead-detail-page">
        <div className="loading">Loading lead details...</div>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="lead-detail-page">
        <div className="error">Lead not found</div>
      </div>
    );
  }

  return (
    <div className="lead-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/leads')}>
          ← Back to Leads
        </button>
        <div className="header-actions">
          {editing ? (
            <>
              <button className="btn-save" onClick={handleSave}>Save</button>
              <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
            </>
          ) : (
            <button className="btn-edit-header" onClick={() => setEditing(true)}>
              ✏️ Edit
            </button>
          )}
        </div>
      </div>

      <div className="detail-content">
        {/* Left Column - Lead Information */}
        <div className="left-column">
          {/* Personal Information */}
          <div className="info-section">
            <h2>Personal Information</h2>
            <div className="info-grid compact">
              <div className="info-field">
                <label>Name</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.name || ''}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.name}</div>
                )}
              </div>
              <div className="info-field">
                <label>Email</label>
                {editing ? (
                  <input
                    type="email"
                    value={formData.email || ''}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.email || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Phone</label>
                {editing ? (
                  <input
                    type="tel"
                    value={formData.phone || ''}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                  />
                ) : (
                  <a href={`tel:${lead.phone}`} className="value phone-link">
                    {lead.phone || 'N/A'}
                  </a>
                )}
              </div>
              <div className="info-field">
                <label>Loan Number</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.loan_number || ''}
                    onChange={(e) => setFormData({...formData, loan_number: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.loan_number || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Employment Status</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.employment_status || ''}
                    onChange={(e) => setFormData({...formData, employment_status: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.employment_status || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Annual Income</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.annual_income || ''}
                    onChange={(e) => setFormData({...formData, annual_income: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.annual_income ? `$${lead.annual_income.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Loan Information */}
          <div className="info-section">
            <h2>Loan Information</h2>
            <div className="info-grid compact">
              <div className="info-field">
                <label>Property Address</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.address || ''}
                    onChange={(e) => setFormData({...formData, address: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.address || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>City</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.city || ''}
                    onChange={(e) => setFormData({...formData, city: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.city || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>State</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.state || ''}
                    onChange={(e) => setFormData({...formData, state: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.state || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Zip Code</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.zip_code || ''}
                    onChange={(e) => setFormData({...formData, zip_code: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.zip_code || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Property Type</label>
                {editing ? (
                  <input
                    type="text"
                    value={formData.property_type || ''}
                    onChange={(e) => setFormData({...formData, property_type: e.target.value})}
                  />
                ) : (
                  <div className="value">{lead.property_type || 'N/A'}</div>
                )}
              </div>
              <div className="info-field">
                <label>Property Value</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.property_value || ''}
                    onChange={(e) => setFormData({...formData, property_value: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.property_value ? `$${lead.property_value.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Down Payment</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.down_payment || ''}
                    onChange={(e) => setFormData({...formData, down_payment: parseFloat(e.target.value)})}
                  />
                ) : (
                  <div className="value">
                    {lead.down_payment ? `$${lead.down_payment.toLocaleString()}` : 'N/A'}
                  </div>
                )}
              </div>
              <div className="info-field">
                <label>Credit Score</label>
                {editing ? (
                  <input
                    type="number"
                    value={formData.credit_score || ''}
                    onChange={(e) => setFormData({...formData, credit_score: parseInt(e.target.value)})}
                  />
                ) : (
                  <div className="value">{lead.credit_score || 'N/A'}</div>
                )}
              </div>
            </div>
          </div>

          {/* Conversation Log */}
          <div className="info-section">
            <h2>Conversation Log</h2>
            <div className="conversation-log">
              {activities.length > 0 ? (
                activities.map((activity) => (
                  <div key={activity.id} className="activity-item">
                    <div className="activity-header">
                      <span className={`activity-type ${activity.type}`}>
                        {activity.type}
                      </span>
                      <span className="activity-date">
                        {new Date(activity.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="activity-description">{activity.description}</div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No activities yet</div>
              )}
            </div>
          </div>

          {/* AI Chat Assistant */}
          <div className="info-section">
            <h2>AI Chat Assistant</h2>
            <form onSubmit={handleSendMessage} className="ai-chat-form">
              <textarea
                value={chatMessage}
                onChange={(e) => setChatMessage(e.target.value)}
                placeholder="Ask the AI assistant about this lead..."
                rows="3"
                disabled={chatLoading}
              />
              <button type="submit" disabled={chatLoading || !chatMessage.trim()}>
                {chatLoading ? 'Sending...' : 'Send Message'}
              </button>
            </form>
          </div>
        </div>

        {/* Right Column - Actions & Email History */}
        <div className="right-column">
          {/* Action Buttons */}
          <div className="actions-card">
            <h3>Quick Actions</h3>
            <div className="action-buttons">
              <button
                className="action-btn sms"
                onClick={() => handleAction('sms')}
                disabled={!lead.phone}
              >
                <span className="icon">💬</span>
                <span>SMS Text</span>
              </button>
              <button
                className="action-btn task"
                onClick={() => handleAction('task')}
              >
                <span className="icon">✓</span>
                <span>Create Task</span>
              </button>
              <button
                className="action-btn email"
                onClick={() => handleAction('email')}
                disabled={!lead.email}
              >
                <span className="icon">✉️</span>
                <span>Send Email</span>
              </button>
              <button
                className="action-btn calendar"
                onClick={() => handleAction('calendar')}
              >
                <span className="icon">📅</span>
                <span>Set Appointment</span>
              </button>
            </div>
          </div>

          {/* Email History */}
          <div className="email-history-card">
            <h3>Email History</h3>
            <div className="email-list">
              {emails.length > 0 ? (
                emails.map((email) => (
                  <div key={email.id} className="email-item">
                    <div className="email-header">
                      <span className="email-subject">
                        {email.description.split('\n')[0]}
                      </span>
                      <span className="email-date">
                        {new Date(email.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="email-preview">
                      {email.description.substring(0, 100)}...
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No emails yet</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LeadDetail;
