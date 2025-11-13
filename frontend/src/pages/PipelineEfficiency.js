import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './PipelineEfficiency.css';

function PipelineEfficiency() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('30days'); // 7days, 30days, 90days, year

  // Mock data - in production this would come from API
  const [efficiencyData, setEfficiencyData] = useState({
    overallScore: 78,
    trend: 5.2,
    lastUpdated: new Date().toISOString(),

    // Stage metrics
    stageMetrics: [
      {
        name: 'Lead Generation',
        efficiency: 85,
        avgTime: '2.3 days',
        conversionRate: 42,
        bottlenecks: 1,
        volume: 45,
        trend: 8
      },
      {
        name: 'Pre-Qualification',
        efficiency: 72,
        avgTime: '4.1 days',
        conversionRate: 68,
        bottlenecks: 3,
        volume: 19,
        trend: -3
      },
      {
        name: 'Application',
        efficiency: 81,
        avgTime: '5.2 days',
        conversionRate: 78,
        bottlenecks: 2,
        volume: 13,
        trend: 12
      },
      {
        name: 'Processing',
        efficiency: 65,
        avgTime: '12.5 days',
        conversionRate: 85,
        bottlenecks: 5,
        volume: 10,
        trend: -8
      },
      {
        name: 'Underwriting',
        efficiency: 70,
        avgTime: '8.7 days',
        conversionRate: 92,
        bottlenecks: 4,
        volume: 8,
        trend: 2
      },
      {
        name: 'Clear to Close',
        efficiency: 88,
        avgTime: '3.2 days',
        conversionRate: 96,
        bottlenecks: 1,
        volume: 7,
        trend: 15
      },
      {
        name: 'Closing',
        efficiency: 92,
        avgTime: '1.8 days',
        conversionRate: 98,
        bottlenecks: 0,
        volume: 7,
        trend: 10
      }
    ],

    // Team performance
    teamMetrics: [
      {
        role: 'Loan Officers',
        efficiency: 82,
        activeLoans: 15,
        avgResponseTime: '2.3 hrs',
        taskCompletionRate: 89,
        trend: 6
      },
      {
        role: 'Processors',
        efficiency: 68,
        activeLoans: 22,
        avgResponseTime: '5.1 hrs',
        taskCompletionRate: 72,
        trend: -4
      },
      {
        role: 'Underwriters',
        efficiency: 75,
        activeLoans: 18,
        avgResponseTime: '4.2 hrs',
        taskCompletionRate: 81,
        trend: 3
      },
      {
        role: 'Closers',
        efficiency: 91,
        activeLoans: 8,
        avgResponseTime: '1.5 hrs',
        taskCompletionRate: 95,
        trend: 12
      }
    ],

    // Active bottlenecks
    bottlenecks: [
      {
        id: 1,
        stage: 'Processing',
        issue: 'Missing Documents',
        affectedLoans: 8,
        avgDelay: '4.5 days',
        severity: 'high',
        suggestedAction: 'Send automated document reminder emails'
      },
      {
        id: 2,
        stage: 'Pre-Qualification',
        issue: 'Income Verification Delays',
        affectedLoans: 6,
        avgDelay: '3.2 days',
        severity: 'high',
        suggestedAction: 'Follow up with employers directly'
      },
      {
        id: 3,
        stage: 'Underwriting',
        issue: 'Appraisal Review Backlog',
        affectedLoans: 5,
        avgDelay: '2.8 days',
        severity: 'medium',
        suggestedAction: 'Escalate to senior underwriters'
      },
      {
        id: 4,
        stage: 'Processing',
        issue: 'Credit Report Disputes',
        affectedLoans: 4,
        avgDelay: '5.1 days',
        severity: 'medium',
        suggestedAction: 'Expedite credit bureau responses'
      },
      {
        id: 5,
        stage: 'Application',
        issue: 'Incomplete Applications',
        affectedLoans: 7,
        avgDelay: '2.1 days',
        severity: 'low',
        suggestedAction: 'Improve application form validation'
      },
      {
        id: 6,
        stage: 'Underwriting',
        issue: 'Title Search Delays',
        affectedLoans: 3,
        avgDelay: '3.5 days',
        severity: 'low',
        suggestedAction: 'Switch to faster title company'
      }
    ],

    // Key metrics
    keyMetrics: {
      avgTimeToClose: 35.2,
      avgTimeToCloseChange: -2.3,
      pullThroughRate: 68,
      pullThroughRateChange: 4.1,
      loansFallingBehind: 12,
      loansFallingBehindChange: -3,
      automationRate: 42,
      automationRateChange: 8.5
    },

    // Performance trends (last 12 weeks)
    trends: [
      { week: 'Week 1', score: 65, volume: 32 },
      { week: 'Week 2', score: 67, volume: 35 },
      { week: 'Week 3', score: 69, volume: 38 },
      { week: 'Week 4', score: 71, volume: 36 },
      { week: 'Week 5', score: 68, volume: 34 },
      { week: 'Week 6', score: 72, volume: 40 },
      { week: 'Week 7', score: 74, volume: 42 },
      { week: 'Week 8', score: 73, volume: 39 },
      { week: 'Week 9', score: 75, volume: 43 },
      { week: 'Week 10', score: 76, volume: 45 },
      { week: 'Week 11', score: 77, volume: 44 },
      { week: 'Week 12', score: 78, volume: 45 }
    ]
  });

  useEffect(() => {
    loadEfficiencyData();
  }, [timeRange]);

  const loadEfficiencyData = () => {
    setLoading(true);
    // Simulate API call
    setTimeout(() => {
      setLoading(false);
    }, 500);
  };

  const getStatusColor = (efficiency) => {
    if (efficiency >= 80) return 'high';
    if (efficiency >= 60) return 'medium';
    return 'low';
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'high': return '🔴';
      case 'medium': return '🟡';
      case 'low': return '🟢';
      default: return '⚪';
    }
  };

  if (loading) {
    return (
      <div className="efficiency-page">
        <div className="loading-spinner">Loading efficiency data...</div>
      </div>
    );
  }

  return (
    <div className="efficiency-page">
      {/* Header */}
      <div className="efficiency-header">
        <div className="header-left">
          <button className="btn-back" onClick={() => navigate('/dashboard')}>
            ← Back to Dashboard
          </button>
          <h1>Pipeline Efficiency Report</h1>
          <p className="last-updated">Last updated: {new Date(efficiencyData.lastUpdated).toLocaleString()}</p>
        </div>
        <div className="header-right">
          <select
            className="time-range-selector"
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
          >
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="90days">Last 90 Days</option>
            <option value="year">Last Year</option>
          </select>
          <button className="btn-export">Export Report</button>
        </div>
      </div>

      {/* Overall Score Card */}
      <div className="efficiency-score-card">
        <div className="score-display">
          <div className="score-number-large">{efficiencyData.overallScore}</div>
          <div className="score-label-large">Overall Pipeline Efficiency</div>
          <div className={`score-trend-large ${efficiencyData.trend >= 0 ? 'up' : 'down'}`}>
            {efficiencyData.trend >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.trend)}% vs. last period
          </div>
        </div>

        {/* Key Metrics Row */}
        <div className="key-metrics-grid">
          <div className="metric-card">
            <div className="metric-label">Avg. Time to Close</div>
            <div className="metric-value">{efficiencyData.keyMetrics.avgTimeToClose} days</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.avgTimeToCloseChange < 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.avgTimeToCloseChange < 0 ? '↓' : '↑'} {Math.abs(efficiencyData.keyMetrics.avgTimeToCloseChange)} days
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Pull-Through Rate</div>
            <div className="metric-value">{efficiencyData.keyMetrics.pullThroughRate}%</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.pullThroughRateChange >= 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.pullThroughRateChange >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.keyMetrics.pullThroughRateChange)}%
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Loans Falling Behind</div>
            <div className="metric-value">{efficiencyData.keyMetrics.loansFallingBehind}</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.loansFallingBehindChange < 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.loansFallingBehindChange < 0 ? '↓' : '↑'} {Math.abs(efficiencyData.keyMetrics.loansFallingBehindChange)}
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Automation Rate</div>
            <div className="metric-value">{efficiencyData.keyMetrics.automationRate}%</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.automationRateChange >= 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.automationRateChange >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.keyMetrics.automationRateChange)}%
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="efficiency-content-grid">

        {/* Stage Performance Section */}
        <div className="efficiency-section stage-performance">
          <h2>Stage Performance Analysis</h2>
          <div className="stage-table">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Efficiency</th>
                  <th>Avg. Time</th>
                  <th>Conv. Rate</th>
                  <th>Volume</th>
                  <th>Bottlenecks</th>
                  <th>Trend</th>
                </tr>
              </thead>
              <tbody>
                {efficiencyData.stageMetrics.map((stage, idx) => (
                  <tr key={idx}>
                    <td className="stage-name">{stage.name}</td>
                    <td>
                      <div className="efficiency-cell">
                        <div className={`efficiency-badge ${getStatusColor(stage.efficiency)}`}>
                          {stage.efficiency}%
                        </div>
                      </div>
                    </td>
                    <td>{stage.avgTime}</td>
                    <td>{stage.conversionRate}%</td>
                    <td>{stage.volume}</td>
                    <td>
                      <span className={`bottleneck-count ${stage.bottlenecks > 0 ? 'has-issues' : 'no-issues'}`}>
                        {stage.bottlenecks}
                      </span>
                    </td>
                    <td>
                      <span className={`trend-indicator ${stage.trend >= 0 ? 'positive' : 'negative'}`}>
                        {stage.trend >= 0 ? '↑' : '↓'} {Math.abs(stage.trend)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Team Performance Section */}
        <div className="efficiency-section team-performance">
          <h2>Team Performance Metrics</h2>
          <div className="team-cards">
            {efficiencyData.teamMetrics.map((member, idx) => (
              <div key={idx} className="team-performance-card">
                <div className="team-card-header">
                  <h3>{member.role}</h3>
                  <div className={`efficiency-score ${getStatusColor(member.efficiency)}`}>
                    {member.efficiency}%
                  </div>
                </div>
                <div className="team-card-metrics">
                  <div className="team-metric">
                    <span className="team-metric-label">Active Loans:</span>
                    <span className="team-metric-value">{member.activeLoans}</span>
                  </div>
                  <div className="team-metric">
                    <span className="team-metric-label">Avg Response:</span>
                    <span className="team-metric-value">{member.avgResponseTime}</span>
                  </div>
                  <div className="team-metric">
                    <span className="team-metric-label">Task Completion:</span>
                    <span className="team-metric-value">{member.taskCompletionRate}%</span>
                  </div>
                </div>
                <div className={`team-trend ${member.trend >= 0 ? 'positive' : 'negative'}`}>
                  {member.trend >= 0 ? '↑' : '↓'} {Math.abs(member.trend)}% vs. last period
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottlenecks Section */}
        <div className="efficiency-section bottlenecks-section">
          <h2>Active Bottlenecks & Recommendations</h2>
          <div className="bottlenecks-list">
            {efficiencyData.bottlenecks.map((bottleneck) => (
              <div key={bottleneck.id} className={`bottleneck-card severity-${bottleneck.severity}`}>
                <div className="bottleneck-header">
                  <div className="bottleneck-title">
                    <span className="severity-icon">{getSeverityIcon(bottleneck.severity)}</span>
                    <h3>{bottleneck.issue}</h3>
                  </div>
                  <div className="bottleneck-stage">{bottleneck.stage}</div>
                </div>
                <div className="bottleneck-details">
                  <div className="bottleneck-stat">
                    <span className="stat-label">Affected Loans:</span>
                    <span className="stat-value">{bottleneck.affectedLoans}</span>
                  </div>
                  <div className="bottleneck-stat">
                    <span className="stat-label">Avg. Delay:</span>
                    <span className="stat-value">{bottleneck.avgDelay}</span>
                  </div>
                </div>
                <div className="bottleneck-action">
                  <strong>Suggested Action:</strong> {bottleneck.suggestedAction}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Performance Trends Chart */}
        <div className="efficiency-section trends-section">
          <h2>Efficiency Trends (Last 12 Weeks)</h2>
          <div className="trends-chart">
            <div className="chart-container">
              {efficiencyData.trends.map((trend, idx) => (
                <div key={idx} className="chart-bar-group">
                  <div className="chart-bars">
                    <div
                      className="chart-bar score-bar"
                      style={{ height: `${trend.score}%` }}
                      title={`Efficiency: ${trend.score}%`}
                    ></div>
                    <div
                      className="chart-bar volume-bar"
                      style={{ height: `${(trend.volume / 50) * 100}%` }}
                      title={`Volume: ${trend.volume}`}
                    ></div>
                  </div>
                  <div className="chart-label">{trend.week.replace('Week ', 'W')}</div>
                </div>
              ))}
            </div>
            <div className="chart-legend">
              <div className="legend-item">
                <div className="legend-color score-color"></div>
                <span>Efficiency Score</span>
              </div>
              <div className="legend-item">
                <div className="legend-color volume-color"></div>
                <span>Loan Volume</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

export default PipelineEfficiency;
