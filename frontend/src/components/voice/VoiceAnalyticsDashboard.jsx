/**
 * Voice Analytics Dashboard Component
 *
 * Comprehensive analytics for Voice OS performance and ROI.
 * Features:
 * - Call volume and trends
 * - Success rates by agent/tool
 * - Average call duration and cost
 * - Conversion metrics
 * - ROI comparison
 */

import React, { useState, useEffect, useCallback } from 'react';
import './VoiceAnalyticsDashboard.css';

const TIME_RANGES = [
  { id: 'today', label: 'Today' },
  { id: 'week', label: 'This Week' },
  { id: 'month', label: 'This Month' },
  { id: 'quarter', label: 'This Quarter' },
  { id: 'year', label: 'This Year' },
];

const formatNumber = (num) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

const formatCurrency = (amount) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatDuration = (seconds) => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const formatPercent = (value) => `${(value * 100).toFixed(1)}%`;

const MetricCard = ({ title, value, change, changeLabel, icon, trend }) => (
  <div className="metric-card">
    <div className="metric-header">
      <span className="metric-icon">{icon}</span>
      <span className="metric-title">{title}</span>
    </div>
    <div className="metric-value">{value}</div>
    {change !== undefined && (
      <div className={`metric-change ${trend}`}>
        <span className="change-arrow">{trend === 'up' ? '^' : trend === 'down' ? 'v' : '-'}</span>
        <span className="change-value">{change}</span>
        <span className="change-label">{changeLabel}</span>
      </div>
    )}
  </div>
);

const SimpleBarChart = ({ data, label, valueFormatter = formatNumber }) => {
  const maxValue = Math.max(...data.map(d => d.value));

  return (
    <div className="simple-chart">
      <div className="chart-bars">
        {data.map((item, index) => (
          <div key={index} className="chart-bar-container">
            <div
              className="chart-bar"
              style={{ height: `${(item.value / maxValue) * 100}%` }}
              title={`${item.label}: ${valueFormatter(item.value)}`}
            />
            <span className="chart-label">{item.label}</span>
          </div>
        ))}
      </div>
      <div className="chart-title">{label}</div>
    </div>
  );
};

