// Call Analytics Dashboard - Comprehensive call performance analytics
import React, { useState, useEffect, useCallback } from 'react';
import './CallAnalyticsDashboard.css';

const CallAnalyticsDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateRange, setDateRange] = useState('last_7_days');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');

  // Data states
  const [dailySummary, setDailySummary] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [dispositionBreakdown, setDispositionBreakdown] = useState(null);
  const [hourlyStats, setHourlyStats] = useState(null);
  const [sessionStats, setSessionStats] = useState(null);

  // API base URL
  const API_BASE_URL = process.env.REACT_APP_API_URL || '';

  // Get auth headers
  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  // Calculate date range for API calls
  const getDateRangeParams = useCallback(() => {
    const today = new Date();
    let startDate, endDate;

    switch (dateRange) {
      case 'today':
        startDate = endDate = today.toISOString().split('T')[0];
        break;
      case 'last_7_days':
        endDate = today.toISOString().split('T')[0];
        startDate = new Date(today - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        break;
      case 'last_30_days':
        endDate = today.toISOString().split('T')[0];
        startDate = new Date(today - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        break;
      case 'this_month':
        endDate = today.toISOString().split('T')[0];
        startDate = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
        break;
      case 'custom':
        startDate = customStartDate;
        endDate = customEndDate;
        break;
      default:
        endDate = today.toISOString().split('T')[0];
        startDate = new Date(today - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    }

    return { startDate, endDate };
  }, [dateRange, customStartDate, customEndDate]);

  // Fetch daily summary
  const fetchDailySummary = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/dialer/analytics/daily-summary`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setDailySummary(data);
      }
    } catch (err) {
      console.error('Error fetching daily summary:', err);
    }
  }, [API_BASE_URL]);

  // Fetch performance metrics
  const fetchPerformance = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/dialer/analytics/performance?date_range=${dateRange}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setPerformance(data);
      }
    } catch (err) {
      console.error('Error fetching performance:', err);
    }
  }, [API_BASE_URL, dateRange]);

  // Fetch disposition breakdown
  const fetchDispositionBreakdown = useCallback(async () => {
    try {
      const { startDate, endDate } = getDateRangeParams();
      if (!startDate || !endDate) return;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/dialer/analytics/disposition-breakdown?start_date=${startDate}&end_date=${endDate}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setDispositionBreakdown(data);
      }
    } catch (err) {
      console.error('Error fetching disposition breakdown:', err);
    }
  }, [API_BASE_URL, getDateRangeParams]);

  // Fetch hourly stats
  const fetchHourlyStats = useCallback(async () => {
    try {
      const { startDate, endDate } = getDateRangeParams();
      if (!startDate || !endDate) return;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/dialer/analytics/connect-rate-by-hour?start_date=${startDate}&end_date=${endDate}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setHourlyStats(data);
      }
    } catch (err) {
      console.error('Error fetching hourly stats:', err);
    }
  }, [API_BASE_URL, getDateRangeParams]);

  // Fetch session analytics
  const fetchSessionStats = useCallback(async () => {
    try {
      const { startDate, endDate } = getDateRangeParams();
      if (!startDate || !endDate) return;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/dialer/analytics/sessions?start_date=${startDate}&end_date=${endDate}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSessionStats(data);
      }
    } catch (err) {
      console.error('Error fetching session stats:', err);
    }
  }, [API_BASE_URL, getDateRangeParams]);

  // Fetch all data
  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([
        fetchDailySummary(),
        fetchPerformance(),
        fetchDispositionBreakdown(),
        fetchHourlyStats(),
        fetchSessionStats()
      ]);
    } catch (err) {
      setError('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  }, [fetchDailySummary, fetchPerformance, fetchDispositionBreakdown, fetchHourlyStats, fetchSessionStats]);

  // Initial load and refresh on date range change
  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Format duration
  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Format percentage
  const formatPercent = (value) => {
    if (value === undefined || value === null) return '0%';
    return `${Math.round(value * 100)}%`;
  };

  // Get disposition color
  const getDispositionColor = (disposition) => {
    const colors = {
      'connected': '#22c55e',
      'live_answer': '#22c55e',
      'voicemail': '#f59e0b',
      'left_vm': '#f59e0b',
      'no_answer': '#ef4444',
      'busy': '#ef4444',
      'bad_number': '#6b7280',
      'callback': '#3b82f6',
      'default': '#94a3b8'
    };
    return colors[disposition?.toLowerCase()] || colors.default;
  };

  // Get max value for bar chart scaling
  const getMaxHourlyValue = () => {
    if (!hourlyStats?.hourly_stats) return 1;
    return Math.max(...hourlyStats.hourly_stats.map(h => h.total_calls), 1);
  };

  if (loading) {
    return (
      <div className="ca-dashboard">
        <div className="ca-loading">
          <div className="ca-spinner"></div>
          <p>Loading analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ca-dashboard">
      {/* Header */}
      <div className="ca-header">
        <div className="ca-header-left">
          <h1>Call Analytics</h1>
          <p className="ca-subtitle">Track your calling performance and optimize outreach</p>
        </div>
        <div className="ca-header-right">
          <select
            className="ca-date-select"
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
          >
            <option value="today">Today</option>
            <option value="last_7_days">Last 7 Days</option>
            <option value="last_30_days">Last 30 Days</option>
            <option value="this_month">This Month</option>
            <option value="custom">Custom Range</option>
          </select>
          {dateRange === 'custom' && (
            <div className="ca-custom-dates">
              <input
                type="date"
                value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
              />
              <span>to</span>
              <input
                type="date"
                value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
              />
              <button className="ca-btn ca-btn-primary" onClick={fetchAllData}>Apply</button>
            </div>
          )}
          <button className="ca-btn ca-btn-secondary" onClick={fetchAllData}>
            Refresh
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="ca-error-banner">
          <span>{error}</span>
          <button onClick={fetchAllData}>Retry</button>
        </div>
      )}

      {/* Today's Summary Cards */}
      <div className="ca-section">
        <h2>Today's Summary</h2>
        <div className="ca-stats-grid">
          <div className="ca-stat-card">
            <div className="ca-stat-icon">📞</div>
            <div className="ca-stat-content">
              <span className="ca-stat-value">{dailySummary?.total_calls || 0}</span>
              <span className="ca-stat-label">Total Calls</span>
            </div>
          </div>
          <div className="ca-stat-card">
            <div className="ca-stat-icon">✅</div>
            <div className="ca-stat-content">
              <span className="ca-stat-value">{dailySummary?.connected_calls || 0}</span>
              <span className="ca-stat-label">Connected</span>
            </div>
          </div>
          <div className="ca-stat-card highlight">
            <div className="ca-stat-icon">📊</div>
            <div className="ca-stat-content">
              <span className="ca-stat-value">{formatPercent(dailySummary?.connect_rate)}</span>
              <span className="ca-stat-label">Connect Rate</span>
            </div>
          </div>
          <div className="ca-stat-card">
            <div className="ca-stat-icon">⏱️</div>
            <div className="ca-stat-content">
              <span className="ca-stat-value">{dailySummary?.total_talk_time_minutes || 0}m</span>
              <span className="ca-stat-label">Talk Time</span>
            </div>
          </div>
          <div className="ca-stat-card">
            <div className="ca-stat-icon">⏳</div>
            <div className="ca-stat-content">
              <span className="ca-stat-value">{formatDuration(dailySummary?.average_call_duration_seconds)}</span>
              <span className="ca-stat-label">Avg Duration</span>
            </div>
          </div>
        </div>
      </div>

      {/* Performance Overview */}
      <div className="ca-section">
        <h2>Performance Overview ({dateRange.replace('_', ' ')})</h2>
        <div className="ca-performance-grid">
          <div className="ca-performance-card">
            <h3>Summary Metrics</h3>
            <div className="ca-metrics-list">
              <div className="ca-metric-row">
                <span className="ca-metric-label">Total Calls</span>
                <span className="ca-metric-value">{performance?.summary?.total_calls || 0}</span>
              </div>
              <div className="ca-metric-row">
                <span className="ca-metric-label">Connected Calls</span>
                <span className="ca-metric-value">{performance?.summary?.connected_calls || 0}</span>
              </div>
              <div className="ca-metric-row">
                <span className="ca-metric-label">Connect Rate</span>
                <span className="ca-metric-value highlight">{formatPercent(performance?.summary?.connect_rate)}</span>
              </div>
              <div className="ca-metric-row">
                <span className="ca-metric-label">Total Talk Time</span>
                <span className="ca-metric-value">{performance?.summary?.total_talk_time_minutes || 0} min</span>
              </div>
              <div className="ca-metric-row">
                <span className="ca-metric-label">Avg Duration</span>
                <span className="ca-metric-value">{formatDuration(performance?.summary?.average_call_duration_seconds)}</span>
              </div>
              <div className="ca-metric-row">
                <span className="ca-metric-label">Avg Calls/Day</span>
                <span className="ca-metric-value">{performance?.summary?.average_calls_per_day || 0}</span>
              </div>
            </div>
          </div>

          {/* Daily Trend */}
          <div className="ca-performance-card ca-trend-card">
            <h3>Daily Call Trend</h3>
            <div className="ca-trend-chart">
              {performance?.daily_trend?.map((day, idx) => (
                <div key={idx} className="ca-trend-bar-container">
                  <div
                    className="ca-trend-bar"
                    style={{
                      height: `${Math.max((day.calls / Math.max(...performance.daily_trend.map(d => d.calls), 1)) * 100, 5)}%`
                    }}
                    title={`${day.date}: ${day.calls} calls`}
                  >
                    <span className="ca-trend-value">{day.calls}</span>
                  </div>
                  <span className="ca-trend-label">{new Date(day.date).toLocaleDateString('en-US', { weekday: 'short' })}</span>
                </div>
              ))}
              {(!performance?.daily_trend || performance.daily_trend.length === 0) && (
                <p className="ca-empty">No call data for this period</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Disposition & Hourly Analysis */}
      <div className="ca-section ca-two-column">
        {/* Disposition Breakdown */}
        <div className="ca-card">
          <h3>Disposition Breakdown</h3>
          <div className="ca-disposition-list">
            {dispositionBreakdown?.breakdown?.map((item, idx) => (
              <div key={idx} className="ca-disposition-item">
                <div className="ca-disposition-info">
                  <span
                    className="ca-disposition-dot"
                    style={{ backgroundColor: getDispositionColor(item.disposition) }}
                  ></span>
                  <span className="ca-disposition-name">{item.disposition || 'Unknown'}</span>
                </div>
                <div className="ca-disposition-stats">
                  <span className="ca-disposition-count">{item.count}</span>
                  <span className="ca-disposition-pct">{item.percentage}%</span>
                </div>
                <div className="ca-disposition-bar-bg">
                  <div
                    className="ca-disposition-bar"
                    style={{
                      width: `${item.percentage}%`,
                      backgroundColor: getDispositionColor(item.disposition)
                    }}
                  ></div>
                </div>
              </div>
            ))}
            {(!dispositionBreakdown?.breakdown || dispositionBreakdown.breakdown.length === 0) && (
              <p className="ca-empty">No disposition data available</p>
            )}
          </div>
        </div>

        {/* Hourly Connect Rate */}
        <div className="ca-card">
          <h3>Connect Rate by Hour</h3>
          {hourlyStats?.best_hours?.length > 0 && (
            <div className="ca-best-hours">
              <span className="ca-best-hours-label">Best times to call:</span>
              {hourlyStats.best_hours.map((h, idx) => (
                <span key={idx} className="ca-best-hour-badge">
                  {h.hour_label} ({formatPercent(h.connect_rate)})
                </span>
              ))}
            </div>
          )}
          <div className="ca-hourly-chart">
            {hourlyStats?.hourly_stats?.filter(h => h.hour >= 8 && h.hour <= 20).map((hour, idx) => (
              <div key={idx} className="ca-hourly-bar-container">
                <div
                  className="ca-hourly-bar"
                  style={{
                    height: `${Math.max((hour.total_calls / getMaxHourlyValue()) * 100, 2)}%`,
                    opacity: hour.total_calls > 0 ? 1 : 0.3
                  }}
                  title={`${hour.hour_label}: ${hour.total_calls} calls, ${formatPercent(hour.connect_rate)} connect rate`}
                >
                  {hour.total_calls > 0 && (
                    <span className="ca-hourly-rate">{formatPercent(hour.connect_rate)}</span>
                  )}
                </div>
                <span className="ca-hourly-label">{hour.hour}:00</span>
              </div>
            ))}
            {(!hourlyStats?.hourly_stats) && (
              <p className="ca-empty">No hourly data available</p>
            )}
          </div>
        </div>
      </div>

      {/* Session Analytics */}
      <div className="ca-section">
        <h2>Session Analytics</h2>
        <div className="ca-session-summary">
          <div className="ca-session-stat">
            <span className="ca-session-value">{sessionStats?.summary?.total_sessions || 0}</span>
            <span className="ca-session-label">Total Sessions</span>
          </div>
          <div className="ca-session-stat">
            <span className="ca-session-value">{sessionStats?.summary?.total_tasks || 0}</span>
            <span className="ca-session-label">Total Tasks</span>
          </div>
          <div className="ca-session-stat">
            <span className="ca-session-value">{sessionStats?.summary?.total_completed || 0}</span>
            <span className="ca-session-label">Completed</span>
          </div>
          <div className="ca-session-stat highlight">
            <span className="ca-session-value">{formatPercent(sessionStats?.summary?.overall_completion_rate)}</span>
            <span className="ca-session-label">Completion Rate</span>
          </div>
          <div className="ca-session-stat">
            <span className="ca-session-value">{sessionStats?.summary?.avg_session_duration_minutes || 0}m</span>
            <span className="ca-session-label">Avg Session Duration</span>
          </div>
        </div>

        {/* Recent Sessions Table */}
        {sessionStats?.sessions?.length > 0 && (
          <div className="ca-sessions-table-container">
            <table className="ca-sessions-table">
              <thead>
                <tr>
                  <th>Session ID</th>
                  <th>Started</th>
                  <th>Status</th>
                  <th>Tasks</th>
                  <th>Completed</th>
                  <th>Completion Rate</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {sessionStats.sessions.slice(0, 10).map((session, idx) => (
                  <tr key={idx}>
                    <td className="ca-session-id">{session.session_id?.slice(0, 8)}...</td>
                    <td>{session.started_at ? new Date(session.started_at).toLocaleString() : '-'}</td>
                    <td>
                      <span className={`ca-status-badge ${session.status}`}>
                        {session.status}
                      </span>
                    </td>
                    <td>{session.total_tasks}</td>
                    <td>{session.completed_tasks}</td>
                    <td>{formatPercent(session.completion_rate)}</td>
                    <td>{session.duration_minutes}m</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default CallAnalyticsDashboard;
