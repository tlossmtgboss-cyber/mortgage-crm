import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { agentAPI } from '../services/api';
import './AgentProfile.css';

// Mock data generators
const generateMockAgent = (id) => ({
  id: parseInt(id),
  agent_name: 'pipeline_analyst',
  display_name: 'Pipeline Analyst',
  description: 'Analyzes loan pipeline data, calculates metrics, identifies bottlenecks, and provides recommendations for improving pipeline efficiency.',
  category: 'crm',
  status: 'active',
  health_status: 'healthy',
  version: '1.2.0',
  model_name: 'claude-3-sonnet',
  system_prompt: 'You are a mortgage pipeline analyst assistant...',
  temperature: 0.7,
  max_tokens: 4096,
  total_executions: 4521,
  successful_executions: 4349,
  failed_executions: 172,
  success_rate: 96.2,
  avg_response_time_ms: 890,
  last_execution_at: new Date(Date.now() - 5 * 60000).toISOString(),
  last_health_check: new Date(Date.now() - 2 * 60000).toISOString(),
  created_at: new Date(Date.now() - 90 * 24 * 3600000).toISOString(),
  updated_at: new Date(Date.now() - 2 * 24 * 3600000).toISOString(),
  capabilities: ['pipeline_analysis', 'bottleneck_detection', 'conversion_tracking', 'forecasting'],
  tools: [
    { name: 'get_pipeline_metrics', uses: 1245, success_rate: 98.2 },
    { name: 'get_loans_by_status', uses: 892, success_rate: 97.5 },
    { name: 'get_loan_aging_report', uses: 654, success_rate: 95.8 },
    { name: 'calculate_conversion_rates', uses: 543, success_rate: 96.1 },
    { name: 'predict_closing_timeline', uses: 421, success_rate: 94.3 },
    { name: 'get_bottleneck_analysis', uses: 387, success_rate: 97.8 },
    { name: 'compare_to_benchmark', uses: 234, success_rate: 95.2 },
    { name: 'get_lo_pipeline_breakdown', uses: 145, success_rate: 98.5 }
  ]
});

const generateMockExecutions = () => [
  {
    id: 1,
    session_id: 'sess_abc123',
    status: 'completed',
    success: true,
    prompt: 'Get the current pipeline metrics for branch 5',
    response_preview: 'Current pipeline has 45 loans totaling $12.3M...',
    started_at: new Date(Date.now() - 5 * 60000).toISOString(),
    response_time_ms: 856,
    tokens_used: 1245,
    tool_calls: [{ tool_name: 'get_pipeline_metrics', success: true }]
  },
  {
    id: 2,
    session_id: 'sess_def456',
    status: 'completed',
    success: true,
    prompt: 'Show me loans in underwriting stage',
    response_preview: 'Found 12 loans currently in underwriting...',
    started_at: new Date(Date.now() - 15 * 60000).toISOString(),
    response_time_ms: 723,
    tokens_used: 987,
    tool_calls: [{ tool_name: 'get_loans_by_status', success: true }]
  },
  {
    id: 3,
    session_id: 'sess_ghi789',
    status: 'completed',
    success: false,
    prompt: 'Calculate conversion rates for last 180 days',
    response_preview: 'Error: Database timeout while fetching data...',
    error_message: 'Database connection timeout after 30s',
    started_at: new Date(Date.now() - 45 * 60000).toISOString(),
    response_time_ms: 30125,
    tokens_used: 0,
    tool_calls: [{ tool_name: 'calculate_conversion_rates', success: false }]
  },
  {
    id: 4,
    session_id: 'sess_jkl012',
    status: 'completed',
    success: true,
    prompt: 'Where are the bottlenecks in our pipeline?',
    response_preview: '3 critical bottlenecks identified: Underwriting (avg 8.2 days)...',
    started_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    response_time_ms: 1245,
    tokens_used: 1876,
    tool_calls: [
      { tool_name: 'get_bottleneck_analysis', success: true },
      { tool_name: 'get_loan_aging_report', success: true }
    ]
  },
  {
    id: 5,
    session_id: 'sess_mno345',
    status: 'completed',
    success: true,
    prompt: 'How does Sarah compare to the team benchmark?',
    response_preview: 'Sarah is performing 15% above the team average...',
    started_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    response_time_ms: 945,
    tokens_used: 1123,
    tool_calls: [{ tool_name: 'compare_to_benchmark', success: true }]
  }
];

