import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { dashboardAPI } from '../services/api';
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
  const [mumAlerts, setMumAlerts] = useState([]);
  const [teamStats, setTeamStats] = useState({});
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const data = await dashboardAPI.getDashboard();

      // Parse dashboard data with safe defaults
      setPrioritizedTasks((data.prioritized_tasks && data.prioritized_tasks.length > 0) ? data.prioritized_tasks : mockPrioritizedTasks());
      setPipelineStats((data.pipeline_stats && data.pipeline_stats.length > 0) ? data.pipeline_stats : mockPipelineStats());
      setProduction(data.production && typeof data.production === 'object' ? data.production : mockProduction());
      setLeadMetrics(data.lead_metrics && typeof data.lead_metrics === 'object' ? data.lead_metrics : mockLeadMetrics());
      setLoanIssues((data.loan_issues && data.loan_issues.length > 0) ? data.loan_issues : mockLoanIssues());
      setAiTasks(data.ai_tasks && typeof data.ai_tasks === 'object' ? data.ai_tasks : mockAiTasks());
      setReferralStats(data.referral_stats && typeof data.referral_stats === 'object' ? data.referral_stats : mockReferralStats());
      setMumAlerts((data.mum_alerts && data.mum_alerts.length > 0) ? data.mum_alerts.filter(a => a && a.icon) : mockMumAlerts());
      setTeamStats(data.team_stats && typeof data.team_stats === 'object' ? data.team_stats : mockTeamStats());
      setMessages((data.messages && data.messages.length > 0) ? data.messages : mockMessages());
    } catch (error) {
      console.error('Failed to load dashboard:', error);
      // Use mock data on error
      setPrioritizedTasks(mockPrioritizedTasks());
      setPipelineStats(mockPipelineStats());
      setProduction(mockProduction());
      setLeadMetrics(mockLeadMetrics());
      setLoanIssues(mockLoanIssues());
      setAiTasks(mockAiTasks());
      setReferralStats(mockReferralStats());
      setMumAlerts(mockMumAlerts());
      setTeamStats(mockTeamStats());
      setMessages(mockMessages());
    } finally {
      setLoading(false);
    }
  };

  const getUrgencyColor = (urgency) => {
    const colors = {
      'critical': '#dc2626',
      'high': '#f59e0b',
      'medium': '#3b82f6',
      'low': '#10b981'
    };
    return colors[urgency] || '#6b7280';
  };

  const handleApproveAiTask = async (taskId) => {
    // TODO: Implement AI task approval
    alert(`Approved task ${taskId}`);
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
        <h1>Today's Command Center</h1>
        <div className="header-date">
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </div>
      </div>

      <div className="dashboard-grid">
        {/* 1. AI PRIORITIZED TASKS */}
        <div className="dashboard-block ai-tasks-block">
          <div className="block-header">
            <h2>🎯 AI Prioritized Tasks (Today)</h2>
            <span className="task-count">{prioritizedTasks.length} tasks</span>
          </div>
          <div className="task-list">
            {prioritizedTasks.filter(task => task && task.title).map((task, index) => (
              <div key={index} className="task-item">
                <div className="task-main">
                  <div className="task-info">
                    <div className="task-title">{task.title}</div>
                    <div className="task-meta">
                      <span className="borrower-name">{task.borrower}</span>
                      <span className="task-stage">{task.stage}</span>
                    </div>
                  </div>
                  <div
                    className="urgency-badge"
                    style={{ backgroundColor: getUrgencyColor(task.urgency) }}
                  >
                    {task.urgency}
                  </div>
                </div>
                {task.ai_action && (
                  <div className="ai-suggestion">
                    <span className="ai-icon">🤖</span>
                    <span className="ai-text">{task.ai_action}</span>
                    <button className="btn-approve-sm">Approve</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 2. PIPELINE AT A GLANCE */}
        <div className="dashboard-block pipeline-block">
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
                {pipelineStats.filter(stage => stage && stage.name).map((stage, index) => (
                  <tr
                    key={index}
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

        {/* 3. MONEY BOARD */}
        <div className="dashboard-block money-block">
          <div className="block-header">
            <h2>💰 Monthly Production Tracker</h2>
          </div>
          <div className="money-stats">
            <div className="money-row">
              <div className="money-stat">
                <div className="money-label">Loans Funded</div>
                <div className="money-value">{production.funded}</div>
              </div>
              <div className="money-stat">
                <div className="money-label">Projected (AI)</div>
                <div className="money-value highlight">{production.projected}</div>
              </div>
              <div className="money-stat">
                <div className="money-label">Dollar Volume</div>
                <div className="money-value">${(production.volume / 1000000).toFixed(1)}M</div>
              </div>
            </div>
            <div className="target-bar">
              <div className="target-progress" style={{ width: `${production.progress}%` }}></div>
            </div>
            <div className="target-text">
              <span>{production.progress}% of monthly target</span>
              <span className="target-amount">${(production.target / 1000000).toFixed(1)}M</span>
            </div>
            <div className="ai-projection">
              🤖 <strong>AI Projection:</strong> Based on your current pipeline and conversion patterns,
              you're pacing to fund <strong>${(production.ai_projection / 1000000).toFixed(1)}M</strong> this month
              (<span className="positive">+{production.projection_change}%</span>)
            </div>
          </div>
        </div>

        {/* 4. LEADS & CONVERSION ENGINE */}
        <div className="dashboard-block leads-block">
          <div className="block-header">
            <h2>🚀 Leads & Conversion Engine</h2>
          </div>
          <div className="leads-metrics">
            <div className="metric-row">
              <div className="metric-item">
                <div className="metric-value">{leadMetrics.new_today}</div>
                <div className="metric-label">New Leads Today</div>
              </div>
              <div className="metric-item">
                <div className="metric-value">{leadMetrics.avg_contact_time}h</div>
                <div className="metric-label">Avg Time-to-Contact</div>
              </div>
              <div className="metric-item">
                <div className="metric-value">{leadMetrics.conversion_rate}%</div>
                <div className="metric-label">Leads → Apps</div>
              </div>
              <div className="metric-item">
                <div className="metric-value hot">{leadMetrics.hot_leads}</div>
                <div className="metric-label">Hot Leads (AI)</div>
              </div>
            </div>
            <div className="ai-alerts-section">
              <div className="ai-alert-title">🚨 AI Alerts</div>
              {leadMetrics.alerts && leadMetrics.alerts.filter(a => a).map((alert, idx) => (
                <div key={idx} className="ai-alert-item">
                  <span className="alert-dot"></span>
                  {alert}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 5. LOAN ISSUES & FIRE PREVENTION */}
        <div className="dashboard-block issues-block">
          <div className="block-header">
            <h2>🔥 Milestone Risk Alerts</h2>
            <span className="issue-count">{loanIssues.length} issues</span>
          </div>
          <div className="issues-list">
            {loanIssues.filter(issue => issue && issue.borrower).map((issue, index) => (
              <div key={index} className="issue-item">
                <div className="issue-main">
                  <div className="issue-borrower">{issue.borrower}</div>
                  <div className="issue-problem">{issue.issue}</div>
                </div>
                <div className="issue-details">
                  <div className="time-remaining" style={{ color: issue.time_color }}>
                    {issue.time_remaining}
                  </div>
                  <button className="btn-fix">{issue.action}</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 6. AI TASK ENGINE PANEL */}
        <div className="dashboard-block ai-engine-block">
          <div className="block-header">
            <h2>🤖 AI Task Engine</h2>
          </div>
          <div className="ai-engine-sections">
            <div className="ai-section">
              <h3>Pending Your Approval ({aiTasks.pending.length})</h3>
              {aiTasks.pending.filter(task => task && task.task).map((task, idx) => (
                <div key={idx} className="ai-task-card">
                  <div className="ai-task-header">
                    <span className="task-name">{task.task}</span>
                    <span className="confidence-badge">{task.confidence}% confident</span>
                  </div>
                  <div className="ai-task-description">{task.what_ai_did}</div>
                  <div className="ai-task-actions">
                    <button className="btn-approve" onClick={() => handleApproveAiTask(task.id)}>
                      ✓ Approve
                    </button>
                    <button className="btn-fix">Fix</button>
                    <button className="btn-coach">Coach AI</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="ai-section">
              <h3>Waiting for Your Input ({aiTasks.waiting.length})</h3>
              {aiTasks.waiting.filter(task => task && task.task).map((task, idx) => (
                <div key={idx} className="ai-task-simple">
                  <span className="task-text">{task.task}</span>
                  <div className="quick-actions">
                    <button className="btn-quick-approve">✓</button>
                    <button className="btn-quick-deny">✗</button>
                    <button className="btn-quick-delegate">→</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 7. REFERRALS & PARTNER HEALTH */}
        <div className="dashboard-block referrals-block">
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

        {/* 8. CLIENT FOR LIFE ENGINE (MUM) */}
        <div className="dashboard-block mum-block">
          <div className="block-header">
            <h2>♻️ Client for Life Engine (MUM)</h2>
            <span className="mum-count">{mumAlerts.length} actions</span>
          </div>
          <div className="mum-list">
            {mumAlerts.filter(alert => alert && alert.icon).map((alert, idx) => (
              <div key={idx} className="mum-item">
                <div className="mum-icon">{alert.icon}</div>
                <div className="mum-content">
                  <div className="mum-title">{alert.title}</div>
                  <div className="mum-client">{alert.client}</div>
                </div>
                <button className="btn-mum-action">{alert.action}</button>
              </div>
            ))}
          </div>
        </div>

        {/* 9. TEAM OPERATIONS */}
        {teamStats.has_team && (
          <div className="dashboard-block team-block">
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
        )}

        {/* 10. COMMUNICATION HUB */}
        <div className="dashboard-block messages-block">
          <div className="block-header">
            <h2>📬 Unified Messages</h2>
            <span className="unread-count">{messages.filter(m => !m.read).length} unread</span>
          </div>
          <div className="messages-list">
            {messages.filter(msg => msg && msg.from).slice(0, 5).map((msg, idx) => (
              <div key={idx} className={`message-item ${!msg.read ? 'unread' : ''}`}>
                <div className="message-type">{msg.type_icon}</div>
                <div className="message-content">
                  <div className="message-from">{msg.from}</div>
                  <div className="message-preview">{msg.preview}</div>
                  {msg.ai_summary && (
                    <div className="ai-summary">🤖 {msg.ai_summary}</div>
                  )}
                </div>
                <div className="message-actions">
                  <button className="btn-icon-sm" title="Reply">↩️</button>
                  <button className="btn-icon-sm" title="AI Response">🤖</button>
                  <button className="btn-icon-sm" title="Create Task">✓</button>
                </div>
              </div>
            ))}
          </div>
          <button className="btn-view-all" onClick={() => navigate('/assistant')}>
            View All Messages →
          </button>
        </div>
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

const mockProduction = () => ({
  funded: 9,
  projected: 14,
  volume: 3400000,
  target: 6000000,
  progress: 57,
  ai_projection: 5900000,
  projection_change: 12
});

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

const mockMumAlerts = () => [
  { icon: '📅', title: 'Annual review due', client: 'Tom Wilson', action: 'Schedule' },
  { icon: '📉', title: 'Rate drop opportunity', client: 'Lisa Brown', action: 'Send alert' },
  { icon: '🎂', title: 'Home anniversary', client: 'Mark Taylor', action: 'Send card' }
];

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
    type_icon: '📧',
    from: 'Sarah Johnson',
    preview: 'Quick question about my pre-approval...',
    ai_summary: 'Asking about pre-approval expiration date',
    read: false
  },
  {
    type_icon: '💬',
    from: 'Mike Chen',
    preview: 'Thanks for the update!',
    ai_summary: null,
    read: true
  }
];

export default Dashboard;
