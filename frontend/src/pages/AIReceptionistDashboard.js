import { useState, useEffect } from 'react';
import { aiReceptionistDashboardAPI } from '../services/api';
import './AIReceptionistDashboard.css';

function AIReceptionistDashboard() {
  const [loading, setLoading] = useState(true);
  const [realtimeMetrics, setRealtimeMetrics] = useState(null);
  const [activityFeed, setActivityFeed] = useState([]);
  const [skills, setSkills] = useState([]);
  const [roi, setROI] = useState(null);
  const [errors, setErrors] = useState([]);
  const [systemHealth, setSystemHealth] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [selectedCall, setSelectedCall] = useState(null);

  // Fetch all dashboard data
  const fetchDashboardData = async () => {
    try {
      const [metricsData, activityData, skillsData, roiData, errorsData, healthData] = await Promise.all([
        aiReceptionistDashboardAPI.getRealtimeMetrics(),
        aiReceptionistDashboardAPI.getActivityFeed({ limit: 20 }),
        aiReceptionistDashboardAPI.getSkills(),
        aiReceptionistDashboardAPI.getROI(),
        aiReceptionistDashboardAPI.getErrors({ limit: 10 }),
        aiReceptionistDashboardAPI.getSystemHealth(),
      ]);

      setRealtimeMetrics(metricsData);
      setActivityFeed(activityData);
      setSkills(skillsData);
      setROI(roiData);
      setErrors(errorsData);
      setSystemHealth(healthData);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
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

  // Auto-select first call when activity feed loads
  useEffect(() => {
    if (activityFeed.length > 0 && !selectedCall) {
      setSelectedCall(activityFeed[0]);
    }
  }, [activityFeed, selectedCall]);

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return '#10b981';
      case 'degraded': return '#f59e0b';
      case 'down': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getActionTypeIcon = (actionType) => {
    switch (actionType) {
      case 'incoming_call': return '📞';
      case 'incoming_text': return '💬';
      case 'appointment_booked': return '📅';
      case 'faq_answered': return '❓';
      case 'lead_prescreened': return '👤';
      case 'escalated': return '⚠️';
      default: return '📋';
    }
  };

  if (loading) {
    return (
      <div className="ai-receptionist-dashboard">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading AI Receptionist Dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-receptionist-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <h1>🤖 AI Receptionist Dashboard</h1>
          <p className="subtitle">Real-time monitoring of AI receptionist performance</p>
        </div>
        <div className="header-controls">
          <button
            className={`refresh-toggle ${autoRefresh ? 'active' : ''}`}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? '⏸ Pause' : '▶️ Auto-refresh'}
          </button>
          <button className="refresh-btn" onClick={fetchDashboardData}>
            🔄 Refresh Now
          </button>
        </div>
      </div>

      {/* Realtime Metrics Cards */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon">💬</div>
          <div className="metric-content">
            <div className="metric-label">Conversations Today</div>
            <div className="metric-value">{realtimeMetrics?.conversations_today || 0}</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon">📅</div>
          <div className="metric-content">
            <div className="metric-label">Appointments Booked</div>
            <div className="metric-value">{realtimeMetrics?.appointments_today || 0}</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon">🎯</div>
          <div className="metric-content">
            <div className="metric-label">AI Coverage</div>
            <div className="metric-value">{realtimeMetrics?.ai_coverage_percentage?.toFixed(1) || 0}%</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon">⚠️</div>
          <div className="metric-content">
            <div className="metric-label">Errors Today</div>
            <div className="metric-value error">{realtimeMetrics?.errors_today || 0}</div>
          </div>
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
          className={`tab ${activeTab === 'skills' ? 'active' : ''}`}
          onClick={() => setActiveTab('skills')}
        >
          Skills Performance
        </button>
        <button
          className={`tab ${activeTab === 'roi' ? 'active' : ''}`}
          onClick={() => setActiveTab('roi')}
        >
          ROI & Impact
        </button>
        <button
          className={`tab ${activeTab === 'errors' ? 'active' : ''}`}
          onClick={() => setActiveTab('errors')}
        >
          Error Log {errors.length > 0 && <span className="badge">{errors.length}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'health' ? 'active' : ''}`}
          onClick={() => setActiveTab('health')}
        >
          System Health
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="email-layout">
              {/* Call List (Left Side) */}
              <div className="call-inbox">
                <div className="inbox-header">
                  <h3>📞 Recent Calls</h3>
                  <span className="call-count">{activityFeed.length}</span>
                </div>
                <div className="inbox-list">
                  {activityFeed.length === 0 ? (
                    <div className="empty-inbox">
                      <p>No calls yet. Waiting for AI receptionist activity...</p>
                    </div>
                  ) : (
                    activityFeed.map((call) => (
                      <div
                        key={call.id}
                        className={`inbox-item ${selectedCall?.id === call.id ? 'selected' : ''}`}
                        onClick={() => setSelectedCall(call)}
                      >
                        <div className="inbox-item-header">
                          <span className="call-icon">{getActionTypeIcon(call.action_type)}</span>
                          <span className="call-type-compact">{call.action_type.replace(/_/g, ' ').toUpperCase()}</span>
                          <span className="call-time-compact">{formatTimestamp(call.timestamp)}</span>
                        </div>
                        <div className="inbox-item-meta">
                          <span className="call-client-compact">
                            {call.client_name || 'Unknown Caller'}
                          </span>
                          <div className={`status-dot status-${call.outcome_status}`}></div>
                        </div>
                        {call.client_phone && (
                          <div className="call-preview">{call.client_phone}</div>
                        )}
                        {call.confidence_score && (
                          <div className="confidence-preview">
                            Confidence: {(call.confidence_score * 100).toFixed(0)}%
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Call Detail (Right Side) */}
              <div className="call-detail-pane">
                {selectedCall ? (
                  <>
                    <div className="detail-header">
                      <div className="detail-title-section">
                        <div className="detail-source">
                          <span className="source-icon-large">{getActionTypeIcon(selectedCall.action_type)}</span>
                          <span className="source-name">{selectedCall.action_type.replace(/_/g, ' ')}</span>
                        </div>
                        <h2 className="detail-title">
                          {selectedCall.client_name || 'Unknown Caller'}
                        </h2>
                        {selectedCall.client_phone && (
                          <p className="detail-subtitle">{selectedCall.client_phone}</p>
                        )}
                      </div>
                      <div className="detail-timestamp">
                        {new Date(selectedCall.timestamp).toLocaleString()}
                      </div>
                    </div>

                    <div className="detail-body">
                      {/* Call Information */}
                      <div className="detail-section">
                        <h3>📋 Call Information</h3>
                        <div className="detail-info-grid">
                          <div className="info-item">
                            <span className="info-label">Type:</span>
                            <span className="info-value">{selectedCall.action_type.replace(/_/g, ' ')}</span>
                          </div>
                          <div className="info-item">
                            <span className="info-label">Status:</span>
                            <span className={`info-value status-badge status-${selectedCall.outcome_status}`}>
                              {selectedCall.outcome_status}
                            </span>
                          </div>
                          {selectedCall.confidence_score && (
                            <div className="info-item">
                              <span className="info-label">Confidence:</span>
                              <span className="info-value">{(selectedCall.confidence_score * 100).toFixed(0)}%</span>
                            </div>
                          )}
                          {selectedCall.duration && (
                            <div className="info-item">
                              <span className="info-label">Duration:</span>
                              <span className="info-value">{selectedCall.duration}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Call Summary */}
                      {selectedCall.summary && (
                        <div className="detail-section">
                          <h3>📝 Summary</h3>
                          <div className="detail-content">
                            <p>{selectedCall.summary}</p>
                          </div>
                        </div>
                      )}

                      {/* Conversation Transcript */}
                      {selectedCall.transcript && (
                        <div className="detail-section">
                          <h3>💬 Transcript</h3>
                          <div className="detail-content transcript">
                            <p>{selectedCall.transcript}</p>
                          </div>
                        </div>
                      )}

                      {/* AI Actions Taken */}
                      {selectedCall.ai_actions && (
                        <div className="detail-section">
                          <h3>🤖 AI Actions</h3>
                          <div className="detail-content">
                            <ul className="actions-list">
                              {selectedCall.ai_actions.split(',').map((action, idx) => (
                                <li key={idx}>{action.trim()}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      )}

                      {/* Outcome */}
                      <div className="detail-section">
                        <h3>✅ Outcome</h3>
                        <div className="detail-content">
                          <div className={`outcome-badge outcome-${selectedCall.outcome_status}`}>
                            {selectedCall.outcome_status}
                          </div>
                          {selectedCall.outcome_description && (
                            <p className="outcome-description">{selectedCall.outcome_description}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="detail-empty">
                    <p>Select a call to view details</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Skills Performance Tab */}
        {activeTab === 'skills' && (
          <div className="skills-tab">
            <h2>🎯 AI Skills Performance</h2>
            <div className="skills-grid">
              {skills.length === 0 ? (
                <div className="empty-state">No skills data available</div>
              ) : (
                skills.map((skill) => (
                  <div key={skill.id} className="skill-card">
                    <div className="skill-header">
                      <h3>{skill.skill_name}</h3>
                      {skill.needs_retraining && <span className="warning-badge">⚠️ Needs Training</span>}
                    </div>
                    <div className="skill-category">{skill.skill_category}</div>
                    <div className="skill-metrics">
                      <div className="skill-metric">
                        <div className="metric-label">Accuracy</div>
                        <div className="metric-value">{(skill.accuracy_score * 100).toFixed(1)}%</div>
                      </div>
                      <div className="skill-metric">
                        <div className="metric-label">Usage Count</div>
                        <div className="metric-value">{skill.usage_count}</div>
                      </div>
                    </div>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{
                          width: `${skill.accuracy_score * 100}%`,
                          backgroundColor: skill.accuracy_score > 0.8 ? '#10b981' : skill.accuracy_score > 0.6 ? '#f59e0b' : '#ef4444'
                        }}
                      ></div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ROI Tab */}
        {activeTab === 'roi' && roi && (
          <div className="roi-tab">
            <h2>💰 Business Impact & ROI</h2>
            <div className="roi-grid">
              <div className="roi-card large">
                <div className="roi-icon">📈</div>
                <div className="roi-content">
                  <div className="roi-label">ROI Percentage</div>
                  <div className="roi-value">{roi.roi_percentage?.toFixed(1) || 0}%</div>
                </div>
              </div>

              <div className="roi-card">
                <div className="roi-icon">💵</div>
                <div className="roi-content">
                  <div className="roi-label">Estimated Revenue</div>
                  <div className="roi-value">${roi.estimated_revenue?.toLocaleString() || 0}</div>
                </div>
              </div>

              <div className="roi-card">
                <div className="roi-icon">⏱️</div>
                <div className="roi-content">
                  <div className="roi-label">Labor Hours Saved</div>
                  <div className="roi-value">{roi.saved_labor_hours?.toFixed(1) || 0}h</div>
                </div>
              </div>

              <div className="roi-card">
                <div className="roi-icon">📞</div>
                <div className="roi-content">
                  <div className="roi-label">Missed Calls Prevented</div>
                  <div className="roi-value">{roi.saved_missed_calls || 0}</div>
                </div>
              </div>

              <div className="roi-card">
                <div className="roi-icon">📅</div>
                <div className="roi-content">
                  <div className="roi-label">Total Appointments</div>
                  <div className="roi-value">{roi.total_appointments || 0}</div>
                </div>
              </div>

              <div className="roi-card">
                <div className="roi-icon">💲</div>
                <div className="roi-content">
                  <div className="roi-label">Cost Per Interaction</div>
                  <div className="roi-value">${roi.cost_per_interaction?.toFixed(2) || 0}</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Errors Tab */}
        {activeTab === 'errors' && (
          <div className="errors-tab">
            <h2>🚨 Error Log</h2>
            <div className="errors-list">
              {errors.length === 0 ? (
                <div className="empty-state success">
                  ✅ No errors reported - AI is running smoothly!
                </div>
              ) : (
                errors.map((error) => (
                  <div key={error.id} className={`error-card severity-${error.severity}`}>
                    <div className="error-header">
                      <span className="error-type">{error.error_type}</span>
                      <span className="error-severity">{error.severity}</span>
                      <span className="error-time">{formatTimestamp(error.timestamp)}</span>
                    </div>
                    <div className="error-context">{error.context}</div>
                    {error.conversation_snippet && (
                      <div className="error-snippet">
                        <strong>Conversation:</strong> {error.conversation_snippet}
                      </div>
                    )}
                    <div className="error-footer">
                      <span className={`error-status ${error.resolution_status}`}>
                        {error.resolution_status}
                      </span>
                      {error.needs_human_review && (
                        <span className="review-badge">👁️ Needs Review</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* System Health Tab */}
        {activeTab === 'health' && (
          <div className="health-tab">
            <h2>💚 System Health</h2>
            <div className="health-grid">
              {systemHealth.length === 0 ? (
                <div className="empty-state">No health data available</div>
              ) : (
                systemHealth.map((component) => (
                  <div key={component.component_name} className="health-card">
                    <div className="health-header">
                      <div className="component-name">{component.component_name.replace('_', ' ')}</div>
                      <div
                        className="status-indicator"
                        style={{ backgroundColor: getStatusColor(component.status) }}
                      >
                        {component.status}
                      </div>
                    </div>
                    <div className="health-metrics">
                      {component.latency_ms && (
                        <div className="health-metric">
                          <span className="label">Latency:</span>
                          <span className="value">{component.latency_ms}ms</span>
                        </div>
                      )}
                      {component.uptime_percentage && (
                        <div className="health-metric">
                          <span className="label">Uptime:</span>
                          <span className="value">{component.uptime_percentage.toFixed(2)}%</span>
                        </div>
                      )}
                      {component.error_rate !== null && (
                        <div className="health-metric">
                          <span className="label">Error Rate:</span>
                          <span className="value">{component.error_rate.toFixed(2)}%</span>
                        </div>
                      )}
                    </div>
                    <div className="health-timestamp">
                      Last checked: {formatTimestamp(component.last_checked)}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AIReceptionistDashboard;
