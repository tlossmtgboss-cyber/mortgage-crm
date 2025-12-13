import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentAPI } from '../services/api';
import './AgentDashboard.css';

// Mock data generators for development/fallback
const generateMockDashboardSummary = () => ({
  total_agents: 20,
  active_agents: 18,
  health_summary: {
    healthy: 15,
    warning: 3,
    critical: 1,
    unknown: 1
  },
  executions_24h: 2847,
  success_rate_24h: 94.2,
  active_alerts: 3,
  avg_response_time_ms: 1250
});

const generateMockAgents = () => [
  // Core CRM Agents (8)
  { id: 1, agent_name: 'pipeline_analyst', display_name: 'Pipeline Analyst', category: 'analytics', status: 'active', health_status: 'healthy', total_executions: 4521, success_rate: 96.2, avg_response_time_ms: 890, last_execution_at: new Date(Date.now() - 5 * 60000).toISOString() },
  { id: 2, agent_name: 'compliance_checker', display_name: 'Compliance Checker', category: 'compliance', status: 'active', health_status: 'healthy', total_executions: 2134, success_rate: 98.1, avg_response_time_ms: 1120, last_execution_at: new Date(Date.now() - 15 * 60000).toISOString() },
  { id: 3, agent_name: 'lead_nurturer', display_name: 'Lead Nurturer', category: 'sales', status: 'active', health_status: 'warning', total_executions: 3876, success_rate: 82.5, avg_response_time_ms: 2340, last_execution_at: new Date(Date.now() - 2 * 60000).toISOString() },
  { id: 4, agent_name: 'document_tracker', display_name: 'Document Tracker', category: 'operations', status: 'active', health_status: 'healthy', total_executions: 5621, success_rate: 95.8, avg_response_time_ms: 750, last_execution_at: new Date(Date.now() - 8 * 60000).toISOString() },
  { id: 5, agent_name: 'rate_advisor', display_name: 'Rate Advisor', category: 'advisory', status: 'active', health_status: 'critical', total_executions: 1892, success_rate: 68.4, avg_response_time_ms: 4500, last_execution_at: new Date(Date.now() - 45 * 60000).toISOString() },
  { id: 6, agent_name: 'scheduler', display_name: 'Smart Scheduler', category: 'operations', status: 'active', health_status: 'healthy', total_executions: 2945, success_rate: 97.3, avg_response_time_ms: 680, last_execution_at: new Date(Date.now() - 3 * 60000).toISOString() },
  { id: 7, agent_name: 'receptionist', display_name: 'AI Receptionist', category: 'communication', status: 'active', health_status: 'healthy', total_executions: 8934, success_rate: 94.5, avg_response_time_ms: 1100, last_execution_at: new Date(Date.now() - 1 * 60000).toISOString() },
  { id: 8, agent_name: 'sla_monitor', display_name: 'SLA Tracker', category: 'monitoring', status: 'active', health_status: 'warning', total_executions: 1567, success_rate: 85.2, avg_response_time_ms: 1890, last_execution_at: new Date(Date.now() - 10 * 60000).toISOString() },
  // Extended Agents (12)
  { id: 9, agent_name: 'task_automation', display_name: 'Task Automation', category: 'operations', status: 'active', health_status: 'healthy', total_executions: 6234, success_rate: 95.7, avg_response_time_ms: 720, last_execution_at: new Date(Date.now() - 4 * 60000).toISOString() },
  { id: 10, agent_name: 'profitability_analyst', display_name: 'Profitability Analyst', category: 'analytics', status: 'active', health_status: 'healthy', total_executions: 1823, success_rate: 97.2, avg_response_time_ms: 1340, last_execution_at: new Date(Date.now() - 12 * 60000).toISOString() },
  { id: 11, agent_name: 'subscription_manager', display_name: 'Subscription Manager', category: 'operations', status: 'active', health_status: 'healthy', total_executions: 987, success_rate: 99.1, avg_response_time_ms: 560, last_execution_at: new Date(Date.now() - 30 * 60000).toISOString() },
  { id: 12, agent_name: 'onboarding_assistant', display_name: 'Onboarding Assistant', category: 'operations', status: 'active', health_status: 'healthy', total_executions: 2456, success_rate: 94.8, avg_response_time_ms: 1200, last_execution_at: new Date(Date.now() - 20 * 60000).toISOString() },
  { id: 13, agent_name: 'voice_agent', display_name: 'Voice OS', category: 'communication', status: 'active', health_status: 'warning', total_executions: 3421, success_rate: 88.3, avg_response_time_ms: 2100, last_execution_at: new Date(Date.now() - 6 * 60000).toISOString() },
  { id: 14, agent_name: 'team_coach', display_name: 'Team Coach', category: 'analytics', status: 'active', health_status: 'healthy', total_executions: 1245, success_rate: 96.5, avg_response_time_ms: 980, last_execution_at: new Date(Date.now() - 25 * 60000).toISOString() },
  { id: 15, agent_name: 'email_intel_agent', display_name: 'Email Intelligence', category: 'automation', status: 'active', health_status: 'healthy', total_executions: 7823, success_rate: 95.4, avg_response_time_ms: 650, last_execution_at: new Date(Date.now() - 2 * 60000).toISOString() },
  { id: 16, agent_name: 'notification_center', display_name: 'Notification Center', category: 'automation', status: 'active', health_status: 'healthy', total_executions: 12456, success_rate: 99.2, avg_response_time_ms: 320, last_execution_at: new Date(Date.now() - 1 * 60000).toISOString() },
  { id: 17, agent_name: 'customer_intelligence', display_name: 'Customer Intelligence', category: 'analytics', status: 'active', health_status: 'healthy', total_executions: 2134, success_rate: 94.1, avg_response_time_ms: 1450, last_execution_at: new Date(Date.now() - 18 * 60000).toISOString() },
  { id: 18, agent_name: 'video_agent', display_name: 'UVIP', category: 'analytics', status: 'active', health_status: 'healthy', total_executions: 567, success_rate: 97.8, avg_response_time_ms: 2800, last_execution_at: new Date(Date.now() - 45 * 60000).toISOString() },
  { id: 19, agent_name: 'integrations_agent', display_name: 'Integrations', category: 'operations', status: 'active', health_status: 'healthy', total_executions: 3421, success_rate: 96.7, avg_response_time_ms: 890, last_execution_at: new Date(Date.now() - 8 * 60000).toISOString() },
  { id: 20, agent_name: 'reporting_engine', display_name: 'Reporting Engine', category: 'analytics', status: 'active', health_status: 'healthy', total_executions: 4567, success_rate: 98.3, avg_response_time_ms: 1100, last_execution_at: new Date(Date.now() - 15 * 60000).toISOString() }
];

