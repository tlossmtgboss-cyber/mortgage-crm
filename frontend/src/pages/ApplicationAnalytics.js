import React, { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  FunnelChart, Funnel, LabelList
} from 'recharts';
import { getAuthHeaders } from '../utils/auth';
import './ApplicationAnalytics.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const COLORS = ['#1F3D2E', '#2D7A52', '#3b82f6', '#B8924A', '#f59e0b', '#ef4444'];

export default function ApplicationAnalytics() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [loId, setLoId] = useState(null);

  // Analytics data
  const [overview, setOverview] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [dailyTrend, setDailyTrend] = useState(null);
  const [bySource, setBySource] = useState(null);
  const [byDevice, setByDevice] = useState(null);
  const [loPerformance, setLoPerformance] = useState(null);
  const [dropOff, setDropOff] = useState(null);

  // Fetch all analytics data
  const fetchAnalytics = async () => {
    setLoading(true);
    setError(null);

    const headers = getAuthHeaders();
    const params = new URLSearchParams({ days: days.toString() });
    if (loId) params.append('lo_id', loId.toString());

    try {
      const endpoints = [
        'overview',
        'funnel',
        'daily-trend',
        'by-source',
        'device-breakdown',
        'lo-performance',
        'drop-off-analysis',
      ];

      const responses = await Promise.all(
        endpoints.map(endpoint =>
          fetch(`${API_BASE_URL}/api/v1/analytics/applications/${endpoint}?${params}`, { headers })
            .then(res => res.ok ? res.json() : null)
            .catch(() => null)
        )
      );

      const [overviewData, funnelData, trendData, sourceData, deviceData, loData, dropOffData] = responses;

      setOverview(overviewData);
      setFunnel(funnelData);
      setDailyTrend(trendData);
      setBySource(sourceData);
      setByDevice(deviceData);
      setLoPerformance(loData);
      setDropOff(dropOffData);

    } catch (err) {
      console.error('Failed to fetch analytics:', err);
      setError('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [days, loId]);

  // Format numbers
  const formatNumber = (num) => {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString();
  };

  const formatPercent = (num) => {
    if (num === null || num === undefined) return '0%';
    return `${num.toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="analytics-loading">
        <div className="spinner"></div>
        <p>Loading analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-error">
        <span className="error-icon">!</span>
        <p>{error}</p>
        <button onClick={fetchAnalytics}>Retry</button>
      </div>
    );
  }

  return (
    <div className="application-analytics">
      {/* Header */}
      <div className="analytics-header">
        <div className="header-left">
          <h1>Application Analytics</h1>
          <p>Track borrower application performance and conversion metrics</p>
        </div>
        <div className="header-controls">
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button className="btn-refresh" onClick={fetchAnalytics}>
            Refresh
          </button>
        </div>
      </div>

      {/* Overview Cards */}
      {overview && (
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-value">{formatNumber(overview.metrics.total_applications)}</div>
            <div className="metric-label">Total Applications</div>
          </div>
          <div className="metric-card highlight">
            <div className="metric-value">{formatNumber(overview.metrics.submitted)}</div>
            <div className="metric-label">Submitted</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{formatNumber(overview.metrics.in_progress)}</div>
            <div className="metric-label">In Progress</div>
          </div>
          <div className="metric-card warning">
            <div className="metric-value">{formatNumber(overview.metrics.abandoned)}</div>
            <div className="metric-label">Abandoned</div>
          </div>
          <div className="metric-card success">
            <div className="metric-value">{formatPercent(overview.metrics.conversion_rate)}</div>
            <div className="metric-label">Conversion Rate</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{overview.metrics.avg_time_minutes.toFixed(0)}m</div>
            <div className="metric-label">Avg. Time to Complete</div>
          </div>
        </div>
      )}

      {/* Charts Row 1 */}
      <div className="charts-row">
        {/* Daily Trend */}
        <div className="chart-card wide">
          <h3>Application Trend</h3>
          {dailyTrend && dailyTrend.daily_data && (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={dailyTrend.daily_data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  stroke="#9ca3af"
                />
                <YAxis stroke="#9ca3af" />
                <Tooltip
                  labelFormatter={(val) => new Date(val).toLocaleDateString()}
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb' }}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="total"
                  name="Started"
                  stroke="#1F3D2E"
                  fill="#1F3D2E"
                  fillOpacity={0.2}
                />
                <Area
                  type="monotone"
                  dataKey="submitted"
                  name="Submitted"
                  stroke="#2D7A52"
                  fill="#2D7A52"
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Funnel */}
        <div className="chart-card">
          <h3>Conversion Funnel</h3>
          {funnel && funnel.funnel && (
            <div className="funnel-container">
              {funnel.funnel.map((step, index) => (
                <div key={step.step} className="funnel-step">
                  <div
                    className="funnel-bar"
                    style={{ width: `${step.rate}%`, backgroundColor: COLORS[index % COLORS.length] }}
                  >
                    <span className="funnel-label">{step.step}</span>
                    <span className="funnel-value">{step.count}</span>
                  </div>
                  <div className="funnel-rate">{formatPercent(step.rate)}</div>
                </div>
              ))}
              <div className="funnel-summary">
                Overall Conversion: <strong>{formatPercent(funnel.overall_conversion)}</strong>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="charts-row">
        {/* By Source */}
        <div className="chart-card">
          <h3>Applications by Source</h3>
          {bySource && bySource.by_source && (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={bySource.by_source}
                  dataKey="count"
                  nameKey="source"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ source, percent }) => `${source} (${(percent * 100).toFixed(0)}%)`}
                >
                  {bySource.by_source.map((entry, index) => (
                    <Cell key={entry.source} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value, name, props) => [
                    `${value} (${formatPercent(props.payload.conversion_rate)} conv.)`,
                    'Count'
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* By Device */}
        <div className="chart-card">
          <h3>Applications by Device</h3>
          {byDevice && byDevice.by_device && (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={byDevice.by_device} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" stroke="#9ca3af" />
                <YAxis type="category" dataKey="device" stroke="#9ca3af" width={80} />
                <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb' }} />
                <Bar dataKey="count" name="Applications" fill="#1F3D2E" radius={[0, 4, 4, 0]} />
                <Bar dataKey="submitted" name="Submitted" fill="#2D7A52" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Drop-off Analysis */}
        <div className="chart-card">
          <h3>Drop-off Analysis</h3>
          {dropOff && dropOff.drop_off_points && (
            <div className="drop-off-list">
              {dropOff.drop_off_points.map((point, index) => (
                <div key={point.step} className="drop-off-item">
                  <div className="drop-off-header">
                    <span className="step-name">{point.step}</span>
                    <span className="step-count">{point.count} ({formatPercent(point.percentage)})</span>
                  </div>
                  <div className="drop-off-bar">
                    <div
                      className="drop-off-fill"
                      style={{ width: `${point.percentage}%`, backgroundColor: COLORS[index % COLORS.length] }}
                    ></div>
                  </div>
                  <div className="drop-off-meta">
                    Avg. {point.avg_time_on_step.toFixed(0)} min on this step
                  </div>
                </div>
              ))}
              <div className="drop-off-total">
                Total Incomplete: <strong>{formatNumber(dropOff.total_incomplete)}</strong>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* LO Performance Table */}
      {loPerformance && loPerformance.by_lo && (
        <div className="chart-card full-width">
          <h3>Loan Officer Performance</h3>
          <table className="performance-table">
            <thead>
              <tr>
                <th>Loan Officer</th>
                <th>Total</th>
                <th>Submitted</th>
                <th>Conversion</th>
                <th>Avg Progress</th>
                <th>Avg Time (min)</th>
              </tr>
            </thead>
            <tbody>
              {loPerformance.by_lo.map((lo) => (
                <tr key={lo.lo_id || 'unassigned'}>
                  <td>{lo.lo_name}</td>
                  <td>{formatNumber(lo.total)}</td>
                  <td>{formatNumber(lo.submitted)}</td>
                  <td className={lo.conversion_rate >= 50 ? 'good' : lo.conversion_rate >= 25 ? 'ok' : 'poor'}>
                    {formatPercent(lo.conversion_rate)}
                  </td>
                  <td>{formatPercent(lo.avg_progress)}</td>
                  <td>{lo.avg_time_minutes.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