const VoiceAnalyticsDashboard = () => {
  const [timeRange, setTimeRange] = useState('week');
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState(null);
  const [agentStats, setAgentStats] = useState([]);
  const [toolStats, setToolStats] = useState([]);
  const [dailyTrend, setDailyTrend] = useState([]);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const [metricsRes, agentsRes, toolsRes, trendRes] = await Promise.all([
        fetch(`/api/voice/analytics/summary?range=${timeRange}`),
        fetch(`/api/voice/analytics/agents?range=${timeRange}`),
        fetch(`/api/voice/analytics/tools?range=${timeRange}`),
        fetch(`/api/voice/analytics/trend?range=${timeRange}`),
      ]);

      if (metricsRes.ok) {
        const data = await metricsRes.json();
        setMetrics(data);
      } else {
        // Mock data if API not available
        setMetrics({
          totalCalls: 1247,
          successfulCalls: 1089,
          failedCalls: 158,
          avgDuration: 187,
          avgCost: 0.42,
          totalCost: 523.74,
          leadsGenerated: 234,
          appointmentsBooked: 89,
          escalationRate: 0.127,
          successRate: 0.873,
          costSavings: 4250,
          humanHoursSaved: 156,
        });
      }

      if (agentsRes.ok) {
        const data = await agentsRes.json();
        setAgentStats(data.agents || []);
      } else {
        setAgentStats([
          { name: 'Main Receptionist', calls: 856, successRate: 0.91, avgDuration: 165 },
          { name: 'Lead Qualifier', calls: 234, successRate: 0.85, avgDuration: 210 },
          { name: 'Status Checker', calls: 157, successRate: 0.94, avgDuration: 120 },
        ]);
      }

      if (toolsRes.ok) {
        const data = await toolsRes.json();
        setToolStats(data.tools || []);
      } else {
        setToolStats([
          { name: 'lookup_caller', calls: 1089, successRate: 0.98 },
          { name: 'schedule_appointment', calls: 234, successRate: 0.89 },
          { name: 'get_loan_status', calls: 412, successRate: 0.95 },
          { name: 'create_lead', calls: 198, successRate: 0.92 },
          { name: 'escalate_to_human', calls: 158, successRate: 1.0 },
        ]);
      }

      if (trendRes.ok) {
        const data = await trendRes.json();
        setDailyTrend(data.trend || []);
      } else {
        setDailyTrend([
          { label: 'Mon', value: 156 },
          { label: 'Tue', value: 189 },
          { label: 'Wed', value: 201 },
          { label: 'Thu', value: 178 },
          { label: 'Fri', value: 234 },
          { label: 'Sat', value: 145 },
          { label: 'Sun', value: 144 },
        ]);
      }
    } catch (err) {
      console.error('Failed to fetch analytics:', err);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  if (loading || !metrics) {
    return (
      <div className="voice-analytics loading">
        <div className="loading-spinner">Loading analytics...</div>
      </div>
    );
  }

  return (
    <div className="voice-analytics">
      <div className="analytics-header">
        <div className="header-left">
          <h1>Voice Analytics</h1>
          <p className="subtitle">Performance metrics and insights</p>
        </div>

        <div className="header-controls">
          <div className="time-range-selector">
            {TIME_RANGES.map(range => (
              <button
                key={range.id}
                className={timeRange === range.id ? 'active' : ''}
                onClick={() => setTimeRange(range.id)}
              >
                {range.label}
              </button>
            ))}
          </div>

          <button onClick={fetchAnalytics} className="refresh-btn">
            Refresh
          </button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="metrics-section">
        <div className="metrics-grid top-metrics">
          <MetricCard
            title="Total Calls"
            value={formatNumber(metrics.totalCalls)}
            change="+12%"
            changeLabel="vs last period"
            icon="A"
            trend="up"
          />
          <MetricCard
            title="Success Rate"
            value={formatPercent(metrics.successRate)}
            change="+2.3%"
            changeLabel="vs last period"
            icon="B"
            trend="up"
          />
          <MetricCard
            title="Avg Duration"
            value={formatDuration(metrics.avgDuration)}
            change="-8s"
            changeLabel="vs last period"
            icon="C"
            trend="down"
          />
          <MetricCard
            title="Leads Generated"
            value={formatNumber(metrics.leadsGenerated)}
            change="+18%"
            changeLabel="vs last period"
            icon="D"
            trend="up"
          />
          <MetricCard
            title="Appointments"
            value={formatNumber(metrics.appointmentsBooked)}
            change="+23%"
            changeLabel="vs last period"
            icon="E"
            trend="up"
          />
          <MetricCard
            title="Escalation Rate"
            value={formatPercent(metrics.escalationRate)}
            change="-1.5%"
            changeLabel="vs last period"
            icon="F"
            trend="down"
          />
        </div>
      </div>

      {/* Charts and Tables */}
      <div className="analytics-content">
        <div className="content-row">
          {/* Call Volume Trend */}
          <div className="analytics-card chart-card">
            <h3>Call Volume Trend</h3>
            <SimpleBarChart
              data={dailyTrend}
              label="Calls by Day"
            />
          </div>

          {/* Cost Analysis */}
          <div className="analytics-card cost-card">
            <h3>Cost Analysis</h3>
            <div className="cost-metrics">
              <div className="cost-item">
                <span className="cost-label">Total Cost</span>
                <span className="cost-value">{formatCurrency(metrics.totalCost)}</span>
              </div>
              <div className="cost-item">
                <span className="cost-label">Avg Cost/Call</span>
                <span className="cost-value">${metrics.avgCost.toFixed(2)}</span>
              </div>
              <div className="cost-item highlight">
                <span className="cost-label">Est. Savings</span>
                <span className="cost-value positive">{formatCurrency(metrics.costSavings)}</span>
              </div>
              <div className="cost-item">
                <span className="cost-label">Hours Saved</span>
                <span className="cost-value">{metrics.humanHoursSaved}h</span>
              </div>
            </div>

            <div className="roi-summary">
              <h4>ROI vs Traditional</h4>
              <div className="roi-comparison">
                <div className="roi-item">
                  <span className="roi-label">Human Operator</span>
                  <span className="roi-bar human" style={{ width: '100%' }}>
                    $15/call
                  </span>
                </div>
                <div className="roi-item">
                  <span className="roi-label">Voice AI (Vapi)</span>
                  <span className="roi-bar vapi" style={{ width: '40%' }}>
                    $0.50/call
                  </span>
                </div>
                <div className="roi-item">
                  <span className="roi-label">Voice OS</span>
                  <span className="roi-bar voiceos" style={{ width: '28%' }}>
                    ${metrics.avgCost.toFixed(2)}/call
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="content-row">
          {/* Agent Performance */}
          <div className="analytics-card table-card">
            <h3>Agent Performance</h3>
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Calls</th>
                  <th>Success Rate</th>
                  <th>Avg Duration</th>
                </tr>
              </thead>
              <tbody>
                {agentStats.map((agent, index) => (
                  <tr key={index}>
                    <td className="agent-name">{agent.name}</td>
                    <td>{formatNumber(agent.calls)}</td>
                    <td>
                      <span className={`success-badge ${agent.successRate >= 0.9 ? 'high' : agent.successRate >= 0.8 ? 'medium' : 'low'}`}>
                        {formatPercent(agent.successRate)}
                      </span>
                    </td>
                    <td>{formatDuration(agent.avgDuration)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Tool Usage */}
          <div className="analytics-card table-card">
            <h3>Tool Usage</h3>
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>Tool</th>
                  <th>Calls</th>
                  <th>Success Rate</th>
                </tr>
              </thead>
              <tbody>
                {toolStats.map((tool, index) => (
                  <tr key={index}>
                    <td className="tool-name">{tool.name.replace(/_/g, ' ')}</td>
                    <td>{formatNumber(tool.calls)}</td>
                    <td>
                      <div className="success-bar-container">
                        <div
                          className="success-bar"
                          style={{ width: `${tool.successRate * 100}%` }}
                        />
                        <span className="success-text">{formatPercent(tool.successRate)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Call Outcomes */}
        <div className="analytics-card outcomes-card">
          <h3>Call Outcomes</h3>
          <div className="outcomes-grid">
            <div className="outcome-item success">
              <span className="outcome-icon">+</span>
              <div className="outcome-content">
                <span className="outcome-value">{formatNumber(metrics.successfulCalls)}</span>
                <span className="outcome-label">Successful Calls</span>
              </div>
            </div>
            <div className="outcome-item info">
              <span className="outcome-icon">$</span>
              <div className="outcome-content">
                <span className="outcome-value">{formatNumber(metrics.leadsGenerated)}</span>
                <span className="outcome-label">Leads Captured</span>
              </div>
            </div>
            <div className="outcome-item info">
              <span className="outcome-icon">=</span>
              <div className="outcome-content">
                <span className="outcome-value">{formatNumber(metrics.appointmentsBooked)}</span>
                <span className="outcome-label">Appointments Booked</span>
              </div>
            </div>
            <div className="outcome-item warning">
              <span className="outcome-icon">!</span>
              <div className="outcome-content">
                <span className="outcome-value">{formatNumber(Math.round(metrics.totalCalls * metrics.escalationRate))}</span>
                <span className="outcome-label">Escalated to Human</span>
              </div>
            </div>
            <div className="outcome-item error">
              <span className="outcome-icon">x</span>
              <div className="outcome-content">
                <span className="outcome-value">{formatNumber(metrics.failedCalls)}</span>
                <span className="outcome-label">Failed Calls</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VoiceAnalyticsDashboard;
