import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './WorkflowStatusDetail.css';
import { getToken } from '../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

// All workflow statuses for the tabs
const ALL_STATUSES = [
  { id: 'new', name: 'New', color: '#2D7A52' },
  { id: 'attempted_contact', name: 'Attempted Contact', color: '#f59e0b' },
  { id: 'prospect', name: 'Prospect', color: '#2D7A52' },
  { id: 'application', name: 'Application', color: '#f59e0b' },
  { id: 'pre_qualified', name: 'Pre-Qualified', color: '#2D7A52' },
  { id: 'pre_approved', name: 'Pre-Approved', color: '#2D7A52' },
  { id: 'under_contract', name: 'Under Contract', color: '#f59e0b' },
  { id: 'long_term_nurture', name: 'Long-Term Nurture', color: '#2D7A52' },
  { id: 'withdrawn', name: 'Withdrawn', color: '#2D7A52' },
  { id: 'does_not_qualify', name: 'Does Not Qualify', color: '#ef4444' }
];

function WorkflowStatusDetail() {
  const { statusId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [statusData, setStatusData] = useState(null);
  const [loans, setLoans] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState('all'); // all, overdue, upcoming
  const [statusScores, setStatusScores] = useState({}); // Store scores for all statuses

  useEffect(() => {
    loadStatusData();
  }, [statusId]);

  const loadStatusData = async () => {
    try {
      setLoading(true);

      // Try to load from API first
      const response = await fetch(`${API_URL}/api/v1/workflow/status/${statusId}/detail`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setStatusData(data.status);
        setLoans(data.loans || []);
        setTasks(data.tasks || []);
      } else {
        // Use mock data as fallback
        loadMockData();
      }
    } catch (error) {
      console.error('Error loading status data:', error);
      loadMockData();
    } finally {
      setLoading(false);
    }
  };

  const loadMockData = () => {
    const statusNames = {
      'new': 'New',
      'attempted_contact': 'Attempted Contact',
      'prospect': 'Prospect',
      'application': 'Application',
      'pre_qualified': 'Pre-Qualified',
      'pre_approved': 'Pre-Approved',
      'under_contract': 'Under Contract',
      'long_term_nurture': 'Long-Term Nurture',
      'withdrawn': 'Withdrawn',
      'does_not_qualify': 'Does Not Qualify'
    };

    // Mock scores for all statuses (for tabs display)
    const mockScores = {
      'new': { score: 82, loans: 15, tasks: '28/32' },
      'attempted_contact': { score: 68, loans: 8, tasks: '12/20' },
      'prospect': { score: 75, loans: 22, tasks: '45/56' },
      'application': { score: 71, loans: 18, tasks: '36/48' },
      'pre_qualified': { score: 88, loans: 12, tasks: '24/26' },
      'pre_approved': { score: 79, loans: 14, tasks: '32/38' },
      'under_contract': { score: 65, loans: 9, tasks: '18/30' },
      'long_term_nurture': { score: 72, loans: 45, tasks: '68/90' },
      'withdrawn': { score: 90, loans: 3, tasks: '6/6' },
      'does_not_qualify': { score: 58, loans: 7, tasks: '8/18' }
    };
    setStatusScores(mockScores);

    const currentScore = mockScores[statusId] || { score: 75, loans: 18, tasks: '36/48' };
    const health = currentScore.score >= 80 ? 'healthy' : currentScore.score >= 65 ? 'warning' : 'critical';

    // Safely parse tasks string (e.g., "36/48") with bounds checking
    const taskParts = (currentScore.tasks || '0/0').split('/');
    const tasksCompleted = parseInt(taskParts[0]) || 0;
    const tasksDue = parseInt(taskParts[1] || '0') || 0;

    setStatusData({
      id: statusId,
      name: statusNames[statusId] || statusId,
      score: currentScore.score,
      health: health,
      activeLoans: currentScore.loans,
      tasksCompleted,
      tasksDue,
      avgDaysInStatus: 4.2,
      conversionRate: 68
    });

    setLoans([
      { id: 1, borrower_name: 'Sarah Johnson', loan_amount: 425000, days_in_status: 3, next_task: 'Follow-up call', next_task_due: '2025-11-29', health: 'healthy' },
      { id: 2, borrower_name: 'Mike Chen', loan_amount: 380000, days_in_status: 7, next_task: 'Document review', next_task_due: '2025-11-28', health: 'warning' },
      { id: 3, borrower_name: 'Emily Davis', loan_amount: 515000, days_in_status: 12, next_task: 'Rate lock decision', next_task_due: '2025-11-27', health: 'critical' },
      { id: 4, borrower_name: 'James Wilson', loan_amount: 290000, days_in_status: 2, next_task: 'Income verification', next_task_due: '2025-11-30', health: 'healthy' },
      { id: 5, borrower_name: 'Lisa Thompson', loan_amount: 445000, days_in_status: 5, next_task: 'Appraisal order', next_task_due: '2025-11-29', health: 'healthy' },
      { id: 6, borrower_name: 'Robert Brown', loan_amount: 350000, days_in_status: 8, next_task: 'Credit explanation letter', next_task_due: '2025-11-28', health: 'warning' }
    ]);

    setTasks([
      { id: 1, title: 'Follow-up call', loan_id: 1, borrower: 'Sarah Johnson', due_date: '2025-11-29', status: 'pending', priority: 'high' },
      { id: 2, title: 'Document review', loan_id: 2, borrower: 'Mike Chen', due_date: '2025-11-28', status: 'overdue', priority: 'critical' },
      { id: 3, title: 'Rate lock decision', loan_id: 3, borrower: 'Emily Davis', due_date: '2025-11-27', status: 'overdue', priority: 'critical' },
      { id: 4, title: 'Income verification', loan_id: 4, borrower: 'James Wilson', due_date: '2025-11-30', status: 'pending', priority: 'medium' },
      { id: 5, title: 'Appraisal order', loan_id: 5, borrower: 'Lisa Thompson', due_date: '2025-11-29', status: 'pending', priority: 'high' },
      { id: 6, title: 'Credit explanation letter', loan_id: 6, borrower: 'Robert Brown', due_date: '2025-11-28', status: 'overdue', priority: 'high' }
    ]);
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const getFilteredTasks = () => {
    if (filter === 'all') return tasks;
    if (filter === 'overdue') return tasks.filter(t => t.status === 'overdue');
    if (filter === 'upcoming') return tasks.filter(t => t.status === 'pending');
    return tasks;
  };

  if (loading) {
    return (
      <div className="workflow-status-detail">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Loading workflow status details...</p>
        </div>
      </div>
    );
  }

  // Helper function to get score color
  const getScoreColor = (score) => {
    if (score >= 80) return 'healthy';
    if (score >= 65) return 'warning';
    return 'critical';
  };

  return (
    <div className="workflow-status-detail">
      {/* Header */}
      <div className="status-detail-header">
        <button className="back-btn" onClick={() => navigate('/dashboard')}>
          ← Back to Dashboard
        </button>
        <div className="header-content">
          <h1>Workflow Scorecards</h1>
        </div>
      </div>

      {/* Status Tabs */}
      <div className="status-tabs-container">
        <div className="status-tabs">
          {ALL_STATUSES.map(status => {
            const scoreData = statusScores[status.id] || { score: 0 };
            const isActive = status.id === statusId;
            const scoreColor = getScoreColor(scoreData.score);
            return (
              <button
                key={status.id}
                className={`status-tab ${isActive ? 'active' : ''} ${scoreColor}`}
                onClick={() => navigate(`/workflow/status/${status.id}`)}
              >
                <span className="tab-name">{status.name}</span>
                <span className={`tab-score ${scoreColor}`}>{scoreData.score}%</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Current Status Header */}
      <div className="current-status-header">
        <h2>{statusData?.name}</h2>
        <div className={`status-health-badge ${statusData?.health}`}>
          {statusData?.health === 'healthy' ? '✓ Healthy' : statusData?.health === 'warning' ? '⚠ Needs Attention' : '⚠ Critical'}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="status-summary-cards">
        <div className="summary-card">
          <div className="card-label">Overall Score</div>
          <div className={`card-value score ${statusData?.health}`}>{statusData?.score}%</div>
        </div>
        <div className="summary-card">
          <div className="card-label">Active Loans</div>
          <div className="card-value">{statusData?.activeLoans}</div>
        </div>
        <div className="summary-card">
          <div className="card-label">Tasks Completed</div>
          <div className="card-value">{statusData?.tasksCompleted}/{statusData?.tasksDue}</div>
        </div>
        <div className="summary-card">
          <div className="card-label">Avg. Days in Status</div>
          <div className="card-value">{statusData?.avgDaysInStatus} days</div>
        </div>
        <div className="summary-card">
          <div className="card-label">Conversion Rate</div>
          <div className="card-value">{statusData?.conversionRate}%</div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="status-detail-grid">
        {/* Loans Table */}
        <div className="detail-section loans-section">
          <div className="section-header">
            <h2>Loans in {statusData?.name}</h2>
            <span className="loan-count">{loans.length} loans</span>
          </div>
          <div className="loans-table">
            <table>
              <thead>
                <tr>
                  <th>Borrower</th>
                  <th>Loan Amount</th>
                  <th>Days in Status</th>
                  <th>Next Task</th>
                  <th>Due Date</th>
                  <th>Health</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loans.map(loan => (
                  <tr key={loan.id} className={`loan-row ${loan.health}`}>
                    <td className="borrower-name">{loan.borrower_name}</td>
                    <td>{formatCurrency(loan.loan_amount)}</td>
                    <td>{loan.days_in_status} days</td>
                    <td>{loan.next_task}</td>
                    <td>{loan.next_task_due}</td>
                    <td>
                      <span className={`health-indicator ${loan.health}`}>
                        {loan.health === 'healthy' ? '●' : loan.health === 'warning' ? '●' : '●'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="view-loan-btn"
                        onClick={() => navigate(`/loans/${loan.id}`)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Tasks List */}
        <div className="detail-section tasks-section">
          <div className="section-header">
            <h2>Workflow Tasks</h2>
            <div className="task-filters">
              <button
                className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
                onClick={() => setFilter('all')}
              >
                All ({tasks.length})
              </button>
              <button
                className={`filter-btn ${filter === 'overdue' ? 'active' : ''}`}
                onClick={() => setFilter('overdue')}
              >
                Overdue ({tasks.filter(t => t.status === 'overdue').length})
              </button>
              <button
                className={`filter-btn ${filter === 'upcoming' ? 'active' : ''}`}
                onClick={() => setFilter('upcoming')}
              >
                Upcoming ({tasks.filter(t => t.status === 'pending').length})
              </button>
            </div>
          </div>
          <div className="tasks-list">
            {getFilteredTasks().map(task => (
              <div key={task.id} className={`task-item ${task.status} ${task.priority}`}>
                <div className="task-info">
                  <div className="task-title">{task.title}</div>
                  <div className="task-borrower">{task.borrower}</div>
                </div>
                <div className="task-meta">
                  <span className={`task-due ${task.status}`}>
                    {task.status === 'overdue' ? 'Overdue: ' : 'Due: '}{task.due_date}
                  </span>
                  <span className={`task-priority ${task.priority}`}>{task.priority}</span>
                </div>
                <button
                  className="complete-task-btn"
                  onClick={() => navigate(`/loans/${task.loan_id}`)}
                >
                  Go to Loan
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default WorkflowStatusDetail;
