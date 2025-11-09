import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './Dashboard.css';

function Dashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  // Dashboard data states
  const [prioritizedTasks, setPrioritizedTasks] = useState([]);
  const [pipelineStats, setPipelineStats] = useState([]);
  const [production, setProduction] = useState({});
  const [leadMetrics, setLeadMetrics] = useState({});
  const [loanIssues, setLoanIssues] = useState([]);
  const [aiTasks, setAiTasks] = useState({ pending: [], waiting: [] });
  const [referralStats, setReferralStats] = useState({});
  const [teamStats, setTeamStats] = useState({});
  const [messages, setMessages] = useState([]);
  const [efficiency, setEfficiency] = useState({});

  // Drag and drop state
  const [draggedIndex, setDraggedIndex] = useState(null);
  const [containerOrder, setContainerOrder] = useState([
    'ai-alerts',
    'production-tracker',
    'efficiency',
    'ai-tasks',
    'pipeline',
    'referrals',
    'team',
    'messages'
  ]);

  useEffect(() => {
    loadDashboard();
    loadContainerOrder();
  }, []);

  // Load saved container order
  const loadContainerOrder = () => {
    try {
      const saved = localStorage.getItem('dashboardOrder');
      if (saved) {
        setContainerOrder(JSON.parse(saved));
      }
    } catch (error) {
      console.error('Failed to load container order:', error);
    }
  };

  // Save container order
  const saveContainerOrder = (order) => {
    try {
      localStorage.setItem('dashboardOrder', JSON.stringify(order));
    } catch (error) {
      console.error('Failed to save container order:', error);
    }
  };

  // Load Goal Tracker data
  const loadGoalTrackerData = () => {
    try {
      const savedInputs = localStorage.getItem('goalTrackerInputs');
      if (savedInputs) {
        const inputs = JSON.parse(savedInputs);
        const annualClosingsUnitGoal = inputs.annualClosingsDollarGoal / inputs.avgLoanAmount;
        const annualOriginationUnitGoal = annualClosingsUnitGoal / inputs.pullThroughRate;
        const monthlyUnitsGoal = annualOriginationUnitGoal / 12;
        const weeklyUnitsGoal = annualOriginationUnitGoal / 52;
        const dailyUnitsGoal = weeklyUnitsGoal / 5;

        return {
          annualGoal: annualOriginationUnitGoal,
          monthlyGoal: monthlyUnitsGoal,
          weeklyGoal: weeklyUnitsGoal,
          dailyGoal: dailyUnitsGoal,
        };
      }
    } catch (error) {
      console.error('Failed to load goal tracker data:', error);
    }
    return { annualGoal: 222, monthlyGoal: 18.5, weeklyGoal: 5, dailyGoal: 1 };
  };

  const loadDashboard = async () => {
    try {
      setLoading(true);

      // Fetch real data from backend
      const API_URL = process.env.REACT_APP_API_URL || '';
      const response = await fetch(`${API_URL}/api/v1/dashboard`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch dashboard data');
      }

      const data = await response.json();

      // Set all data from backend
      setPrioritizedTasks(data.prioritized_tasks || []);
      setPipelineStats(data.pipeline_stats || []);
      setProduction(data.production || {});
      setLeadMetrics(data.lead_metrics || {});
      setLoanIssues(data.loan_issues || []);
      setAiTasks(data.ai_tasks || { pending: [], waiting: [] });
      setReferralStats(data.referral_stats || {});
      setTeamStats(data.team_stats || {});
      setMessages(data.messages || []);
      setEfficiency(data.efficiency || {});

    } catch (error) {
      console.error('Failed to load dashboard:', error);
      // Fallback to mock data on error
      const goals = loadGoalTrackerData();
      setPrioritizedTasks(mockPrioritizedTasks());
      setPipelineStats(mockPipelineStats());
      setProduction(mockProduction(goals));
      setLeadMetrics(mockLeadMetrics());
      setLoanIssues(mockLoanIssues());
      setAiTasks(mockAiTasks());
      setReferralStats(mockReferralStats());
      setTeamStats(mockTeamStats());
      setMessages(mockMessages());
      setEfficiency(mockEfficiency());
    } finally {
      setLoading(false);
    }
  };

  // Drag handlers
  const handleDragStart = (index) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e, index) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;

    const newOrder = [...containerOrder];
    const draggedItem = newOrder[draggedIndex];
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(index, 0, draggedItem);

    setContainerOrder(newOrder);
    setDraggedIndex(index);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    saveContainerOrder(containerOrder);
  };

  const getAggregatedTasksCount = () => {
    let count = 0;
    count += prioritizedTasks.length;
    count += loanIssues.length;
    count += aiTasks.pending.length;
    count += aiTasks.waiting.length;
    count += (leadMetrics.alerts || []).length;
    count += messages.filter(m => !m.read).length;
    return count;
  };

  const formatGoalNumber = (value) => {
    if (!value) return '0.00';
    return Number(value).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  };

  // Render draggable containers
  const renderDraggableContainer = (containerId, index) => {
    const isDragging = draggedIndex === index;

    if (containerId === 'ai-alerts') {
      return (
        <div
          key={containerId}
          className={`ai-alerts-container draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="ai-alerts-header">
            <span className="alerts-icon">🚨</span>
            <h3>AI Alerts</h3>
          </div>
          <div className="ai-alerts-list">
            {leadMetrics.alerts && leadMetrics.alerts.filter(a => a).map((alert, idx) => (
              <div key={idx} className="ai-alert-row">
                <span className="alert-bullet">●</span>
                <span className="alert-text">{alert}</span>
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (containerId === 'production-tracker') {
      return (
        <div
          key={containerId}
          className={`dashboard-block production-tracker-block-standalone draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header clickable-block" onClick={() => navigate('/goal-tracker')}>
            <h2>💰 Monthly Production Tracker</h2>
          </div>
          <div className="production-kpis">
            <div className="kpi-card">
              <div className="kpi-label">Annual Origination Goal</div>
              <div className="kpi-values">
                <div className="kpi-row">
                  <span className="kpi-caption">Goal:</span>
                  <span className="kpi-number">{formatGoalNumber(production.annualGoal)}</span>
                </div>
                <div className="kpi-row">
                  <span className="kpi-caption">Actual:</span>
                  <span className="kpi-number highlight">{formatGoalNumber(production.annualActual)}</span>
                </div>
                <div className="kpi-progress-bar">
                  <div className="kpi-progress-fill" style={{ width: `${production.annualProgress || 0}%` }}></div>
                </div>
                <div className="kpi-percentage">{production.annualProgress || 0}% of Goal</div>
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Monthly Units Goal</div>
              <div className="kpi-values">
                <div className="kpi-row">
                  <span className="kpi-caption">Goal:</span>
                  <span className="kpi-number">{formatGoalNumber(production.monthlyGoal)}</span>
                </div>
                <div className="kpi-row">
                  <span className="kpi-caption">Actual:</span>
                  <span className="kpi-number highlight">{formatGoalNumber(production.monthlyActual)}</span>
                </div>
                <div className="kpi-progress-bar">
                  <div className="kpi-progress-fill" style={{ width: `${production.monthlyProgress || 0}%` }}></div>
                </div>
                <div className="kpi-percentage">{production.monthlyProgress || 0}% of Goal</div>
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Weekly Units Goal</div>
              <div className="kpi-values">
                <div className="kpi-row">
                  <span className="kpi-caption">Goal:</span>
                  <span className="kpi-number">{formatGoalNumber(production.weeklyGoal)}</span>
                </div>
                <div className="kpi-row">
                  <span className="kpi-caption">Actual:</span>
                  <span className="kpi-number highlight">{formatGoalNumber(production.weeklyActual)}</span>
                </div>
                <div className="kpi-progress-bar">
                  <div className="kpi-progress-fill" style={{ width: `${production.weeklyProgress || 0}%` }}></div>
                </div>
                <div className="kpi-percentage">{production.weeklyProgress || 0}% of Goal</div>
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Daily Units Goal</div>
              <div className="kpi-values">
                <div className="kpi-row">
                  <span className="kpi-caption">Goal:</span>
                  <span className="kpi-number">{formatGoalNumber(production.dailyGoal)}</span>
                </div>
                <div className="kpi-row">
                  <span className="kpi-caption">Actual:</span>
                  <span className="kpi-number highlight">{formatGoalNumber(production.dailyActual)}</span>
                </div>
                <div className="kpi-progress-bar">
                  <div className="kpi-progress-fill" style={{ width: `${production.dailyProgress || 0}%` }}></div>
                </div>
                <div className="kpi-percentage">{production.dailyProgress || 0}% of Goal</div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (containerId === 'efficiency') {
      return (
        <div
          key={containerId}
          className={`dashboard-block efficiency-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header">
            <h2>📊 Loan Efficiency Monitor</h2>
          </div>

          {/* Summary Bar */}
          <div className="efficiency-summary">
            <div className="efficiency-score-display">
              <div className="score-number">{efficiency.overallScore || 0}</div>
              <div className="score-label">Pipeline Efficiency</div>
              <div className={`score-trend ${(efficiency.trend || 0) >= 0 ? 'up' : 'down'}`}>
                {(efficiency.trend || 0) >= 0 ? '↑' : '↓'} {Math.abs(efficiency.trend || 0)}% (7 days)
              </div>
            </div>
          </div>

          {/* Three Mini-Cards */}
          <div className="efficiency-cards">
            {/* Stage Efficiency */}
            <div className="efficiency-card stage-efficiency">
              <h4>Stage Efficiency</h4>
              <div className="stage-bars">
                {(efficiency.stages || []).map((stage, idx) => (
                  <div key={idx} className="stage-bar-row">
                    <span className="stage-name">{stage.name}</span>
                    <div className="stage-bar-container">
                      <div
                        className={`stage-bar ${stage.status}`}
                        style={{ width: `${stage.efficiency}%` }}
                      ></div>
                    </div>
                    <span className="stage-percent">{stage.efficiency}%</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Team Efficiency */}
            <div className="efficiency-card team-efficiency">
              <h4>Team Efficiency</h4>
              <div className="team-roles">
                {(efficiency.team || []).map((role, idx) => (
                  <div key={idx} className="team-role-row">
                    <span className="role-name">{role.role}</span>
                    <div className="role-bar-container">
                      <div
                        className={`role-bar ${role.performance >= 80 ? 'high' : role.performance >= 60 ? 'medium' : 'low'}`}
                        style={{ width: `${role.performance}%` }}
                      ></div>
                    </div>
                    <span className="role-percent">{role.performance}%</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Bottlenecks */}
            <div className="efficiency-card bottlenecks">
              <h4>Active Bottlenecks</h4>
              <div className="bottleneck-count">{efficiency.bottleneckCount || 0}</div>
              <div className="bottleneck-list">
                {(efficiency.bottlenecks || []).slice(0, 3).map((bottleneck, idx) => (
                  <div key={idx} className="bottleneck-item">
                    <span className="bottleneck-icon">⚠️</span>
                    <span className="bottleneck-text">{bottleneck}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* View Full Report Button */}
          <button
            className="btn-view-efficiency"
            onClick={() => navigate('/dashboard/efficiency')}
          >
            View Full Efficiency Report →
          </button>
        </div>
      );
    }

    if (containerId === 'ai-tasks') {
      return (
        <div
          key={containerId}
          className={`dashboard-block ai-tasks-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header clickable-block" onClick={() => navigate('/tasks')}>
            <h2>🎯 AI Prioritized Tasks (Today)</h2>
            <span className="task-count">{getAggregatedTasksCount()} tasks</span>
          </div>
          <div className="task-summary-view">
            <div className="task-count-display">
              <div className="count-number">{getAggregatedTasksCount()}</div>
              <div className="count-label">Outstanding Tasks</div>
            </div>
            <div className="click-to-view">
              <p>Click to view all tasks →</p>
            </div>
          </div>
        </div>
      );
    }

    if (containerId === 'pipeline') {
      return (
        <div
          key={containerId}
          className={`dashboard-block pipeline-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header">
            <h2>💼 Live Loan Pipeline</h2>
          </div>
          <div className="pipeline-table">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Count</th>
                  <th>Alerts</th>
                  <th>Funding $</th>
                </tr>
              </thead>
              <tbody>
                {pipelineStats.filter(stage => stage && stage.name).map((stage, stageIndex) => (
                  <tr
                    key={stageIndex}
                    onClick={() => navigate(`/loans?stage=${stage.id}`)}
                    className="clickable-row"
                  >
                    <td><strong>{stage.name}</strong></td>
                    <td>{stage.count}</td>
                    <td>
                      {stage.alerts > 0 && (
                        <span className="alert-count">{stage.alerts} {stage.alert_text}</span>
                      )}
                      {stage.alerts === 0 && <span className="no-issues">no issues</span>}
                    </td>
                    <td>
                      {stage.volume ? (
                        <strong>${(stage.volume / 1000000).toFixed(1)}M</strong>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
    }

    if (containerId === 'referrals') {
      return (
        <div
          key={containerId}
          className={`dashboard-block referrals-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header">
            <h2>🤝 Referral Scoreboard</h2>
          </div>
          <div className="referrals-content">
            <div className="referral-stats-grid">
              {referralStats.top_partners && referralStats.top_partners.filter(p => p && p.name).map((partner, idx) => (
                <div key={idx} className="partner-card">
                  <div className="partner-name">{partner.name}</div>
                  <div className="partner-stats">
                    <span className="received">↓ {partner.received} received</span>
                    <span className="sent">↑ {partner.sent} sent</span>
                  </div>
                  {partner.balance !== 0 && (
                    <div className="balance-alert">
                      {partner.balance > 0
                        ? `You owe ${partner.balance} referral${partner.balance > 1 ? 's' : ''}`
                        : `Owes you ${Math.abs(partner.balance)} referral${Math.abs(partner.balance) > 1 ? 's' : ''}`
                      }
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="engagement-heatmap">
              <h4>Partner Engagement</h4>
              {referralStats.engagement && referralStats.engagement.filter(i => i && i.partner).map((item, idx) => (
                <div key={idx} className="engagement-item">
                  <span className="partner">{item.partner}</span>
                  <span className="last-contact">{item.last_contact}</span>
                  <span className="ai-suggestion">{item.suggestion}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (containerId === 'team' && teamStats.has_team) {
      return (
        <div
          key={containerId}
          className={`dashboard-block team-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header">
            <h2>👥 Team Performance</h2>
          </div>
          <div className="team-content">
            <div className="team-metrics">
              <div className="team-metric">
                <div className="metric-label">Processor Workload</div>
                <div className="metric-value">{teamStats.avg_workload} files/person</div>
              </div>
              <div className="team-metric">
                <div className="metric-label">Task Backlog</div>
                <div className="metric-value warn">{teamStats.backlog}</div>
              </div>
              <div className="team-metric">
                <div className="metric-label">SLA Missed</div>
                <div className="metric-value">{teamStats.sla_missed}</div>
              </div>
            </div>
            <div className="ai-coaching">
              <div className="coaching-title">🎓 AI Coaching Insights</div>
              {teamStats.insights && teamStats.insights.filter(i => i).map((insight, idx) => (
                <div key={idx} className="coaching-insight">
                  <span className="insight-icon">💡</span>
                  {insight}
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (containerId === 'messages') {
      return (
        <div
          key={containerId}
          className={`dashboard-block messages-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header">
            <h2>📬 Unified Messages</h2>
            <span className="unread-count">{messages.filter(m => !m.read).length} unread</span>
          </div>
          <div className="messages-list">
            {messages.filter(msg => msg && msg.from).slice(0, 6).map((msg, idx) => (
              <div key={msg.id || idx} className={`message-item ${!msg.read ? 'unread' : ''} ${msg.requires_response ? 'needs-response' : ''}`}>
                <div className="message-left">
                  <div className="message-type-icon">{msg.type_icon}</div>
                  <div className="message-content">
                    <div className="message-header">
                      <div className="message-from-line">
                        <span className="message-from">{msg.from}</span>
                        <span className="message-client-type">{msg.client_type}</span>
                      </div>
                      <div className="message-meta">
                        <span className="message-source">{msg.source}</span>
                        <span className="message-timestamp">{msg.timestamp}</span>
                      </div>
                    </div>
                    <div className="message-preview">{msg.preview}</div>
                    {msg.ai_summary && (
                      <div className="ai-summary">
                        <span className="ai-icon">🤖</span>
                        <span className="ai-text">{msg.ai_summary}</span>
                      </div>
                    )}
                    {msg.task_created && (
                      <div className="task-status">
                        <span className="task-badge">✓ Task Created: {msg.task_id}</span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="message-actions">
                  {msg.type === 'voicemail' && (
                    <button className="btn-icon-sm" title="Play Voicemail">
                      <span className="voicemail-duration">{msg.duration}</span> ▶️
                    </button>
                  )}
                  {msg.type === 'email' && (
                    <button className="btn-icon-sm" title="View in Outlook">📧</button>
                  )}
                  {msg.type === 'text' && (
                    <button className="btn-icon-sm" title="View in Teams">💬</button>
                  )}
                  <button className="btn-icon-sm btn-reply" title="Reply">↩️</button>
                  <button className="btn-icon-sm" title="AI Suggested Response">🤖</button>
                </div>
              </div>
            ))}
          </div>
          <button className="btn-view-all" onClick={() => navigate('/assistant')}>
            View All Messages →
          </button>
        </div>
      );
    }

    return null;
  };

  if (loading) {
    return (
      <div className="dashboard">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Loading your command center...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header-compact">
        <h1>
          Today's Command Center{' '}
          <span className="task-count-badge">({getAggregatedTasksCount()})</span>
        </h1>
        <div className="header-date">
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </div>
      </div>

      {/* Draggable Containers */}
      <div className="draggable-containers-wrapper">
        {containerOrder.map((containerId, index) => renderDraggableContainer(containerId, index))}
      </div>
    </div>
  );
}

// Mock data functions
const mockPrioritizedTasks = () => [
  {
    title: 'Follow up on pre-approval',
    borrower: 'Sarah Johnson',
    stage: 'Pre-Approved',
    urgency: 'high',
    ai_action: 'AI can send follow-up email — approve?'
  },
  {
    title: 'Upload missing documents',
    borrower: 'Mike Chen',
    stage: 'Processing',
    urgency: 'critical',
    ai_action: null
  },
  {
    title: 'Schedule appraisal',
    borrower: 'Emily Davis',
    stage: 'Application Complete',
    urgency: 'medium',
    ai_action: 'AI can schedule appraisal — approve?'
  }
];

const mockPipelineStats = () => [
  { id: 'new', name: 'New Leads', count: 12, alerts: 3, alert_text: 'follow-ups', volume: null },
  { id: 'preapproved', name: 'Pre-Approved', count: 18, alerts: 2, alert_text: 'docs needed', volume: null },
  { id: 'processing', name: 'In Processing', count: 11, alerts: 4, alert_text: 'delayed', volume: 4100000 },
  { id: 'underwriting', name: 'In Underwriting', count: 7, alerts: 1, alert_text: 'suspended', volume: 2800000 },
  { id: 'ctc', name: 'Clear to Close', count: 4, alerts: 0, alert_text: '', volume: 1300000 },
  { id: 'funded', name: 'Funded This Month', count: 9, alerts: 0, alert_text: '', volume: 3400000 }
];

const mockProduction = (goals = {}) => {
  const annualGoal = goals.annualGoal || 222;
  const monthlyGoal = goals.monthlyGoal || 18.5;
  const weeklyGoal = goals.weeklyGoal || 5;
  const dailyGoal = goals.dailyGoal || 1;

  const annualActual = 189;
  const monthlyActual = 14;
  const weeklyActual = 4;
  const dailyActual = 1;

  const annualProgress = Math.round((annualActual / annualGoal) * 100);
  const monthlyProgress = Math.round((monthlyActual / monthlyGoal) * 100);
  const weeklyProgress = Math.round((weeklyActual / weeklyGoal) * 100);
  const dailyProgress = Math.round((dailyActual / dailyGoal) * 100);

  return {
    funded: 9,
    projected: 14,
    volume: 3400000,
    target: 6000000,
    progress: 57,
    ai_projection: 5900000,
    projection_change: 12,
    annualGoal,
    annualActual,
    annualProgress,
    monthlyGoal,
    monthlyActual,
    monthlyProgress,
    weeklyGoal,
    weeklyActual,
    weeklyProgress,
    dailyGoal,
    dailyActual,
    dailyProgress,
  };
};

const mockLeadMetrics = () => ({
  new_today: 3,
  avg_contact_time: 1.2,
  conversion_rate: 23,
  hot_leads: 5,
  alerts: [
    '3 leads haven\'t been contacted in 24 hours.',
    '2 leads showed high buying intent in email.',
    'A referral partner sent you a lead and you haven\'t responded.'
  ]
});

const mockLoanIssues = () => [
  {
    borrower: 'John Smith',
    issue: 'Appraisal delay',
    time_remaining: '2 days',
    time_color: '#f59e0b',
    action: 'Follow up'
  },
  {
    borrower: 'Jane Doe',
    issue: 'Insurance missing',
    time_remaining: '5 hours',
    time_color: '#dc2626',
    action: 'Send reminder'
  }
];

const mockAiTasks = () => ({
  pending: [
    {
      id: 1,
      task: 'Draft follow-up email to Sarah Johnson',
      confidence: 94,
      what_ai_did: 'Composed personalized email based on last conversation'
    },
    {
      id: 2,
      task: 'Schedule appointment with Mike Chen',
      confidence: 87,
      what_ai_did: 'Found mutual availability on calendar for Thursday 2pm'
    }
  ],
  waiting: [
    { task: 'Approve rate lock for Emily Davis file' },
    { task: 'Review updated credit report for John Smith' }
  ]
});

const mockReferralStats = () => ({
  top_partners: [
    { name: 'Amy Smith (Realtor)', received: 8, sent: 7, balance: 1 },
    { name: 'Bob Johnson (Builder)', received: 5, sent: 6, balance: -1 }
  ],
  engagement: [
    { partner: 'Amy Smith', last_contact: '3 days ago', suggestion: 'Send update on Jane Doe\'s file' }
  ]
});

const mockTeamStats = () => ({
  has_team: true,
  avg_workload: 8,
  backlog: 23,
  sla_missed: 2,
  insights: [
    'You lose 18% of leads between docs requested → docs received.',
    'Your turn time on disclosures is 40% slower than peers.'
  ]
});

const mockMessages = () => [
  {
    id: 1,
    type: 'email',
    type_icon: '📧',
    from: 'Sarah Johnson',
    client_type: 'Active Loan',
    source: 'Outlook',
    preview: 'Quick question about my pre-approval...',
    full_message: 'Hi, I wanted to check on the expiration date for my pre-approval letter. Can you help?',
    ai_summary: 'Client asking about pre-approval expiration date - needs response by EOD',
    timestamp: '2 hours ago',
    read: false,
    task_created: true,
    task_id: 'TSK-1234',
    requires_response: true
  },
  {
    id: 2,
    type: 'text',
    type_icon: '💬',
    from: 'Mike Chen',
    client_type: 'Lead',
    source: 'Teams',
    preview: 'Thanks for the rate quote! When can we schedule a call?',
    full_message: 'Thanks for the rate quote! When can we schedule a call to discuss next steps?',
    ai_summary: 'Lead requesting callback to discuss loan options',
    timestamp: '4 hours ago',
    read: false,
    task_created: true,
    task_id: 'TSK-1235',
    requires_response: true
  },
  {
    id: 3,
    type: 'voicemail',
    type_icon: '🎤',
    from: 'Lisa Brown',
    client_type: 'Portfolio Client',
    source: 'Phone',
    preview: 'Voicemail (1:23) - Interested in refinancing...',
    full_message: '[Voicemail transcription] Hi, this is Lisa Brown. I saw rates dropped and wanted to talk about refinancing my mortgage. Please call me back at 555-0123.',
    ai_summary: 'Portfolio client interested in refinance opportunity - high priority',
    timestamp: '6 hours ago',
    read: false,
    task_created: true,
    task_id: 'TSK-1236',
    requires_response: true,
    duration: '1:23'
  },
  {
    id: 4,
    type: 'email',
    type_icon: '📧',
    from: 'Tom Wilson',
    client_type: 'Portfolio Client',
    source: 'Outlook',
    preview: 'Happy anniversary! Thanks for the card.',
    full_message: 'Thank you so much for remembering my home purchase anniversary! The card was very thoughtful.',
    ai_summary: 'Client thanking for anniversary card - positive relationship building',
    timestamp: '1 day ago',
    read: true,
    task_created: false,
    requires_response: false
  },
  {
    id: 5,
    type: 'text',
    type_icon: '💬',
    from: 'Jennifer Davis',
    client_type: 'Active Loan',
    source: 'Teams',
    preview: 'Just uploaded the bank statements you requested',
    full_message: 'Hi! I just uploaded my bank statements to the portal. Let me know if you need anything else.',
    ai_summary: 'Client uploaded required documents - verify completion',
    timestamp: '1 day ago',
    read: false,
    task_created: true,
    task_id: 'TSK-1237',
    requires_response: true
  },
  {
    id: 6,
    type: 'voicemail',
    type_icon: '🎤',
    from: 'Robert Kim',
    client_type: 'Lead',
    source: 'Phone',
    preview: 'Voicemail (0:45) - Returning your call...',
    full_message: '[Voicemail transcription] Hey, this is Robert Kim returning your call about the first-time homebuyer program. Give me a call when you can.',
    ai_summary: 'Lead returning call about first-time homebuyer program',
    timestamp: '2 days ago',
    read: true,
    task_created: false,
    requires_response: false,
    duration: '0:45'
  }
];

const mockEfficiency = () => ({
  overallScore: 78,
  trend: 5,
  stages: [
    { name: 'Lead Intake', efficiency: 92, status: 'on-track' },
    { name: 'Pre-Approval', efficiency: 85, status: 'on-track' },
    { name: 'Contract', efficiency: 78, status: 'slightly-delayed' },
    { name: 'Processing', efficiency: 65, status: 'behind' },
    { name: 'Underwriting', efficiency: 88, status: 'on-track' },
    { name: 'Conditions', efficiency: 58, status: 'behind' },
    { name: 'CTC', efficiency: 82, status: 'on-track' },
    { name: 'Closing', efficiency: 90, status: 'on-track' }
  ],
  team: [
    { role: 'Loan Officer', performance: 85 },
    { role: 'App Analyst', performance: 92 },
    { role: 'Processor', performance: 68 },
    { role: 'Concierge', performance: 88 }
  ],
  bottleneckCount: 8,
  bottlenecks: [
    '5 loans stuck in Conditions > 72 hours',
    '3 loans waiting on borrower docs',
    '2 loans with unreviewed appraisal reports'
  ]
});

export default Dashboard;
