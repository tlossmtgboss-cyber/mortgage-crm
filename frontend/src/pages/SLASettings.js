import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import './SLASettings.css';

const SLASettings = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dashboard data
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [measures, setMeasures] = useState([]);
  const [trend, setTrend] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);

  // Modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingMeasure, setEditingMeasure] = useState(null);

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Fetch dashboard summary
      const summaryRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/summary`, { headers });
      if (summaryRes.ok) {
        const summaryData = await summaryRes.json();
        setSummary(summaryData);
      }

      // Fetch alerts
      const alertsRes = await fetch(`${API_BASE_URL}/api/v1/sla/alerts?limit=10`, { headers });
      if (alertsRes.ok) {
        const alertsData = await alertsRes.json();
        setAlerts(alertsData);
      }

      // Fetch measures
      const measuresRes = await fetch(`${API_BASE_URL}/api/v1/sla/measures`, { headers });
      if (measuresRes.ok) {
        const measuresData = await measuresRes.json();
        setMeasures(measuresData);
      }

      // Fetch trend data
      const trendRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/trend`, { headers });
      if (trendRes.ok) {
        const trendData = await trendRes.json();
        setTrend(trendData.data_points || []);
      }

      // Fetch bottlenecks
      const bottlenecksRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/bottlenecks`, { headers });
      if (bottlenecksRes.ok) {
        const bottlenecksData = await bottlenecksRes.json();
        setBottlenecks(bottlenecksData.bottlenecks || []);
      }

      setError(null);
    } catch (err) {
      setError('Failed to load SLA data');
      console.error('Error fetching SLA data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const runMigration = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/sla/migrate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        alert('SLA tables created and default measures seeded!');
        fetchDashboard();
      }
    } catch (err) {
      console.error('Migration error:', err);
    }
  };

  const acknowledgeAlert = async (alertId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/sla/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error acknowledging alert:', err);
    }
  };

  const resolveAlert = async (alertId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/sla/alerts/${alertId}/resolve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ resolution_notes: 'Resolved from dashboard' })
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error resolving alert:', err);
    }
  };

  const saveMeasure = async (measureData) => {
    try {
      const token = localStorage.getItem('token');
      const method = editingMeasure ? 'PUT' : 'POST';
      const url = editingMeasure
        ? `${API_BASE_URL}/api/v1/sla/measures/${editingMeasure.id}`
        : `${API_BASE_URL}/api/v1/sla/measures`;

      await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(measureData)
      });
      setShowEditModal(false);
      setEditingMeasure(null);
      fetchDashboard();
    } catch (err) {
      console.error('Error saving measure:', err);
    }
  };

  const formatMilestoneType = (type) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  const formatTargetUnit = (value, unit) => {
    if (unit === 'hours') return `${value} hours`;
    if (unit === 'days') return `${value} days`;
    if (unit === 'business_days') return `${value} business days`;
    return `${value} ${unit}`;
  };

  if (loading) {
    return (
      <div className="sla-settings-page">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <span>Loading SLA data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="sla-settings-page">
      <div className="page-header">
        <h1>SLA Tracking</h1>
        <p>Monitor loan lifecycle milestones and service level agreements</p>
      </div>

      {/* Dashboard Summary */}
      <div className="sla-dashboard-summary">
        <div className="summary-card on-track">
          <div className="card-label">On Track</div>
          <div className="card-value">{summary?.on_track_count || 0}</div>
          <div className="card-sub">milestones within SLA</div>
        </div>
        <div className="summary-card at-risk">
          <div className="card-label">At Risk</div>
          <div className="card-value">{summary?.at_risk_count || 0}</div>
          <div className="card-sub">approaching deadline</div>
        </div>
        <div className="summary-card overdue">
          <div className="card-label">Overdue</div>
          <div className="card-value">{summary?.overdue_count || 0}</div>
          <div className="card-sub">past deadline</div>
        </div>
        <div className="summary-card alerts">
          <div className="card-label">Active Alerts</div>
          <div className="card-value">{summary?.active_alerts_count || 0}</div>
          <div className="card-sub">requiring attention</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="sla-tabs">
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={activeTab === 'measures' ? 'active' : ''}
          onClick={() => setActiveTab('measures')}
        >
          SLA Measures
        </button>
        <button
          className={activeTab === 'alerts' ? 'active' : ''}
          onClick={() => setActiveTab('alerts')}
        >
          Alerts ({alerts.length})
        </button>
        <button
          className={activeTab === 'bottlenecks' ? 'active' : ''}
          onClick={() => setActiveTab('bottlenecks')}
        >
          Bottlenecks
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <>
          <div className="sla-section">
            <h2><span className="icon">📊</span> Performance Overview</h2>
            <div className="trend-stats">
              <div className="trend-stat">
                <div className={`value ${(summary?.overall_on_time_rate || 0) >= 85 ? 'positive' : 'negative'}`}>
                  {(summary?.overall_on_time_rate || 0).toFixed(1)}%
                </div>
                <div className="label">On-Time Rate (30 days)</div>
              </div>
              <div className="trend-stat">
                <div className="value">
                  {(summary?.avg_completion_time_hours || 0).toFixed(1)}h
                </div>
                <div className="label">Avg Completion Time</div>
              </div>
              <div className="trend-stat">
                <div className="value">{summary?.total_active_milestones || 0}</div>
                <div className="label">Active Milestones</div>
              </div>
              <div className="trend-stat">
                <div className="value">{measures.length}</div>
                <div className="label">SLA Measures</div>
              </div>
            </div>

            {/* Milestone Breakdown */}
            {summary?.milestone_breakdown && Object.keys(summary.milestone_breakdown).length > 0 && (
              <div style={{ marginTop: '24px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>
                  Active Milestones by Stage
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
                  {Object.entries(summary.milestone_breakdown).map(([type, stats]) => (
                    <div key={type} style={{
                      padding: '12px',
                      background: '#f9fafb',
                      borderRadius: '8px',
                      fontSize: '13px'
                    }}>
                      <div style={{ fontWeight: '500', marginBottom: '4px' }}>
                        {formatMilestoneType(type)}
                      </div>
                      <div style={{ color: '#6b7280' }}>
                        {stats.total} total
                        {stats.at_risk > 0 && <span style={{ color: '#f59e0b' }}> ({stats.at_risk} at risk)</span>}
                        {stats.overdue > 0 && <span style={{ color: '#ef4444' }}> ({stats.overdue} overdue)</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Recent Alerts Preview */}
          {alerts.length > 0 && (
            <div className="sla-section">
              <h2><span className="icon">🔔</span> Recent Alerts</h2>
              <div className="alerts-list">
                {alerts.slice(0, 3).map((alert) => (
                  <div key={alert.id} className={`alert-item ${alert.alert_type}`}>
                    <span className="alert-icon">
                      {alert.alert_type === 'overdue' ? '🚨' : alert.alert_type === 'at_risk' ? '⚠️' : 'ℹ️'}
                    </span>
                    <div className="alert-content">
                      <div className="alert-title">{alert.title}</div>
                      <div className="alert-message">{alert.message}</div>
                      <div className="alert-meta">
                        <span>Loan: {alert.loan_number || alert.loan_id || 'N/A'}</span>
                        <span>Triggered: {new Date(alert.triggered_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="alert-actions">
                      <button className="btn-acknowledge" onClick={() => acknowledgeAlert(alert.id)}>
                        Acknowledge
                      </button>
                      <button className="btn-resolve" onClick={() => resolveAlert(alert.id)}>
                        Resolve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {alerts.length > 3 && (
                <button
                  onClick={() => setActiveTab('alerts')}
                  style={{
                    marginTop: '12px',
                    padding: '8px 16px',
                    background: 'none',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    cursor: 'pointer'
                  }}
                >
                  View All Alerts ({alerts.length})
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* SLA Measures Tab */}
      {activeTab === 'measures' && (
        <div className="sla-section">
          <h2>
            <span className="icon">⏱️</span> SLA Measures Configuration
            <button
              onClick={() => {
                setEditingMeasure(null);
                setShowEditModal(true);
              }}
              style={{
                marginLeft: 'auto',
                padding: '8px 16px',
                background: '#218D8D',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              + Add Measure
            </button>
          </h2>

          {measures.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📋</div>
              <h3>No SLA Measures Configured</h3>
              <p>Set up SLA measures to start tracking loan lifecycle milestones</p>
              <button onClick={runMigration}>Initialize Default Measures</button>
            </div>
          ) : (
            <table className="measures-table">
              <thead>
                <tr>
                  <th>Milestone</th>
                  <th>Target</th>
                  <th>Warning At</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {measures.map((measure) => (
                  <tr key={measure.id}>
                    <td>
                      <div className="milestone-name">{measure.name}</div>
                      <div className="milestone-type">{formatMilestoneType(measure.milestone_type)}</div>
                    </td>
                    <td>
                      <span className="target-badge">
                        {formatTargetUnit(measure.target_value, measure.target_unit)}
                      </span>
                    </td>
                    <td>{measure.warning_threshold_pct}%</td>
                    <td>
                      <div className={`status-indicator ${measure.is_active ? 'active' : 'inactive'}`}>
                        <span className="dot"></span>
                        {measure.is_active ? 'Active' : 'Inactive'}
                      </div>
                    </td>
                    <td>
                      <button
                        onClick={() => {
                          setEditingMeasure(measure);
                          setShowEditModal(true);
                        }}
                        style={{
                          padding: '6px 12px',
                          background: '#f3f4f6',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '13px'
                        }}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="sla-section">
          <h2><span className="icon">🔔</span> All Active Alerts</h2>
          {alerts.length === 0 ? (
            <div className="empty-state">
              <div className="icon">✅</div>
              <h3>No Active Alerts</h3>
              <p>All milestones are on track</p>
            </div>
          ) : (
            <div className="alerts-list">
              {alerts.map((alert) => (
                <div key={alert.id} className={`alert-item ${alert.alert_type}`}>
                  <span className="alert-icon">
                    {alert.alert_type === 'overdue' ? '🚨' : alert.alert_type === 'at_risk' ? '⚠️' : 'ℹ️'}
                  </span>
                  <div className="alert-content">
                    <div className="alert-title">{alert.title}</div>
                    <div className="alert-message">{alert.message}</div>
                    <div className="alert-meta">
                      <span>Loan: {alert.loan_number || alert.loan_id || 'N/A'}</span>
                      <span>Triggered: {new Date(alert.triggered_at).toLocaleString()}</span>
                      <span>Status: {alert.status}</span>
                    </div>
                  </div>
                  <div className="alert-actions">
                    <button className="btn-acknowledge" onClick={() => acknowledgeAlert(alert.id)}>
                      Acknowledge
                    </button>
                    <button className="btn-resolve" onClick={() => resolveAlert(alert.id)}>
                      Resolve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Bottlenecks Tab */}
      {activeTab === 'bottlenecks' && (
        <div className="sla-section">
          <h2><span className="icon">🚧</span> Bottleneck Analysis</h2>
          <p style={{ color: '#6b7280', marginBottom: '20px' }}>
            Stages causing the most delays based on the last 30 days of data
          </p>
          {bottlenecks.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📈</div>
              <h3>No Bottlenecks Detected</h3>
              <p>All stages are performing within acceptable parameters</p>
            </div>
          ) : (
            <div className="bottleneck-list">
              {bottlenecks.map((bottleneck, index) => (
                <div key={bottleneck.milestone_type} className="bottleneck-item">
                  <div className={`bottleneck-rank ${index === 1 ? 'rank-2' : index === 2 ? 'rank-3' : ''}`}>
                    {index + 1}
                  </div>
                  <div className="bottleneck-content">
                    <div className="bottleneck-name">{formatMilestoneType(bottleneck.milestone_type)}</div>
                    <div className="bottleneck-stats">
                      <span>Avg delay: {bottleneck.avg_delay_hours.toFixed(1)} hours</span>
                      <span>Frequency: {bottleneck.delay_frequency_pct.toFixed(0)}% of loans</span>
                      <span>Affected: {bottleneck.total_affected_loans} loans</span>
                    </div>
                  </div>
                  <div className="bottleneck-bar">
                    <div
                      className="fill"
                      style={{ width: `${Math.min(bottleneck.delay_frequency_pct, 100)}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <EditMeasureModal
          measure={editingMeasure}
          onSave={saveMeasure}
          onClose={() => {
            setShowEditModal(false);
            setEditingMeasure(null);
          }}
        />
      )}
    </div>
  );
};

