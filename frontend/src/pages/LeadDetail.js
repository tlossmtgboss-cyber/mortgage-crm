import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, activitiesAPI, aiAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
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
  const [activeTab, setActiveTab] = useState('personal');

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

      {/* Loan Information Toolbar */}
      <div className="loan-toolbar">
        <div className="toolbar-header">
          <h3>Loan Details</h3>
        </div>
        <div className="loan-fields-grid">
          <div className="loan-field">
            <label>Loan Amount</label>
            {editing ? (
              <input
                type="number"
                value={formData.loan_amount || ''}
                onChange={(e) => setFormData({...formData, loan_amount: e.target.value})}
                placeholder="$"
              />
            ) : (
              <div className="value">
                {formData.loan_amount ? `$${parseFloat(formData.loan_amount).toLocaleString()}` : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>Interest Rate</label>
            {editing ? (
              <input
                type="number"
                step="0.001"
                value={formData.interest_rate || ''}
                onChange={(e) => setFormData({...formData, interest_rate: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.interest_rate ? `${formData.interest_rate}%` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Loan Term</label>
            {editing ? (
              <input
                type="number"
                value={formData.loan_term || ''}
                onChange={(e) => setFormData({...formData, loan_term: e.target.value})}
                placeholder="Years"
              />
            ) : (
              <div className="value">{formData.loan_term ? `${formData.loan_term} years` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Loan Type</label>
            {editing ? (
              <select
                value={formData.loan_type || ''}
                onChange={(e) => setFormData({...formData, loan_type: e.target.value})}
              >
                <option value="">Select...</option>
                <option value="Conventional">Conventional</option>
                <option value="FHA">FHA</option>
                <option value="VA">VA</option>
                <option value="USDA">USDA</option>
                <option value="Jumbo">Jumbo</option>
                <option value="HELOC">HELOC</option>
              </select>
            ) : (
              <div className="value">{formData.loan_type || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Lock Date</label>
            {editing ? (
              <input
                type="date"
                value={formData.lock_date || ''}
                onChange={(e) => setFormData({...formData, lock_date: e.target.value})}
              />
            ) : (
              <div className="value">
                {formData.lock_date ? new Date(formData.lock_date).toLocaleDateString() : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>Lock Expiration</label>
            {editing ? (
              <input
                type="date"
                value={formData.lock_expiration || ''}
                onChange={(e) => setFormData({...formData, lock_expiration: e.target.value})}
              />
            ) : (
              <div className="value">
                {formData.lock_expiration ? new Date(formData.lock_expiration).toLocaleDateString() : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>APR</label>
            {editing ? (
              <input
                type="number"
                step="0.001"
                value={formData.apr || ''}
                onChange={(e) => setFormData({...formData, apr: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.apr ? `${formData.apr}%` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Points</label>
            {editing ? (
              <input
                type="number"
                step="0.125"
                value={formData.points || ''}
                onChange={(e) => setFormData({...formData, points: e.target.value})}
              />
            ) : (
              <div className="value">{formData.points || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Lender</label>
            {editing ? (
              <input
                type="text"
                value={formData.lender || ''}
                onChange={(e) => setFormData({...formData, lender: e.target.value})}
              />
            ) : (
              <div className="value">{formData.lender || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Loan Officer</label>
            {editing ? (
              <input
                type="text"
                value={formData.loan_officer || ''}
                onChange={(e) => setFormData({...formData, loan_officer: e.target.value})}
              />
            ) : (
              <div className="value">{formData.loan_officer || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Processor</label>
            {editing ? (
              <input
                type="text"
                value={formData.processor || ''}
                onChange={(e) => setFormData({...formData, processor: e.target.value})}
              />
            ) : (
              <div className="value">{formData.processor || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Underwriter</label>
            {editing ? (
              <input
                type="text"
                value={formData.underwriter || ''}
                onChange={(e) => setFormData({...formData, underwriter: e.target.value})}
              />
            ) : (
              <div className="value">{formData.underwriter || 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>Closing Date</label>
            {editing ? (
              <input
                type="date"
                value={formData.closing_date || ''}
                onChange={(e) => setFormData({...formData, closing_date: e.target.value})}
              />
            ) : (
              <div className="value">
                {formData.closing_date ? new Date(formData.closing_date).toLocaleDateString() : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>Appraisal Value</label>
            {editing ? (
              <input
                type="number"
                value={formData.appraisal_value || ''}
                onChange={(e) => setFormData({...formData, appraisal_value: e.target.value})}
                placeholder="$"
              />
            ) : (
              <div className="value">
                {formData.appraisal_value ? `$${parseFloat(formData.appraisal_value).toLocaleString()}` : 'N/A'}
              </div>
            )}
          </div>

          <div className="loan-field">
            <label>LTV %</label>
            {editing ? (
              <input
                type="number"
                step="0.01"
                value={formData.ltv || ''}
                onChange={(e) => setFormData({...formData, ltv: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.ltv ? `${formData.ltv}%` : 'N/A'}</div>
            )}
          </div>

          <div className="loan-field">
            <label>DTI %</label>
            {editing ? (
              <input
                type="number"
                step="0.01"
                value={formData.dti || ''}
                onChange={(e) => setFormData({...formData, dti: e.target.value})}
                placeholder="%"
              />
            ) : (
              <div className="value">{formData.dti ? `${formData.dti}%` : 'N/A'}</div>
            )}
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
        <button
          className={`tab-btn ${activeTab === 'personal' ? 'active' : ''}`}
          onClick={() => setActiveTab('personal')}
        >
          Personal Information
        </button>
        <button
          className={`tab-btn ${activeTab === 'loan' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan')}
        >
          Loan Information
        </button>
        <button
          className={`tab-btn ${activeTab === 'conversation' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversation')}
        >
          Conversation Log
        </button>
        <button
          className={`tab-btn ${activeTab === 'circle' ? 'active' : ''}`}
          onClick={() => setActiveTab('circle')}
        >
          Circle
        </button>
      </div>

      <div className="detail-content">
        {/* Left Column - Lead Information */}
        <div className="left-column">
          {/* Personal Information Tab */}
          {activeTab === 'personal' && (
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
                  <div className="value">
                    <ClickableEmail email={lead.email} />
                  </div>
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
                  <div className="value">
                    <ClickablePhone phone={lead.phone} />
                  </div>
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
          )}

          {/* Loan Information Tab */}
          {activeTab === 'loan' && (
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
          )}

          {/* Conversation Log Tab */}
          {activeTab === 'conversation' && (
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
          )}

          {/* Circle Tab */}
          {activeTab === 'circle' && (
          <div className="info-section">
            <h2>Circle</h2>
            <div className="circle-content">
              <p className="circle-description">
                View and manage the borrower's circle of influence - family members, co-borrowers,
                real estate agents, and other key contacts involved in the loan process.
              </p>

              <div className="circle-grid">
                <div className="circle-card">
                  <div className="circle-header">
                    <h3>👥 Co-Borrowers</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No co-borrowers added yet</div>
                  </div>
                </div>

                <div className="circle-card">
                  <div className="circle-header">
                    <h3>🏡 Real Estate Agent</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No agent assigned yet</div>
                  </div>
                </div>

                <div className="circle-card">
                  <div className="circle-header">
                    <h3>👨‍👩‍👧 Family Members</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No family members added yet</div>
                  </div>
                </div>

                <div className="circle-card">
                  <div className="circle-header">
                    <h3>🤝 Other Contacts</h3>
                    <button className="btn-add-circle">+ Add</button>
                  </div>
                  <div className="circle-list">
                    <div className="empty-state">No other contacts added yet</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

          {/* AI Chat Assistant - Always Visible */}
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
