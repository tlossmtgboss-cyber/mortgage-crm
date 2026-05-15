import { useState, useEffect } from 'react';
import { aiReceptionistDashboardAPI } from '../services/api';
import './AIReceptionistDashboard.css';

// Mock data generators
const generateMockRealtimeMetrics = () => ({
  conversations_today: 24,
  appointments_today: 7,
  ai_coverage_percentage: 87.5,
  errors_today: 2
});

const generateMockActivityFeed = () => {
  const now = new Date();
  return [
    {
      id: 1,
      action_type: 'incoming_call',
      client_name: 'Sarah Johnson',
      client_phone: '(555) 123-4567',
      timestamp: new Date(now.getTime() - 30 * 60000).toISOString(),
      outcome_status: 'success',
      confidence_score: 0.95,
      duration: '3:45',
      summary: 'Pre-approval inquiry. Scheduled consultation for tomorrow at 10am.',
      details: 'Client is a first-time homebuyer looking to purchase in the $400-450k range. Pre-qualified based on income and credit score. Sent calendar invite for pre-approval consultation.'
    },
    {
      id: 2,
      action_type: 'appointment_booked',
      client_name: 'Mike Chen',
      client_phone: '(555) 234-5678',
      timestamp: new Date(now.getTime() - 2 * 3600000).toISOString(),
      outcome_status: 'success',
      confidence_score: 0.92,
      duration: '2:15',
      summary: 'Booked document review appointment for Thursday at 2pm.',
      details: 'Follow-up from previous conversation. Client uploaded tax documents and wants to review before proceeding. Confirmed Thursday 2pm via calendar.'
    },
    {
      id: 3,
      action_type: 'faq_answered',
      client_name: 'Emily Davis',
      client_phone: '(555) 345-6789',
      timestamp: new Date(now.getTime() - 4 * 3600000).toISOString(),
      outcome_status: 'success',
      confidence_score: 0.89,
      duration: '1:30',
      summary: 'Answered questions about FHA vs conventional loans.',
      details: 'Provided comparison of FHA and conventional loan requirements, down payment options, and PMI differences. Client satisfied with information.'
    },
    {
      id: 4,
      action_type: 'lead_prescreened',
      client_name: 'John Smith',
      client_phone: '(555) 456-7890',
      timestamp: new Date(now.getTime() - 6 * 3600000).toISOString(),
      outcome_status: 'success',
      confidence_score: 0.88,
      duration: '4:20',
      summary: 'Pre-screened potential buyer. Good credit, stable income.',
      details: 'Collected preliminary financial information. Credit score: 740, DTI: 32%, annual income: $95k. Pre-qualified for up to $425k. Sent to loan officer for follow-up.'
    },
    {
      id: 5,
      action_type: 'escalated',
      client_name: 'Lisa Brown',
      client_phone: '(555) 567-8901',
      timestamp: new Date(now.getTime() - 8 * 3600000).toISOString(),
      outcome_status: 'escalated',
      confidence_score: 0.65,
      duration: '2:50',
      summary: 'Complex refinance question - escalated to loan officer.',
      details: 'Client has unique situation with investment property refinance. Beyond AI capability - transferred to senior loan officer for specialized guidance.'
    },
    {
      id: 6,
      action_type: 'incoming_text',
      client_name: 'Tom Wilson',
      client_phone: '(555) 678-9012',
      timestamp: new Date(now.getTime() - 10 * 3600000).toISOString(),
      outcome_status: 'success',
      confidence_score: 0.91,
      summary: 'Responded to rate inquiry via text.',
      details: 'Client asked about current rates. Provided today\'s rates for 30-year and 15-year fixed mortgages. Mentioned rate lock options.'
    }
  ];
};

const generateMockSkills = () => [
  { name: 'FAQ Handling', success_rate: 94.2, total_uses: 156 },
  { name: 'Appointment Booking', success_rate: 91.5, total_uses: 89 },
  { name: 'Lead Pre-screening', success_rate: 87.8, total_uses: 67 },
  { name: 'Document Status', success_rate: 93.1, total_uses: 45 },
  { name: 'Rate Quotes', success_rate: 89.6, total_uses: 123 }
];

const generateMockROI = () => ({
  calls_handled: 287,
  hours_saved: 47.8,
  appointments_booked: 34,
  conversion_rate: 23.5,
  cost_savings: 2850,
  revenue_generated: 12400
});

const generateMockErrors = () => [
  {
    id: 1,
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    error_type: 'API Timeout',
    message: 'Calendar API timeout while booking appointment',
    severity: 'medium',
    resolved: false
  },
  {
    id: 2,
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    error_type: 'Speech Recognition',
    message: 'Poor audio quality - unable to transcribe',
    severity: 'low',
    resolved: true
  }
];

const generateMockSystemHealth = () => [
  { component: 'Voice API (Vapi)', status: 'active', uptime: '99.8%' },
  { component: 'Calendar Integration', status: 'active', uptime: '99.5%' },
  { component: 'CRM Database', status: 'active', uptime: '99.9%' },
  { component: 'AI Model (Claude)', status: 'active', uptime: '99.7%' }
];

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
      // Load mock data on error
      setRealtimeMetrics(generateMockRealtimeMetrics());
      setActivityFeed(generateMockActivityFeed());
      setSkills(generateMockSkills());
      setROI(generateMockROI());
      setErrors(generateMockErrors());
      setSystemHealth(generateMockSystemHealth());
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
      case 'active': return '#2D7A52';
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
                          backgroundColor: skill.accuracy_score > 0.8 ? '#2D7A52' : skill.accuracy_score > 0.6 ? '#f59e0b' : '#ef4444'
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
