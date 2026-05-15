import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './ManagerDashboard.css';

const ManagerDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [days, setDays] = useState(30);
  const [leaderboardMetric, setLeaderboardMetric] = useState('engagement_score');

  useEffect(() => {
    loadDashboard();
  }, [days]);

  useEffect(() => {
    loadLeaderboard();
  }, [days, leaderboardMetric]);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.get(
        `/api/v1/meetings/analytics/manager/dashboard?days=${days}`
      );
      setDashboardData(response.data);
      setLoading(false);
    } catch (err) {
      console.error('Error loading manager dashboard:', err);
      setError('Failed to load dashboard data');
      setLoading(false);
    }
  };

  const loadLeaderboard = async () => {
    try {
      const response = await axios.get(
        `/api/v1/meetings/analytics/manager/leaderboard?days=${days}&metric=${leaderboardMetric}`
      );
      setLeaderboard(response.data.leaderboard || []);
    } catch (err) {
      console.error('Error loading leaderboard:', err);
    }
  };

  const loadUserComparison = async (userId) => {
    try {
      setSelectedUser(userId);
      const response = await axios.get(
        `/api/v1/meetings/analytics/manager/compare/${userId}?days=${days}`
      );
      setComparison(response.data);
    } catch (err) {
      console.error('Error loading user comparison:', err);
      setComparison(null);
    }
  };

  const formatMetricName = (metric) => {
    const names = {
      engagement_score: 'Engagement',
      question_count: 'Questions',
      positive_sentiment: 'Positivity',
      talk_listen_ratio: 'Talk Ratio'
    };
    return names[metric] || metric;
  };

  const formatPercentage = (value) => {
    return `${(value * 100).toFixed(0)}%`;
  };

  const formatDelta = (value) => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${(value * 100).toFixed(1)}%`;
  };

  const getScoreColor = (score) => {
    if (score >= 0.8) return '#2D7A52';
    if (score >= 0.6) return '#3b82f6';
    if (score >= 0.4) return '#f59e0b';
    return '#ef4444';
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high':
      case 'critical': return '#ef4444';
      case 'medium': return '#f59e0b';
      default: return '#2D7A52';
    }
  };

  if (loading) {
    return (
      <div className="manager-dashboard-loading">
        <div className="loading-spinner"></div>
        <p>Loading manager dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="manager-dashboard-error">
        <p>{error}</p>
        <button onClick={loadDashboard} className="retry-button">
          Retry
        </button>
      </div>
    );
  }

  if (!dashboardData) {
    return (
      <div className="manager-dashboard-empty">
        <h3>No Data Available</h3>
        <p>No team analytics data available for the selected period.</p>
      </div>
    );
  }

  return (
    <div className="manager-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-title">
          <h2>Team Performance Dashboard</h2>
          <p className="subtitle">
            {dashboardData.team_size} team members • {dashboardData.total_recordings_analyzed} recordings analyzed
          </p>
        </div>
        <div className="header-controls">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="period-select"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab ${activeTab === 'performance' ? 'active' : ''}`}
          onClick={() => setActiveTab('performance')}
        >
          Performance
        </button>
        <button
          className={`tab ${activeTab === 'coaching' ? 'active' : ''}`}
          onClick={() => setActiveTab('coaching')}
        >
          Coaching
        </button>
        <button
          className={`tab ${activeTab === 'compliance' ? 'active' : ''}`}
          onClick={() => setActiveTab('compliance')}
        >
          Compliance
        </button>
        <button
          className={`tab ${activeTab === 'intelligence' ? 'active' : ''}`}
          onClick={() => setActiveTab('intelligence')}
        >
          Intelligence
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="tab-content">
          {/* Team Averages */}
          <div className="metrics-grid">
            <div className="metric-card">
              <span className="metric-label">Avg Engagement</span>
              <span
                className="metric-value"
                style={{ color: getScoreColor(dashboardData.team_averages?.engagement_score || 0) }}
              >
                {formatPercentage(dashboardData.team_averages?.engagement_score || 0)}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Avg Talk Ratio</span>
              <span className="metric-value">
                {formatPercentage(dashboardData.team_averages?.talk_listen_ratio || 0)}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Avg Questions/Call</span>
              <span className="metric-value">
                {(dashboardData.team_averages?.question_rate || 0).toFixed(1)}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Avg Positive Sentiment</span>
              <span className="metric-value" style={{ color: '#2D7A52' }}>
                {formatPercentage(dashboardData.team_averages?.positive_sentiment || 0)}
              </span>
            </div>
          </div>

          {/* Performance Distribution */}
          <div className="section-card">
            <h3>Performance Distribution</h3>
            <div className="distribution-chart">
              {Object.entries(dashboardData.performance_distribution || {}).map(([tier, count]) => (
                <div key={tier} className={`distribution-bar tier-${tier}`}>
                  <div className="bar-label">{tier.replace(/_/g, ' ')}</div>
                  <div className="bar-fill" style={{ width: `${Math.min(count * 20, 100)}%` }}>
                    {count}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Performers */}
          <div className="section-card">
            <h3>Top Performers</h3>
            <div className="performers-list">
              {dashboardData.top_performers?.map((performer, idx) => (
                <div
                  key={performer.user_id}
                  className="performer-item"
                  onClick={() => loadUserComparison(performer.user_id)}
                >
                  <div className="performer-rank">#{idx + 1}</div>
                  <div className="performer-info">
                    <span className="performer-name">User {performer.user_id}</span>
                    <span className="performer-recordings">
                      {performer.recordings_analyzed} recordings
                    </span>
                  </div>
                  <div className="performer-stats">
                    <span className="stat">
                      <strong>{formatPercentage(performer.avg_engagement)}</strong> engagement
                    </span>
                    <span className="stat">
                      <strong>{performer.avg_questions_per_call}</strong> questions/call
                    </span>
                  </div>
                </div>
              ))}
              {(!dashboardData.top_performers || dashboardData.top_performers.length === 0) && (
                <p className="no-data">No performance data available</p>
              )}
            </div>
          </div>

          {/* Best Practices */}
          {dashboardData.best_practices?.length > 0 && (
            <div className="section-card">
              <h3>Best Practices Identified</h3>
              <div className="best-practices-list">
                {dashboardData.best_practices.map((practice, idx) => (
                  <div key={idx} className="practice-item">
                    <div className="practice-header">
                      <span className="practice-title">{practice.practice}</span>
                      <span className="practice-metric">{practice.metric}</span>
                    </div>
                    <p className="practice-insight">{practice.insight}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Performance Tab */}
      {activeTab === 'performance' && (
        <div className="tab-content">
          {/* Leaderboard */}
          <div className="section-card">
            <div className="section-header-row">
              <h3>Team Leaderboard</h3>
              <select
                value={leaderboardMetric}
                onChange={(e) => setLeaderboardMetric(e.target.value)}
                className="metric-select"
              >
                <option value="engagement_score">Engagement</option>
                <option value="question_count">Questions</option>
                <option value="positive_sentiment">Sentiment</option>
                <option value="talk_listen_ratio">Talk Ratio</option>
              </select>
            </div>
            <div className="leaderboard">
              {leaderboard.map((entry) => (
                <div
                  key={entry.user_id}
                  className={`leaderboard-entry rank-${entry.rank}`}
                  onClick={() => loadUserComparison(entry.user_id)}
                >
                  <div className="entry-rank">
                    {entry.rank <= 3 ? (
                      <span className={`medal medal-${entry.rank}`}>
                        {entry.rank === 1 ? '🥇' : entry.rank === 2 ? '🥈' : '🥉'}
                      </span>
                    ) : (
                      <span className="rank-number">{entry.rank}</span>
                    )}
                  </div>
                  <div className="entry-info">
                    <span className="entry-name">User {entry.user_id}</span>
                    <span className="entry-recordings">
                      {entry.recordings_analyzed} recordings
                    </span>
                  </div>
                  <div className="entry-value">
                    {leaderboardMetric.includes('ratio') || leaderboardMetric.includes('score') || leaderboardMetric.includes('sentiment')
                      ? formatPercentage(entry.metric_value)
                      : entry.metric_value.toFixed(1)
                    }
                  </div>
                </div>
              ))}
              {leaderboard.length === 0 && (
                <p className="no-data">No leaderboard data available</p>
              )}
            </div>
          </div>

          {/* User Comparison Modal */}
          {comparison && (
            <div className="comparison-card">
              <div className="comparison-header">
                <h3>User {comparison.user_id} vs Team</h3>
                <button
                  className="close-button"
                  onClick={() => { setSelectedUser(null); setComparison(null); }}
                >
                  ×
                </button>
              </div>
              <p className="comparison-subtitle">
                Based on {comparison.recordings_analyzed} recordings over {comparison.period_days} days
              </p>
              <div className="comparison-metrics">
                {Object.entries(comparison.comparison || {}).map(([metric, data]) => (
                  <div key={metric} className="comparison-metric">
                    <div className="metric-name">{formatMetricName(metric)}</div>
                    <div className="metric-bars">
                      <div className="bar-row">
                        <span className="bar-label">Individual</span>
                        <div className="bar-container">
                          <div
                            className="bar individual"
                            style={{ width: `${Math.min(data.individual * 100, 100)}%` }}
                          ></div>
                        </div>
                        <span className="bar-value">{formatPercentage(data.individual)}</span>
                      </div>
                      <div className="bar-row">
                        <span className="bar-label">Team Avg</span>
                        <div className="bar-container">
                          <div
                            className="bar team"
                            style={{ width: `${Math.min(data.team_average * 100, 100)}%` }}
                          ></div>
                        </div>
                        <span className="bar-value">{formatPercentage(data.team_average)}</span>
                      </div>
                    </div>
                    <div className={`delta ${data.delta >= 0 ? 'positive' : 'negative'}`}>
                      {formatDelta(data.delta)}
                      <span className="percentile">({data.percentile}th percentile)</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Coaching Tab */}
      {activeTab === 'coaching' && (
        <div className="tab-content">
          <div className="section-card">
            <h3>Team Coaching Priorities</h3>
            <div className="coaching-priorities">
              {dashboardData.coaching_priorities?.map((priority, idx) => (
                <div key={idx} className="priority-item">
                  <div className="priority-header">
                    <span className="priority-category">{priority.category.replace(/_/g, ' ')}</span>
                    <span
                      className="priority-badge"
                      style={{ backgroundColor: priority.high_priority_count > 0 ? '#ef4444' : '#f59e0b' }}
                    >
                      {priority.high_priority_count > 0 ? 'High Priority' : 'Medium Priority'}
                    </span>
                  </div>
                  <div className="priority-stats">
                    <span>{priority.team_members_affected} team members affected</span>
                    <span>{priority.high_priority_count} high priority</span>
                  </div>
                  {priority.example_recommendations?.length > 0 && (
                    <div className="priority-examples">
                      <h4>Example Recommendations:</h4>
                      <ul>
                        {priority.example_recommendations.map((rec, i) => (
                          <li key={i}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
              {(!dashboardData.coaching_priorities || dashboardData.coaching_priorities.length === 0) && (
                <div className="no-data-card">
                  <p>No coaching priorities identified. Great work!</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Compliance Tab */}
      {activeTab === 'compliance' && (
        <div className="tab-content">
          {/* Compliance Summary */}
          <div className="compliance-summary">
            <div className={`compliance-header ${dashboardData.compliance_summary?.high_severity > 0 ? 'has-issues' : 'clean'}`}>
              <div className="compliance-stat">
                <span className="stat-value">{dashboardData.compliance_summary?.total_risks || 0}</span>
                <span className="stat-label">Total Flags</span>
              </div>
              <div className="compliance-stat alert">
                <span className="stat-value">{dashboardData.compliance_summary?.high_severity || 0}</span>
                <span className="stat-label">High Severity</span>
              </div>
              <div className="compliance-stat">
                <span className="stat-value">{dashboardData.compliance_summary?.recordings_with_risks || 0}</span>
                <span className="stat-label">Recordings Affected</span>
              </div>
            </div>
          </div>

          {/* Risk Types Breakdown */}
          {dashboardData.compliance_summary?.risk_types && Object.keys(dashboardData.compliance_summary.risk_types).length > 0 && (
            <div className="section-card">
              <h3>Risk Type Breakdown</h3>
              <div className="risk-types">
                {Object.entries(dashboardData.compliance_summary.risk_types).map(([type, count]) => (
                  <div key={type} className="risk-type-item">
                    <span className="risk-type-name">{type.replace(/_/g, ' ')}</span>
                    <span className="risk-type-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Incidents */}
          {dashboardData.compliance_summary?.recent_high_severity_incidents?.length > 0 && (
            <div className="section-card incidents">
              <h3>Recent High Severity Incidents</h3>
              <div className="incidents-list">
                {dashboardData.compliance_summary.recent_high_severity_incidents.map((incident, idx) => (
                  <div key={idx} className="incident-item">
                    <div className="incident-header">
                      <span className="incident-type">{incident.risk_type.replace(/_/g, ' ')}</span>
                      <span className={`incident-severity severity-${incident.severity}`}>
                        {incident.severity}
                      </span>
                    </div>
                    <p className="incident-context">"{incident.context}"</p>
                    <span className="incident-recording">Recording #{incident.recording_id}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {dashboardData.compliance_summary?.total_risks === 0 && (
            <div className="section-card success">
              <div className="success-message">
                <span className="success-icon">✓</span>
                <h3>No Compliance Issues Detected</h3>
                <p>Your team is maintaining compliance standards. Keep up the great work!</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Intelligence Tab */}
      {activeTab === 'intelligence' && (
        <div className="tab-content">
          {/* Competitor Landscape */}
          <div className="section-card">
            <h3>Competitor Landscape</h3>
            <div className="competitor-summary">
              <div className="summary-stats">
                <span className="stat">
                  <strong>{dashboardData.competitor_landscape?.total_competitor_mentions || 0}</strong> total mentions
                </span>
                <span className="stat">
                  <strong>{dashboardData.competitor_landscape?.unique_competitors || 0}</strong> competitors
                </span>
              </div>
            </div>
            <div className="competitor-list">
              {dashboardData.competitor_landscape?.top_competitors?.map((comp, idx) => (
                <div key={comp.competitor} className="competitor-item">
                  <div className="competitor-rank">#{idx + 1}</div>
                  <div className="competitor-info">
                    <span className="competitor-name">{comp.competitor}</span>
                    <span className="competitor-mentions">{comp.total_mentions} mentions</span>
                  </div>
                  {comp.sample_contexts?.length > 0 && (
                    <div className="competitor-contexts">
                      {comp.sample_contexts.slice(0, 1).map((ctx, i) => (
                        <p key={i} className="context-snippet">"{ctx}"</p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {(!dashboardData.competitor_landscape?.top_competitors || dashboardData.competitor_landscape.top_competitors.length === 0) && (
                <p className="no-data">No competitor mentions detected</p>
              )}
            </div>
          </div>

          {/* Concern Trends */}
          <div className="section-card">
            <h3>Borrower Concern Trends</h3>
            <div className="concern-trends">
              <div className="total-concerns">
                <strong>{dashboardData.concern_trends?.total_concerns_detected || 0}</strong> total concerns detected
              </div>
              <div className="trending-concerns">
                {dashboardData.concern_trends?.trending_concerns?.map((concern, idx) => (
                  <div key={concern.concern_type} className="trend-item">
                    <div className="trend-header">
                      <span className="trend-type">{concern.concern_type.replace(/_/g, ' ')}</span>
                      <span className="trend-count">{concern.total_occurrences}</span>
                    </div>
                    <div className="severity-breakdown">
                      {concern.severity_breakdown?.high > 0 && (
                        <span className="severity high">{concern.severity_breakdown.high} high</span>
                      )}
                      {concern.severity_breakdown?.medium > 0 && (
                        <span className="severity medium">{concern.severity_breakdown.medium} medium</span>
                      )}
                      {concern.severity_breakdown?.low > 0 && (
                        <span className="severity low">{concern.severity_breakdown.low} low</span>
                      )}
                    </div>
                  </div>
                ))}
                {(!dashboardData.concern_trends?.trending_concerns || dashboardData.concern_trends.trending_concerns.length === 0) && (
                  <p className="no-data">No concern trends detected</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ManagerDashboard;