// Edit Measure Modal Component
const EditMeasureModal = ({ measure, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    name: measure?.name || '',
    milestone_type: measure?.milestone_type || 'lead_response',
    description: measure?.description || '',
    target_value: measure?.target_value || 4,
    target_unit: measure?.target_unit || 'hours',
    warning_threshold_pct: measure?.warning_threshold_pct || 75,
    critical_threshold_pct: measure?.critical_threshold_pct || 100,
    business_hours_only: measure?.business_hours_only ?? true,
    is_active: measure?.is_active ?? true
  });

  const milestoneTypes = [
    'lead_response', 'initial_consultation', 'preapproval',
    'application_submitted', 'document_collection', 'application_complete',
    'processing_start', 'appraisal_ordered', 'appraisal_received',
    'title_ordered', 'title_received', 'submitted_to_uw', 'uw_decision',
    'conditions_issued', 'conditions_cleared', 'clear_to_close',
    'closing_docs_out', 'closing_scheduled', 'closed', 'funded'
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{measure ? 'Edit SLA Measure' : 'Add SLA Measure'}</h3>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Milestone Type</label>
              <select
                value={formData.milestone_type}
                onChange={e => setFormData({ ...formData, milestone_type: e.target.value })}
                disabled={!!measure}
              >
                {milestoneTypes.map(type => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea
                value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                rows={2}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Target Value</label>
                <input
                  type="number"
                  value={formData.target_value}
                  onChange={e => setFormData({ ...formData, target_value: parseFloat(e.target.value) })}
                  min="0"
                  step="0.5"
                  required
                />
              </div>
              <div className="form-group">
                <label>Target Unit</label>
                <select
                  value={formData.target_unit}
                  onChange={e => setFormData({ ...formData, target_unit: e.target.value })}
                >
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                  <option value="business_days">Business Days</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Warning Threshold (%)</label>
                <input
                  type="number"
                  value={formData.warning_threshold_pct}
                  onChange={e => setFormData({ ...formData, warning_threshold_pct: parseFloat(e.target.value) })}
                  min="0"
                  max="100"
                  required
                />
              </div>
              <div className="form-group">
                <label>Critical Threshold (%)</label>
                <input
                  type="number"
                  value={formData.critical_threshold_pct}
                  onChange={e => setFormData({ ...formData, critical_threshold_pct: parseFloat(e.target.value) })}
                  min="0"
                  max="200"
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.business_hours_only}
                  onChange={e => setFormData({ ...formData, business_hours_only: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Business Hours Only
              </label>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Active
              </label>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-save">Save Measure</button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default SLASettings;
