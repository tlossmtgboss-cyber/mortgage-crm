/**
 * Scheduler Analytics
 *
 * Read-only metrics dashboard computed client-side from appointment data.
 * Self-contained component with own state, loading, and API calls.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './SchedulerAnalytics.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const PERIOD_OPTIONS = [
  { value: 7, label: '7 Days' },
  { value: 30, label: '30 Days' },
  { value: 90, label: '90 Days' },
];

const SchedulerAnalytics = () => {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState(30);

  const loadAppointments = useCallback(async (days) => {
    setLoading(true);
    setError(null);
    try {
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - days * 86400000).toISOString().split('T')[0];

      const res = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments?start_date=${startDate}&end_date=${endDate}&limit=500`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) throw new Error('Failed to load appointments');
      const data = await res.json();
      setAppointments(data.appointments || data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAppointments(period);
  }, [period, loadAppointments]);

  const computeMetrics = () => {
    const total = appointments.length;
    if (total === 0) return null;

    const cancelled = appointments.filter(a => a.status === 'cancelled').length;
    const noShow = appointments.filter(a => a.status === 'no_show').length;
    const completed = appointments.filter(a => a.status === 'completed').length;
    const denominator = total - cancelled;

    // No-show rate
    const noShowRate = denominator > 0 ? (noShow / denominator) * 100 : 0;

    // Completion rate
    const completionRate = denominator > 0 ? (completed / denominator) * 100 : 0;

    // Avg booking lead time (days between created_at and scheduled start)
    let totalLeadDays = 0;
    let leadCount = 0;
    appointments.forEach(a => {
      if (a.created_at && (a.start_time || a.scheduled_at)) {
        const created = new Date(a.created_at);
        const scheduled = new Date(a.start_time || a.scheduled_at);
        const diff = (scheduled - created) / 86400000;
        if (diff >= 0) {
          totalLeadDays += diff;
          leadCount++;
        }
      }
    });
    const avgLeadTime = leadCount > 0 ? totalLeadDays / leadCount : 0;

    // By type
    const byType = {};
    appointments.forEach(a => {
      const type = a.appointment_type || a.type_name || 'Unspecified';
      byType[type] = (byType[type] || 0) + 1;
    });

    // By status
    const byStatus = {};
    appointments.forEach(a => {
      const status = a.status || 'unknown';
      byStatus[status] = (byStatus[status] || 0) + 1;
    });

    // By assigned user (team utilization)
    const byUser = {};
    appointments.forEach(a => {
      const user = a.assigned_to_name || a.lo_name || a.user_name || 'Unassigned';
      byUser[user] = (byUser[user] || 0) + 1;
    });

    return {
      total,
      cancelled,
      noShow,
      completed,
      noShowRate,
      completionRate,
      avgLeadTime,
      byType,
      byStatus,
      byUser,
    };
  };

  const metrics = computeMetrics();
  const maxByType = metrics ? Math.max(...Object.values(metrics.byType)) : 0;
  const maxByUser = metrics ? Math.max(...Object.values(metrics.byUser)) : 0;

  if (loading) {
    return (
      <div className="sa-container">
        <div className="sa-loading" role="status">
          <div className="sa-spinner"></div>
          <p>Loading analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="sa-container">
      <div className="sa-header">
        <div>
          <h2>Scheduler Analytics</h2>
          <p className="sa-subtitle">Appointment metrics and team utilization.</p>
        </div>
        <div className="sa-period-toggle">
          {PERIOD_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`sa-period-btn ${period === opt.value ? 'active' : ''}`}
              onClick={() => setPeriod(opt.value)}
              aria-label={`View analytics for last ${opt.value} days`}
              aria-current={period === opt.value ? 'true' : undefined}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="sa-error" role="alert">
          <i className="fas fa-exclamation-circle"></i>
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {!metrics ? (
        <div className="sa-empty" role="status">
          <i className="fas fa-chart-bar"></i>
          <h3>No Data</h3>
          <p>No appointments found for the selected period.</p>
        </div>
      ) : (
        <>
          {/* Metric Cards */}
          <div className="sa-metrics-grid">
            <div className="sa-metric-card">
              <div className="sa-metric-value">{metrics.total}</div>
              <div className="sa-metric-label">Total Appointments</div>
            </div>
            <div className="sa-metric-card">
              <div className={`sa-metric-value ${metrics.noShowRate > 15 ? 'warning' : ''}`}>
                {metrics.noShowRate.toFixed(1)}%
                {metrics.noShowRate > 15 && <span className="sr-only"> (high)</span>}
              </div>
              <div className="sa-metric-label">No-Show Rate</div>
            </div>
            <div className="sa-metric-card">
              <div className="sa-metric-value">{metrics.avgLeadTime.toFixed(1)}</div>
              <div className="sa-metric-label">Avg Lead Time (days)</div>
            </div>
            <div className="sa-metric-card">
              <div className={`sa-metric-value ${metrics.completionRate > 80 ? 'success' : ''}`}>
                {metrics.completionRate.toFixed(1)}%
                {metrics.completionRate > 80 && <span className="sr-only"> (good)</span>}
              </div>
              <div className="sa-metric-label">Completion Rate</div>
            </div>
          </div>

          {/* Breakdowns */}
          <div className="sa-breakdown-grid">
            {/* By Type */}
            <div className="sa-breakdown-card">
              <h3>By Type</h3>
              {Object.entries(metrics.byType)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div key={type} className="sa-bar-row">
                    <div className="sa-bar-label">{type}</div>
                    <div className="sa-bar-track" role="img" aria-label={`${type}: ${count} appointments`}>
                      <div
                        className="sa-bar-fill"
                        style={{ width: `${maxByType > 0 ? (count / maxByType) * 100 : 0}%` }}
                      />
                    </div>
                    <div className="sa-bar-value">{count}</div>
                  </div>
                ))}
            </div>

            {/* By Status */}
            <div className="sa-breakdown-card">
              <h3>By Status</h3>
              <div className="sa-status-list">
                {Object.entries(metrics.byStatus)
                  .sort((a, b) => b[1] - a[1])
                  .map(([status, count]) => (
                    <div key={status} className="sa-status-row">
                      <span className={`sa-status-dot ${status}`} aria-hidden="true"></span>
                      <span className="sa-status-name">{status.replace(/_/g, ' ')}</span>
                      <span className="sa-status-count">{count}</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {/* Team Utilization */}
          {Object.keys(metrics.byUser).length > 1 && (
            <div className="sa-breakdown-card full-width">
              <h3>Team Utilization</h3>
              {Object.entries(metrics.byUser)
                .sort((a, b) => b[1] - a[1])
                .map(([user, count]) => (
                  <div key={user} className="sa-bar-row">
                    <div className="sa-bar-label user">{user}</div>
                    <div className="sa-bar-track" role="img" aria-label={`${user}: ${count} appointments`}>
                      <div
                        className="sa-bar-fill teal"
                        style={{ width: `${maxByUser > 0 ? (count / maxByUser) * 100 : 0}%` }}
                      />
                    </div>
                    <div className="sa-bar-value">{count}</div>
                  </div>
                ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default SchedulerAnalytics;