const generateMockMetrics = () => ({
  daily: [
    { date: '12/06', executions: 145, success_rate: 95.2 },
    { date: '12/07', executions: 189, success_rate: 96.8 },
    { date: '12/08', executions: 167, success_rate: 94.1 },
    { date: '12/09', executions: 234, success_rate: 97.3 },
    { date: '12/10', executions: 198, success_rate: 95.9 },
    { date: '12/11', executions: 223, success_rate: 96.4 },
    { date: '12/12', executions: 156, success_rate: 96.2 }
  ],
  performance: {
    avg_response_time_7d: 892,
    avg_response_time_30d: 945,
    p95_response_time: 2340,
    error_rate_7d: 3.8,
    error_rate_30d: 4.2
  }
});

const generateMockAlerts = () => [
  {
    id: 1,
    alert_type: 'performance',
    severity: 'info',
    title: 'Response Time Improvement',
    message: 'Average response time improved by 12% over last 7 days',
    status: 'resolved',
    created_at: new Date(Date.now() - 24 * 3600000).toISOString()
  }
];

function AgentProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [agent, setAgent] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedExecution, setSelectedExecution] = useState(null);

  useEffect(() => {
    const fetchAgentData = async () => {
      try {
        const [agentData, executionsData, alertsData] = await Promise.all([
          agentAPI.getProfile(id),
          agentAPI.getExecutions({ agent_id: id, limit: 20 }),
          agentAPI.getAlerts({ agent_id: id, limit: 10 })
        ]);

        setAgent(agentData);
        setExecutions(executionsData.executions || executionsData);
        setAlerts(alertsData.alerts || alertsData);
        setMetrics(generateMockMetrics());
        setLoading(false);
      } catch (error) {
        console.error('Error fetching agent data:', error);
        // Load mock data on error
        setAgent(generateMockAgent(id));
        setExecutions(generateMockExecutions());
        setAlerts(generateMockAlerts());
        setMetrics(generateMockMetrics());
        setLoading(false);
      }
    };

    fetchAgentData();
  }, [id]);

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  const getHealthBadgeClass = (status) => {
    switch (status) {
      case 'healthy': return 'health-badge healthy';
      case 'warning': return 'health-badge warning';
      case 'critical': return 'health-badge critical';
      default: return 'health-badge unknown';
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'active': return 'status-badge active';
      case 'inactive': return 'status-badge inactive';
      case 'maintenance': return 'status-badge maintenance';
      default: return 'status-badge';
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

  if (loading) {
    return (
      <div className="agent-profile loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Agent Profile...</p>
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="agent-profile not-found">
        <div className="not-found-content">
          <i className="fas fa-robot"></i>
          <h2>Agent Not Found</h2>
          <p>The requested agent could not be found.</p>
          <button className="primary-btn" onClick={() => navigate('/agents')}>
            Back to Agents
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-profile">
      {/* Header */}
      <div className="profile-header">
        <button className="back-btn" onClick={() => navigate('/agents')}>
          <i className="fas fa-arrow-left"></i> Back to Agents
        </button>

        <div className="header-main">
          <div className="agent-identity">
            <div className="agent-icon-large">
              <i className={getCategoryIcon(agent.category)}></i>
            </div>
            <div className="agent-info">
              <h1>{agent.display_name}</h1>
              <div className="agent-meta">
                <span className={getStatusBadgeClass(agent.status)}>{agent.status}</span>
                <span className={getHealthBadgeClass(agent.health_status)}>{agent.health_status}</span>
                <span className="category-tag">{agent.category}</span>
                <span className="version-tag">v{agent.version}</span>
              </div>
            </div>
          </div>

          <div className="header-actions">
            <button className="action-btn secondary" onClick={() => navigate(`/agent-chat?agent=${agent.agent_name}`)}>
              <i className="fas fa-comments"></i> Chat
            </button>
            <button className="action-btn secondary" onClick={() => navigate(`/agent-gym?agent=${agent.id}`)}>
              <i className="fas fa-dumbbell"></i> Train
            </button>
            <button className="action-btn primary">
              <i className="fas fa-cog"></i> Configure
            </button>
          </div>
        </div>

        <p className="agent-description">{agent.description}</p>
      </div>

      {/* Stats Row */}
      <div className="stats-row">
        <div className="stat-card">
          <span className="stat-value">{agent.total_executions?.toLocaleString()}</span>
          <span className="stat-label">Total Executions</span>
        </div>
        <div className="stat-card success">
          <span className="stat-value">{agent.success_rate?.toFixed(1)}%</span>
          <span className="stat-label">Success Rate</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{agent.avg_response_time_ms}ms</span>
          <span className="stat-label">Avg Response Time</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{formatTimestamp(agent.last_execution_at)}</span>
          <span className="stat-label">Last Execution</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="profile-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <i className="fas fa-info-circle"></i> Overview
        </button>
        <button
          className={`tab ${activeTab === 'executions' ? 'active' : ''}`}
          onClick={() => setActiveTab('executions')}
        >
          <i className="fas fa-history"></i> Executions
        </button>
        <button
          className={`tab ${activeTab === 'tools' ? 'active' : ''}`}
          onClick={() => setActiveTab('tools')}
        >
          <i className="fas fa-tools"></i> Tools
        </button>
        <button
          className={`tab ${activeTab === 'metrics' ? 'active' : ''}`}
          onClick={() => setActiveTab('metrics')}
        >
          <i className="fas fa-chart-bar"></i> Metrics
        </button>
        <button
          className={`tab ${activeTab === 'config' ? 'active' : ''}`}
          onClick={() => setActiveTab('config')}
        >
          <i className="fas fa-sliders-h"></i> Configuration
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="tab-content">
          <div className="overview-grid">
            {/* Capabilities */}
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-magic"></i> Capabilities</h3>
              </div>
              <div className="panel-content">
                <div className="capabilities-list">
                  {agent.capabilities?.map((cap, idx) => (
                    <span key={idx} className="capability-tag">
                      <i className="fas fa-check"></i> {cap.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Recent Activity */}
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-clock"></i> Recent Activity</h3>
              </div>
              <div className="panel-content">
                <div className="activity-list">
                  {executions.slice(0, 5).map(exec => (
                    <div key={exec.id} className={`activity-item ${exec.success ? 'success' : 'failed'}`}>
                      <div className="activity-icon">
                        <i className={exec.success ? 'fas fa-check-circle' : 'fas fa-times-circle'}></i>
                      </div>
                      <div className="activity-content">
                        <span className="activity-prompt">{exec.prompt}</span>
                        <span className="activity-time">{formatTimestamp(exec.started_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Alerts */}
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-bell"></i> Recent Alerts</h3>
              </div>
              <div className="panel-content">
                {alerts.length === 0 ? (
                  <div className="empty-state-small">
                    <i className="fas fa-check-circle"></i>
                    <p>No recent alerts</p>
                  </div>
                ) : (
                  <div className="alerts-mini-list">
                    {alerts.map(alert => (
                      <div key={alert.id} className={`alert-mini ${alert.severity}`}>
                        <span className="alert-title">{alert.title}</span>
                        <span className="alert-time">{formatTimestamp(alert.created_at)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Details */}
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-info"></i> Details</h3>
              </div>
              <div className="panel-content">
                <div className="details-grid">
                  <div className="detail-item">
                    <span className="detail-label">Agent ID</span>
                    <span className="detail-value">{agent.id}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Agent Name</span>
                    <span className="detail-value"><code>{agent.agent_name}</code></span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Model</span>
                    <span className="detail-value">{agent.model_name || 'claude-3-sonnet'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Created</span>
                    <span className="detail-value">{formatDate(agent.created_at)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Last Updated</span>
                    <span className="detail-value">{formatDate(agent.updated_at)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Last Health Check</span>
                    <span className="detail-value">{formatTimestamp(agent.last_health_check)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Executions Tab */}
      {activeTab === 'executions' && (
        <div className="tab-content executions-content">
          <div className="executions-layout">
            <div className="executions-list-panel">
              <div className="panel">
                <div className="panel-header">
                  <h3>Execution History</h3>
                  <span className="count-badge">{executions.length} executions</span>
                </div>
                <div className="panel-content">
                  {executions.map(exec => (
                    <div
                      key={exec.id}
                      className={`execution-item ${selectedExecution?.id === exec.id ? 'selected' : ''} ${exec.success ? 'success' : 'failed'}`}
                      onClick={() => setSelectedExecution(exec)}
                    >
                      <div className="execution-status">
                        <i className={exec.success ? 'fas fa-check-circle' : 'fas fa-times-circle'}></i>
                      </div>
                      <div className="execution-info">
                        <span className="execution-prompt">{exec.prompt}</span>
                        <div className="execution-meta">
                          <span><i className="fas fa-clock"></i> {exec.response_time_ms}ms</span>
                          <span><i className="fas fa-coins"></i> {exec.tokens_used} tokens</span>
                          <span>{formatTimestamp(exec.started_at)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="execution-detail-panel">
              {selectedExecution ? (
                <div className="panel">
                  <div className="panel-header">
                    <h3>Execution Details</h3>
                    <span className={`status-badge ${selectedExecution.success ? 'success' : 'failed'}`}>
                      {selectedExecution.success ? 'Success' : 'Failed'}
                    </span>
                  </div>
                  <div className="panel-content">
                    <div className="detail-section">
                      <h4>Prompt</h4>
                      <div className="prompt-box">{selectedExecution.prompt}</div>
                    </div>
                    <div className="detail-section">
                      <h4>Response</h4>
                      <div className="response-box">
                        {selectedExecution.success ? selectedExecution.response_preview : selectedExecution.error_message}
                      </div>
                    </div>
                    <div className="detail-section">
                      <h4>Tool Calls</h4>
                      <div className="tool-calls-list">
                        {selectedExecution.tool_calls?.map((tool, idx) => (
                          <div key={idx} className={`tool-call-item ${tool.success ? 'success' : 'failed'}`}>
                            <i className={tool.success ? 'fas fa-check' : 'fas fa-times'}></i>
                            <code>{tool.tool_name}</code>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="detail-section metrics-row-small">
                      <div className="metric-item">
                        <span className="metric-label">Response Time</span>
                        <span className="metric-value">{selectedExecution.response_time_ms}ms</span>
                      </div>
                      <div className="metric-item">
                        <span className="metric-label">Tokens Used</span>
                        <span className="metric-value">{selectedExecution.tokens_used}</span>
                      </div>
                      <div className="metric-item">
                        <span className="metric-label">Session ID</span>
                        <span className="metric-value"><code>{selectedExecution.session_id}</code></span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="panel empty-panel">
                  <div className="empty-state-small">
                    <i className="fas fa-mouse-pointer"></i>
                    <p>Select an execution to view details</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tools Tab */}
      {activeTab === 'tools' && (
        <div className="tab-content">
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-tools"></i> Available Tools</h3>
              <span className="count-badge">{agent.tools?.length || 0} tools</span>
            </div>
            <div className="panel-content">
              <div className="tools-grid">
                {agent.tools?.map((tool, idx) => (
                  <div key={idx} className="tool-card">
                    <div className="tool-header">
                      <code className="tool-name">{tool.name}</code>
                      <span className={`success-badge ${tool.success_rate >= 95 ? 'excellent' : tool.success_rate >= 90 ? 'good' : 'needs-work'}`}>
                        {tool.success_rate}%
                      </span>
                    </div>
                    <div className="tool-stats">
                      <div className="tool-stat">
                        <span className="stat-value">{tool.uses.toLocaleString()}</span>
                        <span className="stat-label">Uses</span>
                      </div>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${tool.success_rate}%` }}></div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Metrics Tab */}
      {activeTab === 'metrics' && (
        <div className="tab-content">
          <div className="metrics-grid">
            {/* Daily Chart */}
            <div className="panel chart-panel">
              <div className="panel-header">
                <h3><i className="fas fa-chart-line"></i> Daily Executions (7 Days)</h3>
              </div>
              <div className="panel-content">
                <div className="simple-bar-chart">
                  {metrics?.daily?.map((day, idx) => (
                    <div key={idx} className="bar-column">
                      <div
                        className="bar"
                        style={{ height: `${(day.executions / 250) * 100}%` }}
                        title={`${day.date}: ${day.executions} executions`}
                      >
                        <span className="bar-value">{day.executions}</span>
                      </div>
                      <span className="bar-label">{day.date}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Performance Metrics */}
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-tachometer-alt"></i> Performance</h3>
              </div>
              <div className="panel-content">
                <div className="performance-grid">
                  <div className="perf-item">
                    <span className="perf-label">Avg Response (7d)</span>
                    <span className="perf-value">{metrics?.performance?.avg_response_time_7d}ms</span>
                  </div>
                  <div className="perf-item">
                    <span className="perf-label">Avg Response (30d)</span>
                    <span className="perf-value">{metrics?.performance?.avg_response_time_30d}ms</span>
                  </div>
                  <div className="perf-item">
                    <span className="perf-label">P95 Response</span>
                    <span className="perf-value">{metrics?.performance?.p95_response_time}ms</span>
                  </div>
                  <div className="perf-item">
                    <span className="perf-label">Error Rate (7d)</span>
                    <span className="perf-value">{metrics?.performance?.error_rate_7d}%</span>
                  </div>
                  <div className="perf-item">
                    <span className="perf-label">Error Rate (30d)</span>
                    <span className="perf-value">{metrics?.performance?.error_rate_30d}%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Execution Breakdown */}
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-chart-pie"></i> Execution Breakdown</h3>
              </div>
              <div className="panel-content">
                <div className="breakdown-stats">
                  <div className="breakdown-item success">
                    <span className="breakdown-value">{agent.successful_executions?.toLocaleString()}</span>
                    <span className="breakdown-label">Successful</span>
                    <div className="breakdown-bar">
                      <div className="fill" style={{ width: `${agent.success_rate}%` }}></div>
                    </div>
                  </div>
                  <div className="breakdown-item failed">
                    <span className="breakdown-value">{agent.failed_executions?.toLocaleString()}</span>
                    <span className="breakdown-label">Failed</span>
                    <div className="breakdown-bar">
                      <div className="fill" style={{ width: `${100 - agent.success_rate}%` }}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Configuration Tab */}
      {activeTab === 'config' && (
        <div className="tab-content">
          <div className="config-grid">
            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-brain"></i> Model Settings</h3>
              </div>
              <div className="panel-content">
                <div className="config-form">
                  <div className="form-group">
                    <label>Model</label>
                    <select disabled value={agent.model_name || 'claude-3-sonnet'}>
                      <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                      <option value="claude-3-opus">Claude 3 Opus</option>
                      <option value="claude-3-haiku">Claude 3 Haiku</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Temperature</label>
                    <input type="number" disabled value={agent.temperature || 0.7} step="0.1" min="0" max="1" />
                  </div>
                  <div className="form-group">
                    <label>Max Tokens</label>
                    <input type="number" disabled value={agent.max_tokens || 4096} />
                  </div>
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h3><i className="fas fa-scroll"></i> System Prompt</h3>
              </div>
              <div className="panel-content">
                <div className="system-prompt-box">
                  {agent.system_prompt || 'No system prompt configured'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentProfile;
