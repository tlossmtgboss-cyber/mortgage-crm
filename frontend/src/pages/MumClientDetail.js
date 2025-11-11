import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { mumAPI, activitiesAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSModal from '../components/SMSModal';
import TeamsModal from '../components/TeamsModal';
import './LeadDetail.css';

function MumClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(true);
  const [formData, setFormData] = useState({});
  const [activeTab, setActiveTab] = useState('personal');
  const [saveTimeout, setSaveTimeout] = useState(null);
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [showTeamsModal, setShowTeamsModal] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const [activities, setActivities] = useState([]);

  useEffect(() => {
    loadClientData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadClientData = async () => {
    try {
      setLoading(true);
      const [clientData, activitiesData] = await Promise.all([
        mumAPI.getById(id),
        activitiesAPI.getAll({ mum_client_id: id })
      ]);
      setClient(clientData);
      setFormData(clientData);
      setActivities(activitiesData || []);
    } catch (error) {
      console.error('Failed to load MUM client data:', error);
      alert('Failed to load client details');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await mumAPI.update(id, formData);
      setClient(formData);
    } catch (error) {
      console.error('Failed to save client:', error);
      alert('Failed to save changes');
    }
  };

  const handleFieldChange = (field, value) => {
    const updatedData = { ...formData, [field]: value };
    setFormData(updatedData);

    // Auto-save after 1 second of no typing
    if (saveTimeout) clearTimeout(saveTimeout);
    setSaveTimeout(setTimeout(async () => {
      try {
        await mumAPI.update(id, { [field]: value });
        console.log(`Field ${field} saved successfully`);
      } catch (error) {
        console.error('Auto-save failed:', error);
      }
    }, 1000));
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!noteText.trim()) return;

    try {
      setNoteLoading(true);
      await activitiesAPI.create({
        type: 'Note',
        content: noteText,
        mum_client_id: parseInt(id)
      });
      setNoteText('');
      loadClientData();
    } catch (error) {
      console.error('Failed to add note:', error);
      alert('Failed to add note');
    } finally {
      setNoteLoading(false);
    }
  };

  const handleAction = async (action) => {
    switch(action) {
      case 'call':
        window.open(`tel:${client.phone}`, '_self');
        break;
      case 'sms':
        setShowSMSModal(true);
        break;
      case 'email':
        window.open(`mailto:${client.email}`, '_blank');
        break;
      case 'teams':
        setShowTeamsModal(true);
        break;
      default:
        break;
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const getDaysSinceFunding = (closeDate) => {
    if (!closeDate) return 0;
    const closed = new Date(closeDate);
    const today = new Date();
    const diff = Math.floor((today - closed) / (1000 * 60 * 60 * 24));
    return diff;
  };

  if (loading) {
    return <div className="loading">Loading client details...</div>;
  }

  if (!client) {
    return <div className="error">Client not found</div>;
  }

  const daysSinceFunding = getDaysSinceFunding(client.original_close_date || client.close_date);

  return (
    <div className="lead-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/portfolio')}>
          ← Back to Portfolio
        </button>
        <div className="header-title">
          <h1>{client.name}</h1>
          {client.refinance_opportunity && (
            <span className="opportunity-badge">Refinance Opportunity</span>
          )}
        </div>
      </div>

      {/* Loan Information Toolbar */}
      <div className="loan-toolbar">
        <div className="toolbar-header">
          <h3>Portfolio Client Details</h3>
        </div>
        <div className="loan-fields-grid">
          <div className="loan-field">
            <label>Days Since Funding</label>
            <div className="stat-display">{daysSinceFunding} days</div>
          </div>

          <div className="loan-field">
            <label>Original Rate</label>
            <input
              type="number"
              step="0.001"
              value={formData.original_rate || ''}
              onChange={(e) => handleFieldChange('original_rate', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Current Rate</label>
            <input
              type="number"
              step="0.001"
              value={formData.current_rate || ''}
              onChange={(e) => handleFieldChange('current_rate', parseFloat(e.target.value))}
              placeholder="%"
            />
          </div>

          <div className="loan-field">
            <label>Loan Balance</label>
            <input
              type="number"
              value={formData.loan_balance || ''}
              onChange={(e) => handleFieldChange('loan_balance', parseFloat(e.target.value))}
              placeholder="$"
            />
          </div>

          <div className="loan-field">
            <label>Loan Number</label>
            <input
              type="text"
              value={formData.loan_number || ''}
              onChange={(e) => handleFieldChange('loan_number', e.target.value)}
            />
          </div>

          <div className="loan-field">
            <label>Original Close Date</label>
            <input
              type="date"
              value={formData.original_close_date ? formData.original_close_date.split('T')[0] : ''}
              onChange={(e) => handleFieldChange('original_close_date', e.target.value)}
            />
          </div>

          {client.estimated_savings && (
            <>
              <div className="loan-field">
                <label>Est. Monthly Savings</label>
                <input
                  type="number"
                  value={formData.estimated_savings || ''}
                  onChange={(e) => handleFieldChange('estimated_savings', parseFloat(e.target.value))}
                  placeholder="$"
                />
              </div>
            </>
          )}

          <div className="loan-field">
            <label>Refinance Opportunity</label>
            <select
              value={formData.refinance_opportunity ? 'yes' : 'no'}
              onChange={(e) => handleFieldChange('refinance_opportunity', e.target.value === 'yes')}
            >
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
        <button
          className={`tab-btn ${activeTab === 'personal' ? 'active' : ''}`}
          onClick={() => setActiveTab('personal')}
        >
          Personal
        </button>
        <button
          className={`tab-btn ${activeTab === 'loan' ? 'active' : ''}`}
          onClick={() => setActiveTab('loan')}
        >
          Loan Details
        </button>
        <button
          className={`tab-btn ${activeTab === 'touchpoints' ? 'active' : ''}`}
          onClick={() => setActiveTab('touchpoints')}
        >
          Touchpoints
        </button>
        <button
          className={`tab-btn ${activeTab === 'opportunities' ? 'active' : ''}`}
          onClick={() => setActiveTab('opportunities')}
        >
          Opportunities
        </button>
        <button
          className={`tab-btn ${activeTab === 'conversation' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversation')}
        >
          Conversation Log
        </button>
      </div>

      <div className="detail-content">
        {/* Left Column - Client Information */}
        <div className="left-column">
          {/* Personal Information Tab */}
          {activeTab === 'personal' && (
            <div className="info-section">
              <h2>Personal Information</h2>
              <div className="info-grid compact">
                <div className="info-field">
                  <label>Client Name</label>
                  <input
                    type="text"
                    value={formData.name || ''}
                    onChange={(e) => handleFieldChange('name', e.target.value)}
                  />
                </div>
                <div className="info-field">
                  <label>Email</label>
                  <input
                    type="email"
                    value={formData.email || ''}
                    onChange={(e) => handleFieldChange('email', e.target.value)}
                  />
                </div>
                <div className="info-field">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={formData.phone || ''}
                    onChange={(e) => handleFieldChange('phone', e.target.value)}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Loan Details Tab */}
          {activeTab === 'loan' && (
            <div className="info-section">
              <h2>Loan Information</h2>
              <div className="info-grid compact">
                <div className="info-field">
                  <label>Original Close Date</label>
                  <input
                    type="date"
                    value={formData.original_close_date ? formData.original_close_date.split('T')[0] : ''}
                    onChange={(e) => handleFieldChange('original_close_date', e.target.value)}
                  />
                </div>
                <div className="info-field">
                  <label>Original Interest Rate (%)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={formData.original_rate || ''}
                    onChange={(e) => handleFieldChange('original_rate', parseFloat(e.target.value))}
                  />
                </div>
                <div className="info-field">
                  <label>Current Rate (%)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={formData.current_rate || ''}
                    onChange={(e) => handleFieldChange('current_rate', parseFloat(e.target.value))}
                  />
                </div>
                <div className="info-field">
                  <label>Loan Balance ($)</label>
                  <input
                    type="number"
                    value={formData.loan_balance || ''}
                    onChange={(e) => handleFieldChange('loan_balance', parseFloat(e.target.value))}
                  />
                </div>
                <div className="info-field" style={{gridColumn: 'span 2'}}>
                  <label>Notes</label>
                  <textarea
                    rows="4"
                    value={formData.notes || ''}
                    onChange={(e) => handleFieldChange('notes', e.target.value)}
                    placeholder="Add notes about this client..."
                  />
                </div>
              </div>
            </div>
          )}

          {/* Touchpoints Tab */}
          {activeTab === 'touchpoints' && (
            <div className="info-section">
              <h2>Client Touchpoints</h2>
              <div className="info-grid compact">
                <div className="info-field">
                  <label>Last Contact</label>
                  <input
                    type="date"
                    value={formData.last_contact ? formData.last_contact.split('T')[0] : ''}
                    onChange={(e) => handleFieldChange('last_contact', e.target.value)}
                  />
                </div>
                <div className="info-field">
                  <label>Next Touchpoint</label>
                  <input
                    type="date"
                    value={formData.next_touchpoint ? formData.next_touchpoint.split('T')[0] : ''}
                    onChange={(e) => handleFieldChange('next_touchpoint', e.target.value)}
                  />
                </div>
                <div className="info-field">
                  <label>Engagement Score</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={formData.engagement_score || 0}
                    onChange={(e) => handleFieldChange('engagement_score', parseInt(e.target.value))}
                  />
                  <small>Score from 0-100 based on client responsiveness</small>
                </div>
                <div className="info-field">
                  <label>Referrals Sent</label>
                  <input
                    type="number"
                    min="0"
                    value={formData.referrals_sent || 0}
                    onChange={(e) => handleFieldChange('referrals_sent', parseInt(e.target.value))}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Opportunities Tab */}
          {activeTab === 'opportunities' && (
            <div className="info-section">
              <h2>Refinance Opportunities</h2>
              <div className="info-grid compact">
                {client.refinance_opportunity ? (
                  <>
                    <div className="opportunity-alert" style={{gridColumn: 'span 2'}}>
                      <h3>Refinance Opportunity Detected</h3>
                      <p>This client may benefit from refinancing based on current market rates.</p>
                    </div>
                    <div className="info-field">
                      <label>Estimated Monthly Savings</label>
                      <input
                        type="number"
                        value={formData.estimated_savings || ''}
                        onChange={(e) => handleFieldChange('estimated_savings', parseFloat(e.target.value))}
                        placeholder="$"
                      />
                    </div>
                    <div className="info-field" style={{gridColumn: 'span 2'}}>
                      <label>Opportunity Notes</label>
                      <textarea
                        rows="4"
                        value={formData.opportunity_notes || ''}
                        onChange={(e) => handleFieldChange('opportunity_notes', e.target.value)}
                        placeholder="Details about the refinance opportunity..."
                      />
                    </div>
                  </>
                ) : (
                  <div className="no-opportunity" style={{gridColumn: 'span 2'}}>
                    <p>No refinance opportunity identified at this time.</p>
                    <p>Monitor market rates and client circumstances for future opportunities.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Conversation Log Tab */}
          {activeTab === 'conversation' && (
            <div className="info-section">
              <h2>Conversation Log</h2>

              {/* Add Note Form */}
              <form onSubmit={handleAddNote} className="add-note-form">
                <textarea
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="Add a note to the conversation log..."
                  rows="3"
                  disabled={noteLoading}
                />
                <button type="submit" disabled={noteLoading || !noteText.trim()}>
                  {noteLoading ? 'Adding...' : 'Add Note'}
                </button>
              </form>

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
                      <div className="activity-description">{activity.content || activity.description}</div>
                    </div>
                  ))
                ) : (
                  <div className="empty-state">No activities yet</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column - Actions */}
        <div className="right-column">
          {/* Action Buttons */}
          <div className="actions-card">
            <h3>Quick Actions</h3>
            <div className="action-buttons">
              <button
                className="action-btn call"
                onClick={() => handleAction('call')}
                disabled={!client.phone}
                title="Click to call"
              >
                <span className="icon">📞</span>
                <span>Call</span>
              </button>
              <button
                className="action-btn sms"
                onClick={() => handleAction('sms')}
                disabled={!client.phone}
                title="Send SMS"
              >
                <span className="icon">💬</span>
                <span>SMS Text</span>
              </button>
              <button
                className="action-btn email"
                onClick={() => handleAction('email')}
                disabled={!client.email}
              >
                <span className="icon">✉️</span>
                <span>Send Email</span>
              </button>
              <button
                className="action-btn teams"
                onClick={() => handleAction('teams')}
                title="Create Microsoft Teams meeting"
              >
                <span className="icon">👥</span>
                <span>Teams Meeting</span>
              </button>
            </div>
          </div>

          {/* Stats Card */}
          <div className="stats-card">
            <h3>Client Stats</h3>
            <div className="stats-list">
              <div className="stat-row">
                <span className="stat-label">Days Since Funding</span>
                <span className="stat-value">{daysSinceFunding}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Original Rate</span>
                <span className="stat-value">{formData.original_rate || 'N/A'}%</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Current Rate</span>
                <span className="stat-value">{formData.current_rate || 'N/A'}%</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Loan Balance</span>
                <span className="stat-value">{formatCurrency(formData.loan_balance || 0)}</span>
              </div>
              {formData.estimated_savings && (
                <div className="stat-row highlight">
                  <span className="stat-label">Est. Savings</span>
                  <span className="stat-value">{formatCurrency(formData.estimated_savings)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* SMS Modal */}
      {client && (
        <SMSModal
          isOpen={showSMSModal}
          onClose={() => setShowSMSModal(false)}
          lead={client}
        />
      )}

      {/* Teams Modal */}
      {client && (
        <TeamsModal
          isOpen={showTeamsModal}
          onClose={() => setShowTeamsModal(false)}
          lead={client}
        />
      )}
    </div>
  );
}

export default MumClientDetail;
