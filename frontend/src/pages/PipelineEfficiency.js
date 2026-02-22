import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './PipelineEfficiency.css';
import { toast } from '../utils/toast';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

function PipelineEfficiency() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('30days');
  const [efficiencyData, setEfficiencyData] = useState(null);
  const [stageMetrics, setStageMetrics] = useState([]);
  const [teamMetrics, setTeamMetrics] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [trends, setTrends] = useState([]);
  const [hasData, setHasData] = useState(false);

  useEffect(() => {
    loadAllData();
  }, [timeRange]);

  const loadAllData = async () => {
    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Fetch all data in parallel
      const [efficiencyRes, stagesRes, teamRes, bottlenecksRes, trendsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/pipeline/efficiency?time_range=${timeRange}`, { headers }),
        fetch(`${API_BASE}/api/v1/pipeline/stages?time_range=${timeRange}`, { headers }),
        fetch(`${API_BASE}/api/v1/pipeline/team?time_range=${timeRange}`, { headers }),
        fetch(`${API_BASE}/api/v1/pipeline/bottlenecks?time_range=${timeRange}`, { headers }),
        fetch(`${API_BASE}/api/v1/pipeline/trends?weeks=12`, { headers })
      ]);

      // Parse responses
      const efficiency = efficiencyRes.ok ? await efficiencyRes.json() : null;
      const stages = stagesRes.ok ? await stagesRes.json() : null;
      const team = teamRes.ok ? await teamRes.json() : null;
      const bottlenecksData = bottlenecksRes.ok ? await bottlenecksRes.json() : null;
      const trendsData = trendsRes.ok ? await trendsRes.json() : null;

      // Update state
      setEfficiencyData(efficiency);
      setStageMetrics(stages?.stageMetrics || []);
      setTeamMetrics(team?.teamMetrics || []);
      setBottlenecks(bottlenecksData?.bottlenecks || []);
      setTrends(trendsData?.trends || []);

      // Check if there's any data
      const dataExists = efficiency?.hasData ||
                        stages?.hasData ||
                        bottlenecksData?.hasData ||
                        trendsData?.hasData;
      setHasData(dataExists);

    } catch (err) {
      console.error('Failed to load pipeline efficiency data:', err);
      setError('Failed to load pipeline data. Please try again.');
    } finally {
      setLoading(false);
    }
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

  const handleStageClick = (stage) => {
    const stageSlug = stage.name.toLowerCase().replace(/\s+/g, '-');
    navigate(`/efficiency/stage/${stageSlug}`);
  };

  const handleTeamMemberClick = (member) => {
    const roleSlug = member.role.toLowerCase().replace(/\s+/g, '-');
    navigate(`/efficiency/team/${roleSlug}`);
  };

  const handleBottleneckClick = (bottleneck) => {
    navigate(`/efficiency/bottleneck/${bottleneck.id}`);
  };

  // Empty State Component
  const EmptyState = () => (
    <div className="empty-state-container">
      <div className="empty-state-icon">📊</div>
      <h2>No Pipeline Data Yet</h2>
      <p>Start adding leads and loans to see your pipeline efficiency metrics.</p>
      <div className="empty-state-actions">
        <button className="btn-primary" onClick={() => navigate('/leads')}>
          Add Your First Lead
        </button>
        <button className="btn-secondary" onClick={() => navigate('/loans')}>
          Add Your First Loan
        </button>
      </div>
      <div className="empty-state-tips">
        <h4>What you'll see here:</h4>
        <ul>
          <li>Overall pipeline efficiency score</li>
          <li>Stage-by-stage performance analysis</li>
          <li>Team performance metrics</li>
          <li>Active bottlenecks and recommendations</li>
          <li>Historical trends and patterns</li>
        </ul>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="efficiency-page">
        <div className="loading-spinner">Loading pipeline efficiency data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="efficiency-page">
        <div className="error-message">
          <p>{error}</p>
          <button onClick={loadAllData}>Try Again</button>
        </div>
      </div>
    );
  }

  // Show empty state if no data
  if (!hasData) {
    return (
      <div className="efficiency-page">
        <div className="efficiency-header">
          <div className="header-left">
            <button className="btn-back" onClick={() => navigate('/dashboard')}>
              ← Back to Dashboard
            </button>
            <h1>Pipeline Efficiency Report</h1>
          </div>
        </div>
        <EmptyState />
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
          <p className="last-updated">
            Last updated: {efficiencyData?.lastUpdated ? new Date(efficiencyData.lastUpdated).toLocaleString() : 'N/A'}
          </p>
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
          <button className="btn-export" onClick={() => toast.info('Export feature coming soon')}>
            Export Report
          </button>
        </div>
      </div>

      {/* Overall Score Card */}
      <div className="efficiency-score-card">
        <div className="score-display">
          <div className="score-number-large">{efficiencyData?.overallScore || 0}</div>
          <div className="score-label-large">Overall Pipeline Efficiency</div>
          {efficiencyData?.trend !== 0 && (
            <div className={`score-trend-large ${efficiencyData?.trend >= 0 ? 'up' : 'down'}`}>
              {efficiencyData?.trend >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData?.trend || 0)}% vs. last period
            </div>
          )}
        </div>

        {/* Key Metrics Row */}
        <div className="key-metrics-grid">
          <div className="metric-card">
            <div className="metric-label">Avg. Time to Close</div>
            <div className="metric-value">
              {efficiencyData?.keyMetrics?.avgTimeToClose || 0} days
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Pull-Through Rate</div>
            <div className="metric-value">
              {efficiencyData?.keyMetrics?.pullThroughRate || 0}%
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Loans Falling Behind</div>
            <div className="metric-value">
              {efficiencyData?.keyMetrics?.loansFallingBehind || 0}
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Total Leads</div>
            <div className="metric-value">
              {efficiencyData?.summary?.totalLeads || 0}
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Total Loans</div>
            <div className="metric-value">
              {efficiencyData?.summary?.totalLoans || 0}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="efficiency-content-grid">

        {/* Stage Performance Section */}
        <div className="efficiency-section stage-performance">
          <h2>Stage Performance Analysis</h2>
          {stageMetrics.length > 0 ? (
            <div className="stage-table">
              <table>
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Type</th>
                    <th>Volume</th>
                    <th>Avg. Time</th>
                    <th>Efficiency</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {stageMetrics.filter(s => s.volume > 0).map((stage, idx) => (
                    <tr
                      key={idx}
                      className="stage-row clickable"
                      onClick={() => handleStageClick(stage)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="stage-name">{stage.name}</td>
                      <td>
                        <span className={`type-badge ${stage.type}`}>
                          {stage.type === 'lead' ? '📋 Lead' : '🏠 Loan'}
                        </span>
                      </td>
                      <td>{stage.volume}</td>
                      <td>{stage.avgTime}</td>
                      <td>
                        <div className="efficiency-cell">
                          <div className={`efficiency-badge ${getStatusColor(stage.efficiency)}`}>
                            {stage.efficiency}%
                          </div>
                        </div>
                      </td>
                      <td className="view-arrow-cell">
                        <span className="view-arrow" title="View details">→</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {stageMetrics.filter(s => s.volume > 0).length === 0 && (
                <div className="empty-section">
                  <p>No active leads or loans in any stage.</p>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-section">
              <p>No stage data available.</p>
            </div>
          )}
        </div>

        {/* Team Performance Section */}
        {teamMetrics.length > 0 && (
          <div className="efficiency-section team-performance">
            <h2>Team Performance Metrics</h2>
            <div className="team-cards">
              {teamMetrics.map((member, idx) => (
                <div
                  key={idx}
                  className="team-performance-card clickable"
                  onClick={() => handleTeamMemberClick(member)}
                  style={{ cursor: 'pointer' }}
                >
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
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bottlenecks Section */}
        <div className="efficiency-section bottlenecks-section">
          <h2>Active Bottlenecks & Recommendations</h2>
          {bottlenecks.length > 0 ? (
            <div className="bottlenecks-list">
              {bottlenecks.map((bottleneck) => (
                <div
                  key={bottleneck.id}
                  className={`bottleneck-card severity-${bottleneck.severity}`}
                  onClick={() => handleBottleneckClick(bottleneck)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="bottleneck-header">
                    <div className="bottleneck-title">
                      <span className="severity-icon">{getSeverityIcon(bottleneck.severity)}</span>
                      <h3>{bottleneck.issue}</h3>
                    </div>
                    <div className="bottleneck-stage">{bottleneck.stage}</div>
                  </div>
                  <div className="bottleneck-details">
                    <div className="bottleneck-stat">
                      <span className="stat-label">Affected:</span>
                      <span className="stat-value">{bottleneck.affectedCount}</span>
                    </div>
                    <div className="bottleneck-stat">
                      <span className="stat-label">Delay:</span>
                      <span className="stat-value">{bottleneck.avgDelay}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-section success">
              <span className="success-icon">✅</span>
              <p>No bottlenecks detected! Your pipeline is flowing smoothly.</p>
            </div>
          )}
        </div>

        {/* Performance Trends Chart */}
        <div className="efficiency-section trends-section">
          <h2>Efficiency Trends (Last 12 Weeks)</h2>
          {trends.some(t => t.volume > 0) ? (
            <div className="trends-chart">
              <div className="chart-container">
                {trends.map((trend, idx) => (
                  <div key={idx} className="chart-bar-group">
                    <div className="chart-bars">
                      <div
                        className="chart-bar score-bar"
                        style={{ height: `${trend.score}%` }}
                        title={`Efficiency: ${trend.score}%`}
                      ></div>
                      <div
                        className="chart-bar volume-bar"
                        style={{ height: `${Math.min((trend.volume / 20) * 100, 100)}%` }}
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
          ) : (
            <div className="empty-section">
              <p>No historical data available yet. Check back after processing some leads and loans.</p>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

export default PipelineEfficiency;