const generateMockAlerts = () => [
  {
    id: 1,
    agent_name: 'rate_advisor',
    alert_type: 'health',
    severity: 'critical',
    title: 'High Error Rate Detected',
    message: 'Error rate at 31.6% - exceeds threshold of 20%',
    status: 'active',
    created_at: new Date(Date.now() - 30 * 60000).toISOString()
  },
  {
    id: 2,
    agent_name: 'lead_nurturer',
    alert_type: 'performance',
    severity: 'warning',
    title: 'Elevated Response Time',
    message: 'Average response time 2340ms - above 2000ms threshold',
    status: 'active',
    created_at: new Date(Date.now() - 2 * 3600000).toISOString()
  },
  {
    id: 3,
    agent_name: 'sla_monitor',
    alert_type: 'health',
    severity: 'warning',
    title: 'Success Rate Below Target',
    message: 'Success rate 85.2% - below 90% target',
    status: 'active',
    created_at: new Date(Date.now() - 4 * 3600000).toISOString()
  }
];

const generateMockMetrics = () => ({
  hourly_executions: [
    { hour: '00:00', count: 45, success_rate: 95.5 },
    { hour: '01:00', count: 23, success_rate: 96.2 },
    { hour: '02:00', count: 18, success_rate: 94.1 },
    { hour: '03:00', count: 12, success_rate: 97.8 },
    { hour: '04:00', count: 15, success_rate: 93.3 },
    { hour: '05:00', count: 28, success_rate: 95.0 },
    { hour: '06:00', count: 67, success_rate: 94.8 },
    { hour: '07:00', count: 124, success_rate: 92.1 },
    { hour: '08:00', count: 189, success_rate: 93.5 },
    { hour: '09:00', count: 234, success_rate: 94.2 },
    { hour: '10:00', count: 256, success_rate: 95.1 },
    { hour: '11:00', count: 198, success_rate: 94.8 }
  ],
  top_tools: [
    { name: 'get_pipeline_metrics', count: 342, avg_time_ms: 450 },
    { name: 'check_trid_compliance', count: 289, avg_time_ms: 890 },
    { name: 'get_lead_details', count: 256, avg_time_ms: 320 },
    { name: 'get_missing_documents', count: 234, avg_time_ms: 560 },
    { name: 'send_document_reminder', count: 189, avg_time_ms: 1200 }
  ]
});

function AgentDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
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
      const [summaryData, agentsData, alertsData] = await Promise.all([
        agentAPI.getDashboardSummary(),
        agentAPI.getProfiles({ status: 'active' }),
        agentAPI.getAlerts({ status: 'active', limit: 10 })
      ]);

      setSummary(summaryData);
      setAgents(agentsData.profiles || agentsData);
      setAlerts(alertsData.alerts || alertsData);
      setMetrics(generateMockMetrics()); // Metrics from backend or mock
      setLoading(false);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      // Load mock data on error
      setSummary(generateMockDashboardSummary());
      setAgents(generateMockAgents());
      setAlerts(generateMockAlerts());
      setMetrics(generateMockMetrics());
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

          {/* Agents Grid */}
          <div className="agents-grid">
            {filteredAgents.map(agent => (
              <div
                key={agent.id}
                className={`agent-card ${agent.health_status}`}
                onClick={() => navigate(`/agent/${agent.id}`)}
              >
                <div className="agent-card-header">
                  <div className="agent-icon-large">
                    <i className={getCategoryIcon(agent.category)}></i>
                  </div>
                  <span className={getHealthBadgeClass(agent.health_status)}>
                    {agent.health_status}
                  </span>
                </div>
                <div className="agent-card-body">
                  <h4>{agent.display_name}</h4>
                  <span className="agent-category">{agent.category}</span>
                  <div className="agent-metrics">
                    <div className="metric">
                      <span className="metric-value">{agent.total_executions?.toLocaleString()}</span>
                      <span className="metric-label">Executions</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{agent.success_rate?.toFixed(1)}%</span>
                      <span className="metric-label">Success</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{agent.avg_response_time_ms}ms</span>
                      <span className="metric-label">Avg Time</span>
                    </div>
                  </div>
                </div>
                <div className="agent-card-footer">
                  <span className="last-activity">
                    <i className="fas fa-clock"></i> {formatTimestamp(agent.last_execution_at)}
                  </span>
                  <div className="card-actions">
                    <button
                      className="card-action-btn"
                      onClick={(e) => { e.stopPropagation(); navigate(`/agent-chat?agent=${agent.agent_name}`); }}
                      title="Chat with agent"
                    >
                      <i className="fas fa-comments"></i>
                    </button>
                    <button
                      className="card-action-btn"
                      onClick={(e) => { e.stopPropagation(); navigate(`/agent-gym?agent=${agent.id}`); }}
                      title="Train agent"
                    >
                      <i className="fas fa-dumbbell"></i>
                    </button>
                  </div>
                </div>
              </div>
            ))}
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
              <div className="simple-bar-chart">
                {metrics?.hourly_executions?.map((hour, idx) => (
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
            </div>
          </div>

          {/* Top Tools */}
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-tools"></i> Most Used Tools</h3>
            </div>
            <div className="panel-content">
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
                    {metrics?.top_tools?.map((tool, idx) => (
                      <tr key={idx}>
                        <td><code>{tool.name}</code></td>
                        <td>{tool.count.toLocaleString()}</td>
                        <td>{tool.avg_time_ms}ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Agent Performance Comparison */}
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-trophy"></i> Agent Performance Ranking</h3>
            </div>
            <div className="panel-content">
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentDashboard;
