import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getDashboardStats,
  getPipelineMetrics,
  getPartnerCandidates,
  createPartnerCandidate,
  createEmployeeCandidate,
  updatePartnerStatus,
  getStatusColor,
  getStatusLabel,
  getPartnerTypeLabel,
  getAvailableStatuses,
  formatPhoneNumber,
  PARTNER_TYPES,
  PARTNER_STATUSES,
  PARTNER_SOURCES,
  EMPLOYEE_ROLES,
  EMPLOYEE_STATUSES,
  EMPLOYEE_SOURCES
} from '../../services/partnerRecruitingApi';
import './PartnerRecruiting.css';

const PartnerRecruitingDashboard = () => {
  const navigate = useNavigate();

  // State
  const [activeTab, setActiveTab] = useState('overview');
  const [activeCategory, setActiveCategory] = useState('partner'); // 'partner' | 'employee'
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
  const [showAddEmployee, setShowAddEmployee] = useState(false);
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

  // New employee form
  const [newEmployee, setNewEmployee] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    employee_role: 'loan_officer',
    nmls_id: '',
    current_employer: '',
    years_experience: '',
    desired_compensation: '',
    source: 'referral',
    city: '',
    state: '',
    notes: ''
  });

  const isEmployee = activeCategory === 'employee';

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsData, metricsData] = await Promise.all([
        getDashboardStats(activeCategory).catch(() => null),
        getPipelineMetrics(90, activeCategory).catch(() => null)
      ]);

      setStats(statsData);
      setMetrics(metricsData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [activeCategory]);

  const loadPartners = useCallback(async () => {
    try {
      const data = await getPartnerCandidates({
        status: statusFilter,
        partner_type: typeFilter,
        search: searchQuery,
        candidate_category: activeCategory,
        limit: 100
      });
      setPartners(data.candidates || []);
    } catch (err) {
      console.error('Failed to load candidates:', err);
    }
  }, [statusFilter, typeFilter, searchQuery, activeCategory]);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  useEffect(() => {
    if (activeTab === 'candidates') {
      loadPartners();
    }
  }, [activeTab, loadPartners]);

  const handleCategoryChange = (category) => {
    setActiveCategory(category);
    setStatusFilter('');
    setTypeFilter('');
    setSearchQuery('');
  };

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
        first_name: '', last_name: '', email: '', phone: '',
        partner_type: 'realtor', company_name: '', license_number: '',
        license_state: '', source: 'referral', city: '', state: '', notes: ''
      });
      await loadPartners();
      await loadDashboardData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddEmployee = async (e) => {
    e.preventDefault();
    try {
      await createEmployeeCandidate({
        ...newEmployee,
        years_experience: newEmployee.years_experience ? parseInt(newEmployee.years_experience) : null
      });
      setShowAddEmployee(false);
      setNewEmployee({
        first_name: '', last_name: '', email: '', phone: '',
        employee_role: 'loan_officer', nmls_id: '', current_employer: '',
        years_experience: '', desired_compensation: '', source: 'referral',
        city: '', state: '', notes: ''
      });
      await loadPartners();
      await loadDashboardData();
    } catch (err) {
      setError(err.message);
    }
  };

  const currentStatuses = isEmployee ? EMPLOYEE_STATUSES : PARTNER_STATUSES;
  const currentTypes = isEmployee ? EMPLOYEE_ROLES : PARTNER_TYPES;
  const currentSources = isEmployee ? EMPLOYEE_SOURCES : PARTNER_SOURCES;

  if (loading && !stats) {
    return (
      <div className="pr-loading">
        <div className="pr-spinner"></div>
        <p>Loading Recruiting...</p>
      </div>
    );
  }

  return (
    <div className="pr-container">
      {/* Header */}
      <div className="pr-header">
        <div className="pr-header-left">
          <h1>Partner & Employee Recruiting</h1>
          <p>{isEmployee ? 'Build your team' : 'Build your referral partner network'}</p>
        </div>
        <div className="pr-header-actions">
          <button
            className="pr-btn pr-btn-secondary"
            onClick={() => setShowAddPartner(true)}
          >
            + Add Partner
          </button>
          <button
            className="pr-btn pr-btn-primary"
            onClick={() => setShowAddEmployee(true)}
          >
            + Add Employee
          </button>
        </div>
      </div>

      {error && (
        <div className="pr-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Category Toggle */}
      <div className="pr-category-toggle" style={{ display: 'flex', gap: '0', marginBottom: '16px', borderBottom: '2px solid #e5e7eb' }}>
        <button
          style={{
            padding: '10px 24px',
            border: 'none',
            borderBottom: activeCategory === 'partner' ? '2px solid #3b82f6' : '2px solid transparent',
            background: 'none',
            cursor: 'pointer',
            fontWeight: activeCategory === 'partner' ? 600 : 400,
            color: activeCategory === 'partner' ? '#3b82f6' : '#6b7280',
            fontSize: '14px',
            marginBottom: '-2px'
          }}
          onClick={() => handleCategoryChange('partner')}
        >
          Partners
        </button>
        <button
          style={{
            padding: '10px 24px',
            border: 'none',
            borderBottom: activeCategory === 'employee' ? '2px solid #8b5cf6' : '2px solid transparent',
            background: 'none',
            cursor: 'pointer',
            fontWeight: activeCategory === 'employee' ? 600 : 400,
            color: activeCategory === 'employee' ? '#8b5cf6' : '#6b7280',
            fontSize: '14px',
            marginBottom: '-2px'
          }}
          onClick={() => handleCategoryChange('employee')}
        >
          Employees
        </button>
      </div>

      {/* Tabs */}
      <div className="pr-tabs">
        <button
          className={`pr-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`pr-tab ${activeTab === 'candidates' ? 'active' : ''}`}
          onClick={() => setActiveTab('candidates')}
        >
          {isEmployee ? 'Candidates' : 'Partners'}
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
                onClick={() => { setStatusFilter(''); setActiveTab('candidates'); }}
                title={`View all active ${isEmployee ? 'candidates' : 'partners'}`}
              >
                <div className="pr-stat-value">{stats.total_active || 0}</div>
                <div className="pr-stat-label">Active {isEmployee ? 'Candidates' : 'Partners'}</div>
              </div>
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter('new'); setActiveTab('candidates'); }}
                title={`View new ${isEmployee ? 'candidates' : 'partners'}`}
              >
                <div className="pr-stat-value" style={{ color: '#3b82f6' }}>
                  {stats.new_this_week || 0}
                </div>
                <div className="pr-stat-label">New This Week</div>
              </div>
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter('meeting_scheduled'); setActiveTab('candidates'); }}
                title="View scheduled meetings"
              >
                <div className="pr-stat-value" style={{ color: '#f59e0b' }}>
                  {stats.upcoming_meetings || 0}
                </div>
                <div className="pr-stat-label">Meetings Scheduled</div>
              </div>
              {isEmployee ? (
                <div
                  className="pr-card pr-stat-card pr-clickable"
                  onClick={() => { setStatusFilter('offer'); setActiveTab('candidates'); }}
                  title="View pending offers"
                >
                  <div className="pr-stat-value" style={{ color: '#14b8a6' }}>
                    {stats.by_status?.offer || 0}
                  </div>
                  <div className="pr-stat-label">Offers Pending</div>
                </div>
              ) : (
                <div
                  className="pr-card pr-stat-card pr-clickable"
                  onClick={() => { setStatusFilter('proposal_sent'); setActiveTab('candidates'); }}
                  title="View pending proposals"
                >
                  <div className="pr-stat-value" style={{ color: '#22c55e' }}>
                    {stats.pending_proposals || 0}
                  </div>
                  <div className="pr-stat-label">Proposals Pending</div>
                </div>
              )}
              <div
                className="pr-card pr-stat-card pr-clickable"
                onClick={() => { setStatusFilter(isEmployee ? 'hired' : 'onboarded'); setActiveTab('candidates'); }}
                title={`View ${isEmployee ? 'hired' : 'onboarded'}`}
              >
                <div className="pr-stat-value" style={{ color: '#10b981' }}>
                  {stats.onboarded_total || 0}
                </div>
                <div className="pr-stat-label">{isEmployee ? 'Hired' : 'Onboarded'}</div>
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
                    <span className="pr-metric-label">Overall Conversion</span>
                    <span className="pr-metric-value">
                      {metrics.conversion_rates?.overall_conversion || 0}%
                    </span>
                  </div>
                  <div className="pr-progress-container">
                    <div
                      className="pr-progress-bar"
                      style={{
                        width: `${metrics.conversion_rates?.overall_conversion || 0}%`,
                        backgroundColor: '#10b981'
                      }}
                    />
                  </div>
                </div>
                <div className="pr-card pr-metric-card">
                  <div className="pr-metric-header">
                    <span className="pr-metric-label">Contact Rate</span>
                    <span className="pr-metric-value">
                      {metrics.conversion_rates?.contact_rate || 0}%
                    </span>
                  </div>
                  <div className="pr-progress-container">
                    <div
                      className="pr-progress-bar"
                      style={{
                        width: `${metrics.conversion_rates?.contact_rate || 0}%`,
                        backgroundColor: '#8b5cf6'
                      }}
                    />
                  </div>
                </div>
                <div className="pr-card pr-metric-card">
                  <div className="pr-metric-header">
                    <span className="pr-metric-label">Meeting Rate</span>
                    <span className="pr-metric-value">
                      {metrics.conversion_rates?.meeting_rate || 0}%
                    </span>
                  </div>
                  <div className="pr-progress-container">
                    <div
                      className="pr-progress-bar"
                      style={{
                        width: `${metrics.conversion_rates?.meeting_rate || 0}%`,
                        backgroundColor: '#f59e0b'
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Pipeline by Stage */}
          {stats?.pipeline_stages && (
            <div className="pr-section">
              <h2>Pipeline by Stage</h2>
              <div className="pr-pipeline-stages">
                {stats.pipeline_stages.map((stage) => {
                  const statusInfo = currentStatuses.find(s => s.value === stage.status);
                  return (
                    <div
                      key={stage.status}
                      className="pr-pipeline-stage pr-clickable"
                      onClick={() => { setStatusFilter(stage.status); setActiveTab('candidates'); }}
                      title={`View ${stage.label}`}
                    >
                      <div
                        className="pr-stage-count"
                        style={{ backgroundColor: statusInfo?.color || '#6b7280' }}
                      >
                        {stage.count || 0}
                      </div>
                      <div className="pr-stage-label">{stage.label}</div>
                    </div>
                  );
                })}
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
                    <div className="pr-activity-icon" style={{ backgroundColor: getStatusColor(activity.status, activeCategory) }}>
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

      {/* Candidates Tab */}
      {activeTab === 'candidates' && (
        <div className="pr-section">
          <div className="pr-section-header">
            <h2>All {isEmployee ? 'Employee Candidates' : 'Partners'}</h2>
            <div className="pr-filters">
              <input
                type="text"
                placeholder={`Search ${isEmployee ? 'candidates' : 'partners'}...`}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pr-input"
              />
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="pr-select"
              >
                <option value="">{isEmployee ? 'All Roles' : 'All Types'}</option>
                {currentTypes.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="pr-select"
              >
                <option value="">All Statuses</option>
                {currentStatuses.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="pr-table-container">
            <table className="pr-table">
              <thead>
                <tr>
                  <th>{isEmployee ? 'Candidate' : 'Partner'}</th>
                  <th>{isEmployee ? 'Role' : 'Type'}</th>
                  <th>{isEmployee ? 'Current Employer' : 'Company'}</th>
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
                      No {isEmployee ? 'employee candidates' : 'partners'} found. Click "+ Add {isEmployee ? 'Employee' : 'Partner'}" to add one.
                    </td>
                  </tr>
                ) : (
                  partners.map((partner) => {
                    const cat = partner.candidate_category || 'partner';
                    return (
                      <tr
                        key={partner.id}
                        onClick={() => navigate(`/partner-recruiting/${partner.id}`)}
                        style={{ cursor: 'pointer' }}
                        className="pr-clickable-row"
                      >
                        <td>
                          <div className="pr-user-cell">
                            <div className="pr-user-avatar" style={{ backgroundColor: getStatusColor(partner.status, cat) }}>
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
                        <td>{cat === 'employee' ? (partner.current_employer || '-') : (partner.company || '-')}</td>
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
                            style={{ backgroundColor: getStatusColor(partner.status, cat), color: 'white' }}
                          >
                            {getAvailableStatuses(cat).map((s) => (
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
                    );
                  })
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
                  <input type="text" value={newPartner.first_name}
                    onChange={(e) => setNewPartner({ ...newPartner, first_name: e.target.value })}
                    required className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>Last Name*</label>
                  <input type="text" value={newPartner.last_name}
                    onChange={(e) => setNewPartner({ ...newPartner, last_name: e.target.value })}
                    required className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Email*</label>
                  <input type="email" value={newPartner.email}
                    onChange={(e) => setNewPartner({ ...newPartner, email: e.target.value })}
                    required className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>Phone</label>
                  <input type="tel" value={newPartner.phone}
                    onChange={(e) => setNewPartner({ ...newPartner, phone: e.target.value })}
                    className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Partner Type*</label>
                  <select value={newPartner.partner_type}
                    onChange={(e) => setNewPartner({ ...newPartner, partner_type: e.target.value })}
                    required className="pr-select">
                    {PARTNER_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div className="pr-form-group">
                  <label>Source</label>
                  <select value={newPartner.source}
                    onChange={(e) => setNewPartner({ ...newPartner, source: e.target.value })}
                    className="pr-select">
                    {PARTNER_SOURCES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Company Name</label>
                  <input type="text" value={newPartner.company_name}
                    onChange={(e) => setNewPartner({ ...newPartner, company_name: e.target.value })}
                    className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>License Number</label>
                  <input type="text" value={newPartner.license_number}
                    onChange={(e) => setNewPartner({ ...newPartner, license_number: e.target.value })}
                    className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>City</label>
                  <input type="text" value={newPartner.city}
                    onChange={(e) => setNewPartner({ ...newPartner, city: e.target.value })}
                    className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>State</label>
                  <input type="text" value={newPartner.state}
                    onChange={(e) => setNewPartner({ ...newPartner, state: e.target.value })}
                    maxLength={2} placeholder="CA" className="pr-input" />
                </div>
              </div>
              <div className="pr-form-group">
                <label>Notes</label>
                <textarea value={newPartner.notes}
                  onChange={(e) => setNewPartner({ ...newPartner, notes: e.target.value })}
                  placeholder="Additional notes about this partner..." rows="3" className="pr-textarea" />
              </div>
              <div className="pr-modal-actions">
                <button type="button" className="pr-btn pr-btn-secondary" onClick={() => setShowAddPartner(false)}>Cancel</button>
                <button type="submit" className="pr-btn pr-btn-primary">Add Partner</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Employee Modal */}
      {showAddEmployee && (
        <div className="pr-modal-overlay">
          <div className="pr-modal pr-modal-large">
            <div className="pr-modal-header">
              <h3>Add Employee Candidate</h3>
              <button className="pr-modal-close" onClick={() => setShowAddEmployee(false)}>&times;</button>
            </div>
            <form onSubmit={handleAddEmployee}>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>First Name*</label>
                  <input type="text" value={newEmployee.first_name}
                    onChange={(e) => setNewEmployee({ ...newEmployee, first_name: e.target.value })}
                    required className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>Last Name*</label>
                  <input type="text" value={newEmployee.last_name}
                    onChange={(e) => setNewEmployee({ ...newEmployee, last_name: e.target.value })}
                    required className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Email*</label>
                  <input type="email" value={newEmployee.email}
                    onChange={(e) => setNewEmployee({ ...newEmployee, email: e.target.value })}
                    required className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>Phone</label>
                  <input type="tel" value={newEmployee.phone}
                    onChange={(e) => setNewEmployee({ ...newEmployee, phone: e.target.value })}
                    className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Role*</label>
                  <select value={newEmployee.employee_role}
                    onChange={(e) => setNewEmployee({ ...newEmployee, employee_role: e.target.value })}
                    required className="pr-select">
                    {EMPLOYEE_ROLES.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </div>
                <div className="pr-form-group">
                  <label>Source</label>
                  <select value={newEmployee.source}
                    onChange={(e) => setNewEmployee({ ...newEmployee, source: e.target.value })}
                    className="pr-select">
                    {EMPLOYEE_SOURCES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>NMLS ID</label>
                  <input type="text" value={newEmployee.nmls_id}
                    onChange={(e) => setNewEmployee({ ...newEmployee, nmls_id: e.target.value })}
                    placeholder="e.g. 1234567" className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>Current Employer</label>
                  <input type="text" value={newEmployee.current_employer}
                    onChange={(e) => setNewEmployee({ ...newEmployee, current_employer: e.target.value })}
                    className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Years Experience</label>
                  <input type="number" value={newEmployee.years_experience}
                    onChange={(e) => setNewEmployee({ ...newEmployee, years_experience: e.target.value })}
                    min="0" max="50" className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>Desired Compensation</label>
                  <input type="text" value={newEmployee.desired_compensation}
                    onChange={(e) => setNewEmployee({ ...newEmployee, desired_compensation: e.target.value })}
                    placeholder="e.g. 80/20 split, $65K base" className="pr-input" />
                </div>
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>City</label>
                  <input type="text" value={newEmployee.city}
                    onChange={(e) => setNewEmployee({ ...newEmployee, city: e.target.value })}
                    className="pr-input" />
                </div>
                <div className="pr-form-group">
                  <label>State</label>
                  <input type="text" value={newEmployee.state}
                    onChange={(e) => setNewEmployee({ ...newEmployee, state: e.target.value })}
                    maxLength={2} placeholder="CA" className="pr-input" />
                </div>
              </div>
              <div className="pr-form-group">
                <label>Notes</label>
                <textarea value={newEmployee.notes}
                  onChange={(e) => setNewEmployee({ ...newEmployee, notes: e.target.value })}
                  placeholder="Additional notes about this candidate..." rows="3" className="pr-textarea" />
              </div>
              <div className="pr-modal-actions">
                <button type="button" className="pr-btn pr-btn-secondary" onClick={() => setShowAddEmployee(false)}>Cancel</button>
                <button type="submit" className="pr-btn pr-btn-primary">Add Employee</button>
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
                <h4>{selectedPartner.candidate_category === 'employee' ? 'Candidate Details' : 'Business Details'}</h4>
                <p><strong>{selectedPartner.candidate_category === 'employee' ? 'Role' : 'Type'}:</strong> {getPartnerTypeLabel(selectedPartner.partner_type)}</p>
                {selectedPartner.candidate_category === 'employee' ? (
                  <>
                    <p><strong>Current Employer:</strong> {selectedPartner.current_employer || 'Not specified'}</p>
                    <p><strong>Years Experience:</strong> {selectedPartner.years_experience || 'Not specified'}</p>
                  </>
                ) : (
                  <>
                    <p><strong>Company:</strong> {selectedPartner.company || 'Not specified'}</p>
                    <p><strong>License #:</strong> {selectedPartner.license_number || 'Not provided'}</p>
                  </>
                )}
                <p><strong>Location:</strong> {selectedPartner.location || 'Not specified'}</p>
                <p><strong>Source:</strong> {selectedPartner.source || 'Direct'}</p>
              </div>
              {selectedPartner.overall_score && (
                <div className="pr-detail-section">
                  <h4>Assessment</h4>
                  <p><strong>Overall Score:</strong> {Math.round(selectedPartner.overall_score)}/100</p>
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
                  {getAvailableStatuses(selectedPartner.candidate_category || 'partner').map((s) => (
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
