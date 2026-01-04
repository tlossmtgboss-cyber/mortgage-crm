import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getDashboardStats,
  getPipelineMetrics,
  getPartnerCandidates,
  createPartnerCandidate,
  updatePartnerStatus,
  getStatusColor,
  getStatusLabel,
  getPartnerTypeLabel,
  formatPhoneNumber,
  PARTNER_TYPES,
  PARTNER_STATUSES,
  PARTNER_SOURCES
} from '../../services/partnerRecruitingApi';
import './PartnerRecruiting.css';

const PartnerRecruitingDashboard = () => {
  const navigate = useNavigate();

  // State
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [partners, setPartners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [showAddPartner, setShowAddPartner] = useState(false);
  const [selectedPartner, setSelectedPartner] = useState(null);

  // New partner form
  const [newPartner, setNewPartner] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    partner_type: 'realtor',
    company_name: '',
    license_number: '',
    license_state: '',
    source: 'referral',
    city: '',
    state: '',
    notes: ''
  });

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsData, metricsData] = await Promise.all([
        getDashboardStats().catch(() => null),
        getPipelineMetrics(90).catch(() => null)
      ]);

      setStats(statsData);
      setMetrics(metricsData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPartners = useCallback(async () => {
    try {
      const data = await getPartnerCandidates({
        status: statusFilter,
        partner_type: typeFilter,
        search: searchQuery,
        limit: 100
      });
      setPartners(data.partners || []);
    } catch (err) {
      console.error('Failed to load partners:', err);
    }
  }, [statusFilter, typeFilter, searchQuery]);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  useEffect(() => {
    if (activeTab === 'partners') {
      loadPartners();
    }
  }, [activeTab, loadPartners]);

  const handleStatusChange = async (partnerId, newStatus) => {
    try {
      await updatePartnerStatus(partnerId, newStatus);
      await loadPartners();
      await loadDashboardData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddPartner = async (e) => {
    e.preventDefault();
    try {
      await createPartnerCandidate(newPartner);
      setShowAddPartner(false);
      setNewPartner({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        partner_type: 'realtor',
        company_name: '',
        license_number: '',
        license_state: '',
        source: 'referral',
        city: '',
        state: '',
        notes: ''
      });
      await loadPartners();
      await loadDashboardData();
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading && !stats) {
    return (
      <div className="pr-loading">
        <div className="pr-spinner"></div>
        <p>Loading Partner Recruiting...</p>
      </div>
    );
  }

  return (
    <div className="pr-container">
      {/* Header */}
      <div className="pr-header">
        <div className="pr-header-left">
          <h1>Partner Recruiting</h1>
          <p>Build your referral partner network</p>
        </div>
        <div className="pr-header-actions">
          <button
            className="pr-btn pr-btn-primary"
            onClick={() => setShowAddPartner(true)}
          >
            + Add Partner
          </button>
        </div>
      </div>

      {error && (
        <div className="pr-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Tabs */}
      <div className="pr-tabs">
        <button
          className={`pr-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`pr-tab ${activeTab === 'partners' ? 'active' : ''}`}
          onClick={() => setActiveTab('partners')}
        >
          Partners
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <>
          {/* Stats Cards */}
          {stats && (
            <div className="pr-stats-grid">
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter(''); setActiveTab('partners'); }}
                title="View all active partners"
              >
                <div className="pr-stat-value">{stats.total_active || 0}</div>
                <div className="pr-stat-label">Active Partners</div>
              </div>
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter('new'); setActiveTab('partners'); }}
                title="View new partners"
              >
                <div className="pr-stat-value" style={{ color: '#3b82f6' }}>
                  {stats.new_this_week || 0}
                </div>
                <div className="pr-stat-label">New This Week</div>
              </div>
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter('meeting_scheduled'); setActiveTab('partners'); }}
                title="View scheduled meetings"
              >
                <div className="pr-stat-value" style={{ color: '#f59e0b' }}>
                  {stats.meetings_scheduled || 0}
                </div>
                <div className="pr-stat-label">Meetings Scheduled</div>
              </div>
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter('proposal_sent'); setActiveTab('partners'); }}
                title="View pending proposals"
              >
                <div className="pr-stat-value" style={{ color: '#22c55e' }}>
                  {stats.proposals_pending || 0}
                </div>
                <div className="pr-stat-label">Proposals Pending</div>
              </div>
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter('onboarded'); setActiveTab('partners'); }}
                title="View onboarded partners"
              >
                <div className="pr-stat-value" style={{ color: '#10b981' }}>
                  {stats.onboarded || 0}
                </div>
                <div className="pr-stat-label">Onboarded</div>
              </div>
              <div className="pr-card pr-stat-card">
                <div className="pr-stat-value" style={{ color: '#8b5cf6' }}>
                  {stats.total_referrals || 0}
                </div>
                <div className="pr-stat-label">Total Referrals</div>
              </div>
            </div>
          )}

          {/* Pipeline Metrics */}
          {metrics && (
            <div className="pr-section">
              <h2>Pipeline Performance</h2>
              <div className="pr-metrics-grid">
                <div className="pr-card pr-metric-card">
                  <div className="pr-metric-header">
                    <span className="pr-metric-label">Avg Days to Onboard</span>
                    <span className="pr-metric-value">{metrics.avg_days_to_onboard || 0} days</span>
                  </div>
                </div>
                <div className="pr-card pr-metric-card">
                  <div className="pr-metric-header">
                    <span className="pr-metric-label">Contact to Meeting Rate</span>
                    <span className="pr-metric-value">{metrics.contact_to_meeting_rate || 0}%</span>
                  </div>
                  <div className="pr-progress-container">
                    <div
                      className="pr-progress-bar"
                      style={{
                        width: `${metrics.contact_to_meeting_rate || 0}%`,
                        backgroundColor: '#8b5cf6'
                      }}
                    />
                  </div>
                </div>
                <div className="pr-card pr-metric-card">
                  <div className="pr-metric-header">
                    <span className="pr-metric-label">Meeting to Proposal Rate</span>
                    <span className="pr-metric-value">{metrics.meeting_to_proposal_rate || 0}%</span>
                  </div>
                  <div className="pr-progress-container">
                    <div
                      className="pr-progress-bar"
                      style={{
                        width: `${metrics.meeting_to_proposal_rate || 0}%`,
                        backgroundColor: '#f59e0b'
                      }}
                    />
                  </div>
                </div>
                <div className="pr-card pr-metric-card">
                  <div className="pr-metric-header">
                    <span className="pr-metric-label">Overall Conversion</span>
                    <span className="pr-metric-value">{metrics.overall_conversion_rate || 0}%</span>
                  </div>
                  <div className="pr-progress-container">
                    <div
                      className="pr-progress-bar"
                      style={{
                        width: `${metrics.overall_conversion_rate || 0}%`,
                        backgroundColor: '#10b981'
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Pipeline by Stage */}
          {stats?.by_status && (
            <div className="pr-section">
              <h2>Pipeline by Stage</h2>
              <div className="pr-pipeline-stages">
                {PARTNER_STATUSES.slice(0, 8).map((status) => (
                  <div
                    key={status.value}
                    className="pr-pipeline-stage pr-clickable"
                    onClick={() => { setStatusFilter(status.value); setActiveTab('partners'); }}
                    title={`View ${status.label} partners`}
                  >
                    <div
                      className="pr-stage-count"
                      style={{ backgroundColor: status.color }}
                    >
                      {stats.by_status[status.value] || 0}
                    </div>
                    <div className="pr-stage-label">{status.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Partner Type Breakdown */}
          {stats?.by_type && (
            <div className="pr-section">
              <h2>By Partner Type</h2>
              <div className="pr-type-grid">
                {PARTNER_TYPES.map((type) => (
                  <div
                    key={type.value}
                    className="pr-card pr-type-card pr-clickable"
                    onClick={() => { setTypeFilter(type.value); setActiveTab('partners'); }}
                  >
                    <div className="pr-type-count">{stats.by_type[type.value] || 0}</div>
                    <div className="pr-type-label">{type.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Activity */}
          {stats?.recent_activity && stats.recent_activity.length > 0 && (
            <div className="pr-section">
              <h2>Recent Activity</h2>
              <div className="pr-activity-list">
                {stats.recent_activity.map((activity, idx) => (
                  <div key={idx} className="pr-card pr-activity-card">
                    <div className="pr-activity-icon" style={{ backgroundColor: getStatusColor(activity.status) }}>
                      {activity.partner_name?.charAt(0) || '?'}
                    </div>
                    <div className="pr-activity-content">
                      <div className="pr-activity-title">{activity.partner_name}</div>
                      <div className="pr-activity-description">{activity.description}</div>
                    </div>
                    <div className="pr-activity-time">
                      {new Date(activity.created_at).toLocaleDateString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Partners Tab */}
      {activeTab === 'partners' && (
        <div className="pr-section">
          <div className="pr-section-header">
            <h2>All Partners</h2>
            <div className="pr-filters">
              <input
                type="text"
                placeholder="Search partners..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pr-input"
              />
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="pr-select"
              >
                <option value="">All Types</option>
                {PARTNER_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="pr-select"
              >
                <option value="">All Statuses</option>
                {PARTNER_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="pr-table-container">
            <table className="pr-table">
              <thead>
                <tr>
                  <th>Partner</th>
                  <th>Type</th>
                  <th>Company</th>
                  <th>Phone</th>
                  <th>Source</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {partners.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="pr-table-empty">
                      No partners found. Click "+ Add Partner" to add one.
                    </td>
                  </tr>
                ) : (
                  partners.map((partner) => (
                    <tr
                      key={partner.id}
                      onClick={() => navigate(`/partner-recruiting/${partner.id}`)}
                      style={{ cursor: 'pointer' }}
                      className="pr-clickable-row"
                    >
                      <td>
                        <div className="pr-user-cell">
                          <div className="pr-user-avatar" style={{ backgroundColor: getStatusColor(partner.status) }}>
                            {partner.first_name?.charAt(0) || '?'}
                          </div>
                          <div>
                            <div className="pr-user-name">
                              {partner.first_name} {partner.last_name}
                            </div>
                            <div className="pr-user-email">{partner.email}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="pr-badge pr-badge-type">
                          {getPartnerTypeLabel(partner.partner_type)}
                        </span>
                      </td>
                      <td>{partner.company_name || partner.business_name || '-'}</td>
                      <td>{formatPhoneNumber(partner.phone) || '-'}</td>
                      <td>
                        {partner.source === 'retr' ? (
                          <span className="pr-badge pr-badge-info">RETR</span>
                        ) : (
                          partner.source || 'Direct'
                        )}
                      </td>
                      <td>
                        {partner.overall_score ? (
                          <span
                            className="pr-score-badge"
                            style={{
                              backgroundColor: partner.overall_score >= 80 ? '#dcfce7' :
                                             partner.overall_score >= 60 ? '#fef3c7' :
                                             partner.overall_score >= 40 ? '#ffedd5' : '#fee2e2',
                              color: partner.overall_score >= 80 ? '#166534' :
                                    partner.overall_score >= 60 ? '#92400e' :
                                    partner.overall_score >= 40 ? '#9a3412' : '#991b1b'
                            }}
                          >
                            {Math.round(partner.overall_score)}
                          </span>
                        ) : (
                          <span style={{ color: '#9ca3af' }}>-</span>
                        )}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <select
                          value={partner.status}
                          onChange={(e) => handleStatusChange(partner.id, e.target.value)}
                          className="pr-select pr-select-inline"
                          style={{ backgroundColor: getStatusColor(partner.status), color: 'white' }}
                        >
                          {PARTNER_STATUSES.map((s) => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      </td>
                      <td className="pr-actions-cell" onClick={(e) => e.stopPropagation()}>
                        <button
                          className="pr-btn pr-btn-small pr-btn-primary"
                          onClick={() => navigate(`/partner-recruiting/${partner.id}`)}
                          title="View full profile"
                        >
                          View
                        </button>
                        <button
                          className="pr-btn pr-btn-small pr-btn-secondary"
                          onClick={() => setSelectedPartner(partner)}
                          title="Quick view"
                        >
                          ...
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Add Partner Modal */}
      {showAddPartner && (
        <div className="pr-modal-overlay">
          <div className="pr-modal pr-modal-large">
            <div className="pr-modal-header">
              <h3>Add Partner</h3>
              <button className="pr-modal-close" onClick={() => setShowAddPartner(false)}>&times;</button>
            </div>
            <form onSubmit={handleAddPartner}>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>First Name*</label>
                  <input
                    type="text"
                    value={newPartner.first_name}
                    onChange={(e) => setNewPartner({ ...newPartner, first_name: e.target.value })}
                    required
                    className="pr-input"
                  />
                </div>
                <div className="pr-form-group">
                  <label>Last Name*</label>
                  <input
                    type="text"
                    value={newPartner.last_name}
                    onChange={(e) => setNewPartner({ ...newPartner, last_name: e.target.value })}
                    required
                    className="pr-input"
                  />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Email*</label>
                  <input
                    type="email"
                    value={newPartner.email}
                    onChange={(e) => setNewPartner({ ...newPartner, email: e.target.value })}
                    required
                    className="pr-input"
                  />
                </div>
                <div className="pr-form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={newPartner.phone}
                    onChange={(e) => setNewPartner({ ...newPartner, phone: e.target.value })}
                    className="pr-input"
                  />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Partner Type*</label>
                  <select
                    value={newPartner.partner_type}
                    onChange={(e) => setNewPartner({ ...newPartner, partner_type: e.target.value })}
                    required
                    className="pr-select"
                  >
                    {PARTNER_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div className="pr-form-group">
                  <label>Source</label>
                  <select
                    value={newPartner.source}
                    onChange={(e) => setNewPartner({ ...newPartner, source: e.target.value })}
                    className="pr-select"
                  >
                    {PARTNER_SOURCES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Company Name</label>
                  <input
                    type="text"
                    value={newPartner.company_name}
                    onChange={(e) => setNewPartner({ ...newPartner, company_name: e.target.value })}
                    className="pr-input"
                  />
                </div>
                <div className="pr-form-group">
                  <label>License Number</label>
                  <input
                    type="text"
                    value={newPartner.license_number}
                    onChange={(e) => setNewPartner({ ...newPartner, license_number: e.target.value })}
                    className="pr-input"
                  />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={newPartner.city}
                    onChange={(e) => setNewPartner({ ...newPartner, city: e.target.value })}
                    className="pr-input"
                  />
                </div>
                <div className="pr-form-group">
                  <label>State</label>
                  <input
                    type="text"
                    value={newPartner.state}
                    onChange={(e) => setNewPartner({ ...newPartner, state: e.target.value })}
                    maxLength={2}
                    placeholder="CA"
                    className="pr-input"
                  />
                </div>
              </div>
              <div className="pr-form-group">
                <label>Notes</label>
                <textarea
                  value={newPartner.notes}
                  onChange={(e) => setNewPartner({ ...newPartner, notes: e.target.value })}
                  placeholder="Additional notes about this partner..."
                  rows="3"
                  className="pr-textarea"
                />
              </div>
              <div className="pr-modal-actions">
                <button type="button" className="pr-btn pr-btn-secondary" onClick={() => setShowAddPartner(false)}>
                  Cancel
                </button>
                <button type="submit" className="pr-btn pr-btn-primary">
                  Add Partner
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Quick View Modal */}
      {selectedPartner && (
        <div className="pr-modal-overlay">
          <div className="pr-modal pr-modal-large">
            <div className="pr-modal-header">
              <h3>{selectedPartner.first_name} {selectedPartner.last_name}</h3>
              <button className="pr-modal-close" onClick={() => setSelectedPartner(null)}>&times;</button>
            </div>
            <div className="pr-detail-content">
              <div className="pr-detail-section">
                <h4>Contact Information</h4>
                <p><strong>Email:</strong> {selectedPartner.email || 'Not provided'}</p>
                <p><strong>Phone:</strong> {formatPhoneNumber(selectedPartner.phone) || 'Not provided'}</p>
              </div>
              <div className="pr-detail-section">
                <h4>Business Details</h4>
                <p><strong>Type:</strong> {getPartnerTypeLabel(selectedPartner.partner_type)}</p>
                <p><strong>Company:</strong> {selectedPartner.company_name || selectedPartner.business_name || 'Not specified'}</p>
                <p><strong>License #:</strong> {selectedPartner.license_number || 'Not provided'}</p>
                <p><strong>Location:</strong> {selectedPartner.city && selectedPartner.state ? `${selectedPartner.city}, ${selectedPartner.state}` : 'Not specified'}</p>
                <p><strong>Source:</strong> {selectedPartner.source || 'Direct'}</p>
              </div>
              {selectedPartner.overall_score && (
                <div className="pr-detail-section">
                  <h4>Assessment</h4>
                  <p><strong>Overall Score:</strong> {Math.round(selectedPartner.overall_score)}/100</p>
                </div>
              )}
              {selectedPartner.notes && (
                <div className="pr-detail-section">
                  <h4>Notes</h4>
                  <p>{selectedPartner.notes}</p>
                </div>
              )}
              <div className="pr-detail-section">
                <h4>Status</h4>
                <select
                  value={selectedPartner.status || 'new'}
                  onChange={(e) => {
                    handleStatusChange(selectedPartner.id, e.target.value);
                    setSelectedPartner({ ...selectedPartner, status: e.target.value });
                  }}
                  className="pr-select"
                >
                  {PARTNER_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="pr-modal-actions">
              <button
                className="pr-btn pr-btn-primary"
                onClick={() => navigate(`/partner-recruiting/${selectedPartner.id}`)}
              >
                View Full Profile
              </button>
              <button className="pr-btn pr-btn-secondary" onClick={() => setSelectedPartner(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PartnerRecruitingDashboard;
