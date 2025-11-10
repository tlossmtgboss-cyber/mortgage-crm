import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { mumAPI } from '../services/api';
import './LeadDetail.css';

function MumClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(true);
  const [formData, setFormData] = useState({});
  const [activeTab, setActiveTab] = useState('overview');
  const [saveTimeout, setSaveTimeout] = useState(null);

  useEffect(() => {
    loadClientData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadClientData = async () => {
    try {
      setLoading(true);
      const clientData = await mumAPI.getById(id);
      setClient(clientData);
      setFormData(clientData);
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

  const handleChange = (field, value) => {
    const updatedData = { ...formData, [field]: value };
    setFormData(updatedData);

    // Auto-save after 1 second of no typing
    if (saveTimeout) clearTimeout(saveTimeout);
    setSaveTimeout(setTimeout(() => handleSave(), 1000));
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
    <div className="lead-detail">
      <div className="detail-header">
        <button className="back-btn" onClick={() => navigate('/portfolio')}>
          ← Back to Portfolio
        </button>
        <h1>{client.name}</h1>
        {client.refinance_opportunity && (
          <span className="opportunity-badge">Refinance Opportunity</span>
        )}
      </div>

      <div className="detail-content">
        {/* Stats Cards */}
        <div className="stats-overview">
          <div className="stat-card">
            <div className="stat-label">Days Since Funding</div>
            <div className="stat-value">{daysSinceFunding}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Original Rate</div>
            <div className="stat-value">{client.original_rate}%</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Current Rate</div>
            <div className="stat-value">{client.current_rate || 'N/A'}%</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Loan Balance</div>
            <div className="stat-value">{formatCurrency(client.loan_balance || 0)}</div>
          </div>
          {client.estimated_savings && (
            <div className="stat-card highlight">
              <div className="stat-label">Est. Savings</div>
              <div className="stat-value">{formatCurrency(client.estimated_savings)}</div>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`tab ${activeTab === 'touchpoints' ? 'active' : ''}`}
            onClick={() => setActiveTab('touchpoints')}
          >
            Touchpoints
          </button>
          <button
            className={`tab ${activeTab === 'opportunities' ? 'active' : ''}`}
            onClick={() => setActiveTab('opportunities')}
          >
            Opportunities
          </button>
        </div>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="tab-content">
            <h2>Client Information</h2>
            <div className="form-section">
              <div className="form-group">
                <label>Client Name</label>
                <input
                  type="text"
                  value={formData.name || ''}
                  onChange={(e) => handleChange('name', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input
                  type="email"
                  value={formData.email || ''}
                  onChange={(e) => handleChange('email', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Phone</label>
                <input
                  type="tel"
                  value={formData.phone || ''}
                  onChange={(e) => handleChange('phone', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Loan Number</label>
                <input
                  type="text"
                  value={formData.loan_number || ''}
                  onChange={(e) => handleChange('loan_number', e.target.value)}
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Original Close Date</label>
                  <input
                    type="date"
                    value={formData.original_close_date ? formData.original_close_date.split('T')[0] : ''}
                    onChange={(e) => handleChange('original_close_date', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Original Interest Rate (%)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={formData.original_rate || ''}
                    onChange={(e) => handleChange('original_rate', parseFloat(e.target.value))}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Current Rate (%)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={formData.current_rate || ''}
                    onChange={(e) => handleChange('current_rate', parseFloat(e.target.value))}
                  />
                </div>
                <div className="form-group">
                  <label>Loan Balance ($)</label>
                  <input
                    type="number"
                    value={formData.loan_balance || ''}
                    onChange={(e) => handleChange('loan_balance', parseFloat(e.target.value))}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Refinance Opportunity</label>
                <select
                  value={formData.refinance_opportunity ? 'yes' : 'no'}
                  onChange={(e) => handleChange('refinance_opportunity', e.target.value === 'yes')}
                >
                  <option value="no">No</option>
                  <option value="yes">Yes</option>
                </select>
              </div>
              <div className="form-group">
                <label>Notes</label>
                <textarea
                  rows="4"
                  value={formData.notes || ''}
                  onChange={(e) => handleChange('notes', e.target.value)}
                  placeholder="Add notes about this client..."
                />
              </div>
            </div>
          </div>
        )}

        {/* Touchpoints Tab */}
        {activeTab === 'touchpoints' && (
          <div className="tab-content">
            <h2>Client Touchpoints</h2>
            <div className="form-section">
              <div className="form-group">
                <label>Last Contact</label>
                <input
                  type="date"
                  value={formData.last_contact ? formData.last_contact.split('T')[0] : ''}
                  onChange={(e) => handleChange('last_contact', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Next Touchpoint</label>
                <input
                  type="date"
                  value={formData.next_touchpoint ? formData.next_touchpoint.split('T')[0] : ''}
                  onChange={(e) => handleChange('next_touchpoint', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Engagement Score</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={formData.engagement_score || 0}
                  onChange={(e) => handleChange('engagement_score', parseInt(e.target.value))}
                />
                <small>Score from 0-100 based on client responsiveness</small>
              </div>
              <div className="form-group">
                <label>Referrals Sent</label>
                <input
                  type="number"
                  min="0"
                  value={formData.referrals_sent || 0}
                  onChange={(e) => handleChange('referrals_sent', parseInt(e.target.value))}
                />
              </div>
            </div>
          </div>
        )}

        {/* Opportunities Tab */}
        {activeTab === 'opportunities' && (
          <div className="tab-content">
            <h2>Refinance Opportunities</h2>
            <div className="form-section">
              {client.refinance_opportunity ? (
                <>
                  <div className="opportunity-alert">
                    <h3>Refinance Opportunity Detected</h3>
                    <p>This client may benefit from refinancing based on current market rates.</p>
                  </div>
                  <div className="form-group">
                    <label>Estimated Monthly Savings</label>
                    <input
                      type="number"
                      value={formData.estimated_savings || ''}
                      onChange={(e) => handleChange('estimated_savings', parseFloat(e.target.value))}
                      placeholder="$"
                    />
                  </div>
                  <div className="form-group">
                    <label>Opportunity Notes</label>
                    <textarea
                      rows="4"
                      value={formData.opportunity_notes || ''}
                      onChange={(e) => handleChange('opportunity_notes', e.target.value)}
                      placeholder="Details about the refinance opportunity..."
                    />
                  </div>
                </>
              ) : (
                <div className="no-opportunity">
                  <p>No refinance opportunity identified at this time.</p>
                  <p>Monitor market rates and client circumstances for future opportunities.</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default MumClientDetail;
