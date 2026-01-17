import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { rateMonitorAPI } from '../services/api';
import RateTargetModal from '../components/RateTargetModal';
import './RateMonitor.css';

function RateMonitor() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dashboard data
  const [metrics, setMetrics] = useState(null);

  // Targets data
  const [targets, setTargets] = useState([]);
  const [targetsTotal, setTargetsTotal] = useState(0);
  const [targetFilters, setTargetFilters] = useState({
    status: '',
    isActive: true,
  });

  // Alerts data
  const [alerts, setAlerts] = useState([]);
  const [alertsTotal, setAlertsTotal] = useState(0);
  const [alertFilters, setAlertFilters] = useState({
    status: 'pending',
    priority: '',
  });

  // Modal state
  const [showTargetModal, setShowTargetModal] = useState(false);
  const [editingTarget, setEditingTarget] = useState(null);

  // Current rates
  const [currentRates, setCurrentRates] = useState(null);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await rateMonitorAPI.getDashboard();
      setMetrics(data.metrics);
      setCurrentRates(data.current_rates);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setError('Failed to load dashboard data');
    }
  }, []);

  const loadTargets = useCallback(async () => {
    try {
      const params = {};
      if (targetFilters.status) params.status = targetFilters.status;
      if (targetFilters.isActive !== null) params.is_active = targetFilters.isActive;

      const data = await rateMonitorAPI.getTargets(params);
      setTargets(data.targets || []);
      setTargetsTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load targets:', err);
    }
  }, [targetFilters]);

  const loadAlerts = useCallback(async () => {
    try {
      const params = {};
      if (alertFilters.status) params.status = alertFilters.status;
      if (alertFilters.priority) params.priority = alertFilters.priority;

      const data = await rateMonitorAPI.getAlerts(params);
      setAlerts(data.alerts || []);
      setAlertsTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load alerts:', err);
    }
  }, [alertFilters]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([loadDashboard(), loadTargets(), loadAlerts()]);
      setLoading(false);
    };
    loadData();
  }, [loadDashboard, loadTargets, loadAlerts]);

  const handleCreateTarget = () => {
    setEditingTarget(null);
    setShowTargetModal(true);
  };

  const handleEditTarget = (target) => {
    setEditingTarget(target);
    setShowTargetModal(true);
  };

  const handleSaveTarget = async (targetData) => {
    try {
      if (editingTarget) {
        await rateMonitorAPI.updateTarget(editingTarget.id, targetData);
      } else {
        await rateMonitorAPI.createTarget(targetData);
      }
      setShowTargetModal(false);
      loadTargets();
      loadDashboard();
    } catch (err) {
      console.error('Failed to save target:', err);
      alert('Failed to save target: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteTarget = async (targetId) => {
    if (!window.confirm('Are you sure you want to delete this target?')) return;

    try {
      await rateMonitorAPI.deleteTarget(targetId);
      loadTargets();
      loadDashboard();
    } catch (err) {
      console.error('Failed to delete target:', err);
      alert('Failed to delete target');
    }
  };

  const handleToggleActive = async (target) => {
    try {
      await rateMonitorAPI.updateTarget(target.id, { is_active: !target.is_active });
      loadTargets();
      loadDashboard();
    } catch (err) {
      console.error('Failed to toggle target:', err);
    }
  };

  const handleInitiateCall = async (alertId) => {
    if (!window.confirm('Initiate an AI call to this client about refinancing?')) return;

    try {
      const result = await rateMonitorAPI.initiateCall(alertId);
      if (result.status === 'initiated') {
        alert('Call initiated successfully!');
        loadAlerts();
      } else {
        alert(result.message || 'Call could not be initiated');
      }
    } catch (err) {
      console.error('Failed to initiate call:', err);
      alert('Failed to initiate call');
    }
  };

  const handleUpdateAlertStatus = async (alertId, status) => {
    try {
      await rateMonitorAPI.updateAlert(alertId, { status });
      loadAlerts();
      loadDashboard();
    } catch (err) {
      console.error('Failed to update alert:', err);
    }
  };

  const handleViewMumClient = (mumClientId) => {
    navigate(`/portfolio/mum/${mumClientId}`);
  };

  const formatCurrency = (amount) => {
    if (!amount && amount !== 0) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatRate = (rate) => {
    if (!rate && rate !== 0) return '-';
    return `${parseFloat(rate).toFixed(3)}%`;
  };

  const getPriorityClass = (priority) => {
    switch (priority) {
      case 'urgent': return 'priority-urgent';
      case 'high': return 'priority-high';
      case 'medium': return 'priority-medium';
      case 'low': return 'priority-low';
      default: return '';
    }
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'pending': return 'status-pending';
      case 'acknowledged': return 'status-acknowledged';
      case 'called': return 'status-called';
      case 'converted': return 'status-converted';
      case 'dismissed': return 'status-dismissed';
      default: return '';
    }
  };

  if (loading) {
    return (
      <div className="rate-monitor-page">
        <div className="loading-spinner">Loading...</div>
      </div>
    );
  }

  return (
    <div className="rate-monitor-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Rate Monitor</h1>
          <p className="subtitle">Track refinance opportunities for MUM clients</p>
        </div>
        <div className="header-actions">
          <button className="btn-primary" onClick={handleCreateTarget}>
            + New Rate Target
          </button>
        </div>
      </div>

      {/* Current Rates Banner */}
      {currentRates && (
        <div className="rates-banner">
          <div className="rates-banner-content">
            <span className="rates-label">Current Rates:</span>
            <span className="rate-item">
              <strong>30-Year:</strong> {formatRate(currentRates['30_year'])}
            </span>
            <span className="rate-item">
              <strong>15-Year:</strong> {formatRate(currentRates['15_year'])}
            </span>
            {currentRates.is_mock && (
              <span className="mock-badge">Mock Data</span>
            )}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs-container">
        <button
          className={`tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`tab ${activeTab === 'targets' ? 'active' : ''}`}
          onClick={() => setActiveTab('targets')}
        >
          Rate Targets ({targetsTotal})
        </button>
        <button
          className={`tab ${activeTab === 'alerts' ? 'active' : ''}`}
          onClick={() => setActiveTab('alerts')}
        >
          Alerts ({alertsTotal})
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && metrics && (
        <div className="dashboard-content">
          <div className="metrics-grid">
            <div className="metric-card">
              <div className="metric-value">{metrics.active_monitors}</div>
              <div className="metric-label">Active Monitors</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.auto_call_enabled}</div>
              <div className="metric-label">Auto-Call Enabled</div>
            </div>
            <div className="metric-card highlight">
              <div className="metric-value">{metrics.pending_alerts}</div>
              <div className="metric-label">Pending Alerts</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.high_priority_alerts}</div>
              <div className="metric-label">High Priority</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.alerts_today}</div>
              <div className="metric-label">Alerts Today</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.calls_made_this_month}</div>
              <div className="metric-label">Calls This Month</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.appointments_this_month}</div>
              <div className="metric-label">Appointments</div>
            </div>
            <div className="metric-card success">
              <div className="metric-value">{metrics.conversions_this_month}</div>
              <div className="metric-label">Conversions</div>
            </div>
          </div>

          <div className="savings-summary">
            <h3>Potential Monthly Savings from Pending Alerts</h3>
            <div className="savings-value">{formatCurrency(metrics.pending_monthly_savings)}</div>
          </div>

          {/* Recent Pending Alerts Preview */}
          <div className="recent-alerts-section">
            <div className="section-header">
              <h3>Recent Pending Alerts</h3>
              <button className="btn-link" onClick={() => setActiveTab('alerts')}>
                View All
              </button>
            </div>
            <div className="alerts-preview">
              {alerts.filter(a => a.status === 'pending').slice(0, 5).map(alert => (
                <div key={alert.id} className="alert-preview-item">
                  <div className="alert-info">
                    <span className="client-name">{alert.client_name || 'Unknown Client'}</span>
                    <span className={`priority-badge ${getPriorityClass(alert.priority)}`}>
                      {alert.priority}
                    </span>
                  </div>
                  <div className="alert-savings">
                    {formatCurrency(alert.monthly_savings)}/month potential savings
                  </div>
                  <div className="alert-actions">
                    <button
                      className="btn-sm btn-primary"
                      onClick={() => handleInitiateCall(alert.id)}
                    >
                      Call
                    </button>
                    <button
                      className="btn-sm btn-secondary"
                      onClick={() => handleViewMumClient(alert.mum_client_id)}
                    >
                      View
                    </button>
                  </div>
                </div>
              ))}
              {alerts.filter(a => a.status === 'pending').length === 0 && (
                <div className="no-alerts">No pending alerts</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Targets Tab */}
      {activeTab === 'targets' && (
        <div className="targets-content">
          <div className="filters-bar">
            <select
              value={targetFilters.status}
              onChange={(e) => setTargetFilters({ ...targetFilters, status: e.target.value })}
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="triggered">Triggered</option>
            </select>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={targetFilters.isActive}
                onChange={(e) => setTargetFilters({ ...targetFilters, isActive: e.target.checked })}
              />
              Active Only
            </label>
          </div>

          <div className="targets-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Target Type</th>
                  <th>Threshold</th>
                  <th>Status</th>
                  <th>Auto-Call</th>
                  <th>Triggers</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {targets.map(target => (
                  <tr key={target.id} className={!target.is_active ? 'inactive-row' : ''}>
                    <td>
                      <span
                        className="client-link"
                        onClick={() => handleViewMumClient(target.mum_client_id)}
                      >
                        {target.client_name || `Client #${target.mum_client_id}`}
                      </span>
                      {target.client_rate && (
                        <div className="client-rate-info">
                          Current: {formatRate(target.client_rate)}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="target-type">{target.target_type.replace(/_/g, ' ')}</span>
                    </td>
                    <td>{target.threshold_description}</td>
                    <td>
                      <span className={`status-badge ${target.status}`}>
                        {target.status}
                      </span>
                    </td>
                    <td>
                      <span className={`auto-call-badge ${target.auto_call_enabled ? 'enabled' : 'disabled'}`}>
                        {target.auto_call_enabled ? 'On' : 'Off'}
                      </span>
                    </td>
                    <td>{target.trigger_count || 0}</td>
                    <td className="actions-cell">
                      <button
                        className="btn-icon"
                        onClick={() => handleToggleActive(target)}
                        title={target.is_active ? 'Pause' : 'Activate'}
                      >
                        {target.is_active ? '⏸' : '▶'}
                      </button>
                      <button
                        className="btn-icon"
                        onClick={() => handleEditTarget(target)}
                        title="Edit"
                      >
                        ✏️
                      </button>
                      <button
                        className="btn-icon delete"
                        onClick={() => handleDeleteTarget(target.id)}
                        title="Delete"
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
                {targets.length === 0 && (
                  <tr>
                    <td colSpan="7" className="no-data">
                      No rate targets found. Click "New Rate Target" to create one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="alerts-content">
          <div className="filters-bar">
            <select
              value={alertFilters.status}
              onChange={(e) => setAlertFilters({ ...alertFilters, status: e.target.value })}
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="called">Called</option>
              <option value="converted">Converted</option>
              <option value="dismissed">Dismissed</option>
            </select>
            <select
              value={alertFilters.priority}
              onChange={(e) => setAlertFilters({ ...alertFilters, priority: e.target.value })}
            >
              <option value="">All Priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="alerts-list">
            {alerts.map(alert => (
              <div key={alert.id} className={`alert-card ${getPriorityClass(alert.priority)}`}>
                <div className="alert-header">
                  <div className="alert-client">
                    <h4
                      className="client-link"
                      onClick={() => handleViewMumClient(alert.mum_client_id)}
                    >
                      {alert.client_name || `Client #${alert.mum_client_id}`}
                    </h4>
                    <span className={`priority-badge ${getPriorityClass(alert.priority)}`}>
                      {alert.priority}
                    </span>
                    <span className={`status-badge ${getStatusClass(alert.status)}`}>
                      {alert.status}
                    </span>
                  </div>
                  <div className="alert-date">
                    {new Date(alert.created_at).toLocaleDateString()}
                  </div>
                </div>

                <div className="alert-body">
                  <div className="rate-comparison">
                    <div className="rate-item">
                      <span className="label">Current Rate:</span>
                      <span className="value">{formatRate(alert.client_rate)}</span>
                    </div>
                    <div className="rate-arrow">→</div>
                    <div className="rate-item">
                      <span className="label">Market Rate:</span>
                      <span className="value highlight">{formatRate(alert.market_rate)}</span>
                    </div>
                  </div>

                  <div className="savings-info">
                    <div className="savings-item">
                      <span className="label">Monthly Savings:</span>
                      <span className="value">{formatCurrency(alert.monthly_savings)}</span>
                    </div>
                    <div className="savings-item">
                      <span className="label">Annual Savings:</span>
                      <span className="value">{formatCurrency(alert.annual_savings)}</span>
                    </div>
                  </div>

                  {alert.call_status && (
                    <div className="call-status">
                      <span className="label">Call Status:</span>
                      <span className={`value ${alert.call_status}`}>
                        {alert.call_status}
                      </span>
                      {alert.call_outcome && (
                        <span className="call-outcome"> - {alert.call_outcome}</span>
                      )}
                    </div>
                  )}
                </div>

                <div className="alert-actions">
                  {alert.status === 'pending' && (
                    <>
                      <button
                        className="btn-primary"
                        onClick={() => handleInitiateCall(alert.id)}
                      >
                        Initiate Call
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'acknowledged')}
                      >
                        Acknowledge
                      </button>
                    </>
                  )}
                  {alert.status === 'acknowledged' && (
                    <>
                      <button
                        className="btn-primary"
                        onClick={() => handleInitiateCall(alert.id)}
                      >
                        Initiate Call
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'dismissed')}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                  {alert.status === 'called' && (
                    <>
                      <button
                        className="btn-success"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'converted')}
                      >
                        Mark Converted
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'dismissed')}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                  <button
                    className="btn-link"
                    onClick={() => handleViewMumClient(alert.mum_client_id)}
                  >
                    View Client
                  </button>
                </div>
              </div>
            ))}
            {alerts.length === 0 && (
              <div className="no-alerts-message">
                No alerts found matching your filters.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Target Modal */}
      {showTargetModal && (
        <RateTargetModal
          target={editingTarget}
          onSave={handleSaveTarget}
          onClose={() => setShowTargetModal(false)}
        />
      )}
    </div>
  );
}

export default RateMonitor;
