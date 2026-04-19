import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { rateMonitorAPI } from '../services/api';
import './RateMonitorWidget.css';

/**
 * RateMonitorWidget - Embeddable widget for Portfolio and MUM pages
 *
 * Props:
 *   mumClientId - Optional: Show targets for specific MUM client
 *   compact - Optional: Show compact view (default: false)
 */
function RateMonitorWidget({ mumClientId, compact = false }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    targets: [],
    alerts: [],
    currentRates: null,
    metrics: null,
  });

  useEffect(() => {
    loadData();
  }, [mumClientId]);

  const loadData = async () => {
    try {
      setLoading(true);

      const params = mumClientId ? { mum_client_id: mumClientId } : {};

      const [targetsRes, alertsRes, dashboardRes] = await Promise.allSettled([
        rateMonitorAPI.getTargets({ ...params, is_active: true, limit: 5 }),
        rateMonitorAPI.getAlerts({ ...params, status: 'pending', limit: 5 }),
        rateMonitorAPI.getDashboard(),
      ]);

      const targets = targetsRes.status === 'fulfilled' ? targetsRes.value : null;
      const alerts = alertsRes.status === 'fulfilled' ? alertsRes.value : null;
      const dashboard = dashboardRes.status === 'fulfilled' ? dashboardRes.value : null;

      setData({
        targets: targets?.targets || [],
        alerts: alerts?.alerts || [],
        currentRates: dashboard?.current_rates || null,
        metrics: dashboard?.metrics || null,
      });
    } catch (error) {
      console.error('Failed to load rate monitor data:', error);
    } finally {
      setLoading(false);
    }
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
      default: return 'priority-low';
    }
  };

  if (loading) {
    return (
      <div className={`rate-monitor-widget ${compact ? 'compact' : ''}`}>
        <div className="widget-loading">Loading rate data...</div>
      </div>
    );
  }

  // Compact view for embedding in sidebars/cards
  if (compact) {
    return (
      <div className="rate-monitor-widget compact">
        <div className="widget-header">
          <h4>Rate Monitor</h4>
          <button className="view-all-link" onClick={() => navigate('/rate-monitor')}>
            View All
          </button>
        </div>

        {/* Current Rates */}
        {data.currentRates && (
          <div className="compact-rates">
            <div className="rate-display">
              <span className="rate-term">30yr:</span>
              <span className="rate-value">{formatRate(data.currentRates['30_year'])}</span>
            </div>
            <div className="rate-display">
              <span className="rate-term">15yr:</span>
              <span className="rate-value">{formatRate(data.currentRates['15_year'])}</span>
            </div>
          </div>
        )}

        {/* Quick Stats */}
        <div className="compact-stats">
          <div className="stat-item">
            <span className="stat-value">{data.metrics?.active_monitors || 0}</span>
            <span className="stat-label">Monitoring</span>
          </div>
          <div className="stat-item highlight">
            <span className="stat-value">{data.metrics?.pending_alerts || 0}</span>
            <span className="stat-label">Alerts</span>
          </div>
        </div>

        {/* Top Alert */}
        {data.alerts.length > 0 && (
          <div className="top-alert">
            <div className={`alert-indicator ${getPriorityClass(data.alerts[0].priority)}`}></div>
            <div className="alert-content">
              <span className="client-name">{data.alerts[0].client_name || 'Client'}</span>
              <span className="savings">{formatCurrency(data.alerts[0].monthly_savings)}/mo savings</span>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Full widget view
  return (
    <div className="rate-monitor-widget full">
      <div className="widget-header">
        <h3>Rate Monitor</h3>
        <button className="btn-link" onClick={() => navigate('/rate-monitor')}>
          Open Dashboard
        </button>
      </div>

      {/* Current Rates Banner */}
      {data.currentRates && (
        <div className="rates-row">
          <div className="rate-card">
            <span className="rate-term">30-Year Rate</span>
            <span className="rate-value">{formatRate(data.currentRates['30_year'])}</span>
          </div>
          <div className="rate-card">
            <span className="rate-term">15-Year Rate</span>
            <span className="rate-value">{formatRate(data.currentRates['15_year'])}</span>
          </div>
          {data.currentRates.is_mock && (
            <span className="mock-indicator">Mock Data</span>
          )}
        </div>
      )}

      {/* Stats Row */}
      <div className="stats-row">
        <div className="stat-card">
          <span className="stat-number">{data.metrics?.active_monitors || 0}</span>
          <span className="stat-label">Active Monitors</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{data.metrics?.auto_call_enabled || 0}</span>
          <span className="stat-label">Auto-Call</span>
        </div>
        <div className="stat-card highlight">
          <span className="stat-number">{data.metrics?.pending_alerts || 0}</span>
          <span className="stat-label">Pending Alerts</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{data.metrics?.conversions_this_month || 0}</span>
          <span className="stat-label">Conversions</span>
        </div>
      </div>

      {/* Pending Alerts */}
      {data.alerts.length > 0 && (
        <div className="alerts-section">
          <h4>Pending Alerts</h4>
          <div className="alerts-list">
            {data.alerts.slice(0, 3).map(alert => (
              <div key={alert.id} className={`alert-item ${getPriorityClass(alert.priority)}`}>
                <div className="alert-left">
                  <span className="client-name">{alert.client_name || `Client #${alert.mum_client_id}`}</span>
                  <span className="rate-info">
                    {formatRate(alert.client_rate)} → {formatRate(alert.market_rate)}
                  </span>
                </div>
                <div className="alert-right">
                  <span className="savings-amount">{formatCurrency(alert.monthly_savings)}</span>
                  <span className="savings-label">/month</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Targets (for specific client) */}
      {mumClientId && data.targets.length > 0 && (
        <div className="targets-section">
          <h4>Active Targets</h4>
          <div className="targets-list">
            {data.targets.map(target => (
              <div key={target.id} className="target-item">
                <div className="target-type">{(target.target_type || '').replace(/_/g, ' ')}</div>
                <div className="target-threshold">{target.threshold_description}</div>
                <div className={`target-status ${target.auto_call_enabled ? 'auto-call' : ''}`}>
                  {target.auto_call_enabled ? 'Auto-Call On' : 'Manual'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {data.alerts.length === 0 && data.targets.length === 0 && (
        <div className="empty-state">
          <p>No rate monitoring targets or alerts</p>
          <button className="btn-primary-sm" onClick={() => navigate('/rate-monitor')}>
            Set Up Rate Monitoring
          </button>
        </div>
      )}
    </div>
  );
}

export default RateMonitorWidget;
