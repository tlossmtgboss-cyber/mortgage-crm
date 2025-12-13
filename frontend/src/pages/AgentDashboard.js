import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentAPI } from '../services/api';
import './AgentDashboard.css';

function AgentDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [agents, setAgents] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [healthFilter, setHealthFilter] = useState('all');

  // Fetch all dashboard data
  const fetchDashboardData = async () => {
    try {
      setError(null);
      const [summaryData, agentsData, alertsData, metricsData] = await Promise.all([
        agentAPI.getDashboardSummary(),
        agentAPI.getProfiles({ status: 'active' }),
        agentAPI.getAlerts({ status: 'active', limit: 10 }),
        agentAPI.getMetrics ? agentAPI.getMetrics() : Promise.resolve(null)
      ]);

      setSummary(summaryData);
      setAgents(agentsData.profiles || agentsData || []);
      setAlerts(alertsData.alerts || alertsData || []);
      setMetrics(metricsData);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      setError('Failed to load dashboard data. Please check your connection and try again.');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();

    // Auto-refresh every 30 seconds
    let refreshInterval;
    if (autoRefresh) {
      refreshInterval = setInterval(() => {
        fetchDashboardData();
      }, 30000);
    }

    return () => {
      if (refreshInterval) clearInterval(refreshInterval);
    };
  }, [autoRefresh]);

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  const getHealthBadgeClass = (status) => {
    switch (status) {
      case 'healthy': return 'health-badge healthy';
      case 'warning': return 'health-badge warning';
      case 'critical': return 'health-badge critical';
      default: return 'health-badge unknown';
    }
  };

  const getSeverityClass = (severity) => {
    switch (severity) {
      case 'critical': return 'severity-critical';
      case 'warning': return 'severity-warning';
      case 'info': return 'severity-info';
      default: return 'severity-low';
    }
  };

  const getCategoryIcon = (category) => {
    const icons = {
      crm: 'fas fa-chart-line',
      compliance: 'fas fa-shield-alt',
      sales: 'fas fa-handshake',
      operations: 'fas fa-cogs',
      advisory: 'fas fa-lightbulb',
      communication: 'fas fa-comments',
      monitoring: 'fas fa-eye'
    };
    return icons[category] || 'fas fa-robot';
  };

  // Filter agents
  const filteredAgents = agents.filter(agent => {
    const matchesSearch = agent.display_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         agent.agent_name?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = categoryFilter === 'all' || agent.category === categoryFilter;
    const matchesHealth = healthFilter === 'all' || agent.health_status === healthFilter;
    return matchesSearch && matchesCategory && matchesHealth;
  });

  // Get unique categories
  const categories = [...new Set(agents.map(a => a.category).filter(Boolean))];

  if (loading) {
    return (
      <div className="agent-dashboard loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Agent Dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="agent-dashboard">
        <div className="dashboard-header">
          <div className="header-left">
            <h1><i className="fas fa-robot"></i> Agent Governance</h1>
            <p className="subtitle">Monitor and manage AI agents</p>
          </div>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={() => fetchDashboardData()}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-left">
          <h1><i className="fas fa-robot"></i> Agent Governance</h1>
          <p className="subtitle">Monitor and manage AI agents</p>
        </div>
        <div className="header-right">
          <button
            className={`auto-refresh-btn ${autoRefresh ? 'active' : ''}`}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            <i className={`fas fa-sync-alt ${autoRefresh ? 'fa-spin' : ''}`}></i>
            {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
          </button>
          <button className="action-btn primary" onClick={() => navigate('/agent-gym')}>
            <i className="fas fa-dumbbell"></i> Agent Gym
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <i className="fas fa-tachometer-alt"></i> Overview
        </button>
        <button
          className={`tab ${activeTab === 'agents' ? 'active' : ''}`}
          onClick={() => setActiveTab('agents')}
        >
          <i className="fas fa-users-cog"></i> Agents
        </button>
        <button
          className={`tab ${activeTab === 'alerts' ? 'active' : ''}`}
          onClick={() => setActiveTab('alerts')}
        >
          <i className="fas fa-bell"></i> Alerts
          {alerts.length > 0 && <span className="tab-badge">{alerts.length}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'metrics' ? 'active' : ''}`}
          onClick={() => setActiveTab('metrics')}
        >
          <i className="fas fa-chart-bar"></i> Metrics
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="tab-content overview-content">
          {/* Summary Cards */}
          <div className="summary-cards">
            <div className="summary-card total">
              <div className="card-icon">
                <i className="fas fa-robot"></i>
              </div>
              <div className="card-content">
                <span className="card-value">{summary?.total_agents || 0}</span>
                <span className="card-label">Total Agents</span>
              </div>
            </div>
            <div className="summary-card healthy">
              <div className="card-icon">
                <i className="fas fa-check-circle"></i>
              </div>
              <div className="card-content">
                <span className="card-value">{summary?.health_summary?.healthy || 0}</span>
                <span className="card-label">Healthy</span>
              </div>
            </div>
            <div className="summary-card warning">
              <div className="card-icon">
                <i className="fas fa-exclamation-triangle"></i>
              </div>
              <div className="card-content">
                <span className="card-value">{summary?.health_summary?.warning || 0}</span>
                <span className="card-label">Warning</span>
              </div>
            </div>
            <div className="summary-card critical">
              <div className="card-icon">
                <i className="fas fa-times-circle"></i>
              </div>
              <div className="card-content">
                <span className="card-value">{summary?.health_summary?.critical || 0}</span>
                <span className="card-label">Critical</span>
              </div>
            </div>
          </div>

          {/* Metrics Row */}
          <div className="metrics-row">
            <div className="metric-card">
              <i className="fas fa-bolt"></i>
              <div className="metric-info">
                <span className="metric-value">{summary?.executions_24h?.toLocaleString() || 0}</span>
                <span className="metric-label">Executions (24h)</span>
              </div>
            </div>
            <div className="metric-card">
              <i className="fas fa-percentage"></i>
              <div className="metric-info">
                <span className="metric-value">{summary?.success_rate_24h?.toFixed(1) || 0}%</span>
                <span className="metric-label">Success Rate</span>
              </div>
            </div>
            <div className="metric-card">
              <i className="fas fa-clock"></i>
              <div className="metric-info">
                <span className="metric-value">{summary?.avg_response_time_ms || 0}ms</span>
                <span className="metric-label">Avg Response Time</span>
              </div>
            </div>
            <div className="metric-card alerts">
              <i className="fas fa-bell"></i>
              <div className="metric-info">
                <span className="metric-value">{summary?.active_alerts || 0}</span>
                <span className="metric-label">Active Alerts</span>
              </div>
            </div>
          </div>

          {/* Two Column Layout */}
          <div className="overview-grid">
            {/* Agent Health Summary */}
            <div className="panel agent-health-panel">
              <div className="panel-header">
                <h3><i className="fas fa-heartbeat"></i> Agent Health</h3>
                <button className="view-all-btn" onClick={() => setActiveTab('agents')}>
                  View All <i className="fas fa-chevron-right"></i>
                </button>
              </div>
              <div className="panel-content">
                <div className="agent-list-mini">
                  {agents.slice(0, 6).map(agent => (
                    <div
                      key={agent.id}
                      className="agent-item-mini"
                      onClick={() => navigate(`/agent/${agent.id}`)}
                    >
                      <div className="agent-icon">
                        <i className={getCategoryIcon(agent.category)}></i>
                      </div>
                      <div className="agent-info">
                        <span className="agent-name">{agent.display_name}</span>
                        <span className="agent-stats">
                          {agent.success_rate?.toFixed(1)}% success | {formatTimestamp(agent.last_execution_at)}
                        </span>
                      </div>
                      <span className={getHealthBadgeClass(agent.health_status)}>
                        {agent.health_status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Recent Alerts */}
            <div className="panel alerts-panel">
              <div className="panel-header">
                <h3><i className="fas fa-exclamation-circle"></i> Recent Alerts</h3>
                <button className="view-all-btn" onClick={() => setActiveTab('alerts')}>
                  View All <i className="fas fa-chevron-right"></i>
                </button>
              </div>
              <div className="panel-content">
                {alerts.length === 0 ? (
                  <div className="empty-state">
                    <i className="fas fa-check-circle"></i>
                    <p>No active alerts</p>
                  </div>
                ) : (
                  <div className="alert-list">
                    {alerts.slice(0, 5).map(alert => (
                      <div key={alert.id} className={`alert-item ${getSeverityClass(alert.severity)}`}>
                        <div className="alert-icon">
                          <i className={alert.severity === 'critical' ? 'fas fa-times-circle' : 'fas fa-exclamation-triangle'}></i>
                        </div>
                        <div className="alert-content">
                          <span className="alert-title">{alert.title}</span>
                          <span className="alert-agent">{alert.agent_name}</span>
                          <span className="alert-time">{formatTimestamp(alert.created_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="quick-actions">
            <h3>Quick Actions</h3>
            <div className="action-buttons">
              <button className="quick-action-btn" onClick={() => navigate('/agent-gym')}>
                <i className="fas fa-dumbbell"></i>
                <span>Training Gym</span>
              </button>
              <button className="quick-action-btn" onClick={() => navigate('/agent-chat')}>
                <i className="fas fa-comments"></i>
                <span>Chat with Agent</span>
              </button>
              <button className="quick-action-btn" onClick={() => fetchDashboardData()}>
                <i className="fas fa-sync-alt"></i>
                <span>Refresh Data</span>
              </button>
              <button className="quick-action-btn" onClick={() => setActiveTab('alerts')}>
                <i className="fas fa-bell"></i>
                <span>View Alerts</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Agents Tab */}
      {activeTab === 'agents' && (
        <div className="tab-content agents-content">
          {/* Filters */}
          <div className="filters-bar">
            <div className="search-box">
              <i className="fas fa-search"></i>
              <input
                type="text"
                placeholder="Search agents..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="filter-group">
              <label>Category:</label>
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <option value="all">All Categories</option>
                {categories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <div className="filter-group">
              <label>Health:</label>
              <select value={healthFilter} onChange={(e) => setHealthFilter(e.target.value)}>
                <option value="all">All Status</option>
                <option value="healthy">Healthy</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>

          {/* Agents List */}
          <div className="agents-table">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Executions</th>
                  <th>Success Rate</th>
                  <th>Avg Response</th>
                  <th>Last Activity</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredAgents.map(agent => (
                  <tr
                    key={agent.id}
                    className={`agent-row ${agent.health_status}`}
                    onClick={() => navigate(`/agent/${agent.id}`)}
                  >
                    <td className="agent-name-cell">
                      <div className="agent-icon">
                        <i className={getCategoryIcon(agent.category)}></i>
                      </div>
                      <span className="agent-display-name">{agent.display_name}</span>
                    </td>
                    <td>
                      <span className="category-badge">{agent.category}</span>
                    </td>
                    <td>
                      <span className={getHealthBadgeClass(agent.health_status)}>
                        {agent.health_status}
                      </span>
                    </td>
                    <td className="metric-cell">{agent.total_executions?.toLocaleString()}</td>
                    <td className="metric-cell">
                      <span className={`success-rate ${agent.success_rate >= 95 ? 'high' : agent.success_rate >= 90 ? 'medium' : 'low'}`}>
                        {agent.success_rate?.toFixed(1)}%
                      </span>
                    </td>
                    <td className="metric-cell">{agent.avg_response_time_ms}ms</td>
                    <td className="timestamp-cell">{formatTimestamp(agent.last_execution_at)}</td>
                    <td className="actions-cell">
                      <button
                        className="table-action-btn"
                        onClick={(e) => { e.stopPropagation(); navigate(`/agent-chat?agent=${agent.agent_name}`); }}
                        title="Chat with agent"
                      >
                        <i className="fas fa-comments"></i>
                      </button>
                      <button
                        className="table-action-btn"
                        onClick={(e) => { e.stopPropagation(); navigate(`/agent-gym?agent=${agent.id}`); }}
                        title="Train agent"
                      >
                        <i className="fas fa-dumbbell"></i>
                      </button>
                      <button
                        className="table-action-btn"
                        onClick={(e) => { e.stopPropagation(); navigate(`/agent/${agent.id}`); }}
                        title="View details"
                      >
                        <i className="fas fa-eye"></i>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {filteredAgents.length === 0 && (
            <div className="empty-state large">
              <i className="fas fa-search"></i>
              <h3>No agents found</h3>
              <p>Try adjusting your filters</p>
            </div>
          )}
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="tab-content alerts-content-full">
          <div className="alerts-header">
            <h3>Active Alerts ({alerts.length})</h3>
            <div className="alerts-actions">
              <button className="secondary-btn" onClick={() => fetchDashboardData()}>
                <i className="fas fa-sync-alt"></i> Refresh
              </button>
            </div>
          </div>

          {alerts.length === 0 ? (
            <div className="empty-state large">
              <i className="fas fa-check-circle"></i>
              <h3>All Clear!</h3>
              <p>No active alerts at this time</p>
            </div>
          ) : (
            <div className="alerts-table">
              <table>
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Agent</th>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Message</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map(alert => (
                    <tr key={alert.id} className={getSeverityClass(alert.severity)}>
                      <td>
                        <span className={`severity-badge ${alert.severity}`}>
                          {alert.severity}
                        </span>
                      </td>
                      <td>{alert.agent_name}</td>
                      <td>{alert.alert_type}</td>
                      <td>{alert.title}</td>
                      <td className="message-cell">{alert.message}</td>
                      <td>{formatTimestamp(alert.created_at)}</td>
                      <td>
                        <button
                          className="table-action-btn"
                          onClick={() => navigate(`/agent/${agents.find(a => a.agent_name === alert.agent_name)?.id}`)}
                          title="View agent"
                        >
                          <i className="fas fa-eye"></i>
                        </button>
                        <button
                          className="table-action-btn acknowledge"
                          title="Acknowledge"
                        >
                          <i className="fas fa-check"></i>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Metrics Tab */}
      {activeTab === 'metrics' && (
        <div className="tab-content metrics-content">
          {/* Executions Chart */}
          <div className="panel chart-panel">
            <div className="panel-header">
              <h3><i className="fas fa-chart-line"></i> Hourly Executions</h3>
            </div>
            <div className="panel-content">
              {metrics?.hourly_executions?.length > 0 ? (
                <div className="simple-bar-chart">
                  {metrics.hourly_executions.map((hour, idx) => (
                    <div key={idx} className="bar-column">
                      <div
                        className="bar"
                        style={{ height: `${(hour.count / 300) * 100}%` }}
                        title={`${hour.hour}: ${hour.count} executions, ${hour.success_rate}% success`}
                      >
                        <span className="bar-value">{hour.count}</span>
                      </div>
                      <span className="bar-label">{hour.hour.split(':')[0]}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <i className="fas fa-chart-bar"></i>
                  <p>No execution data available</p>
                </div>
              )}
            </div>
          </div>

          {/* Top Tools */}
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-tools"></i> Most Used Tools</h3>
            </div>
            <div className="panel-content">
              {metrics?.top_tools?.length > 0 ? (
                <div className="tools-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Tool Name</th>
                        <th>Executions</th>
                        <th>Avg Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metrics.top_tools.map((tool, idx) => (
                        <tr key={idx}>
                          <td><code>{tool.name}</code></td>
                          <td>{tool.count.toLocaleString()}</td>
                          <td>{tool.avg_time_ms}ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state">
                  <i className="fas fa-tools"></i>
                  <p>No tool usage data available</p>
                </div>
              )}
            </div>
          </div>

          {/* Agent Performance Comparison */}
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-trophy"></i> Agent Performance Ranking</h3>
            </div>
            <div className="panel-content">
              {agents.length > 0 ? (
                <div className="performance-list">
                  {[...agents]
                    .sort((a, b) => (b.success_rate || 0) - (a.success_rate || 0))
                    .slice(0, 8)
                    .map((agent, idx) => (
                      <div key={agent.id} className="performance-item">
                        <span className="rank">#{idx + 1}</span>
                        <span className="agent-name">{agent.display_name}</span>
                        <div className="progress-bar">
                          <div
                            className="progress-fill"
                            style={{ width: `${agent.success_rate || 0}%` }}
                          ></div>
                        </div>
                        <span className="success-rate">{agent.success_rate?.toFixed(1)}%</span>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="empty-state">
                  <i className="fas fa-trophy"></i>
                  <p>No agent performance data available</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentDashboard;
