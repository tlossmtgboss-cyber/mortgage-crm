import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useDashboard } from '../hooks/useQueries';
import { getDashboardContainersForRole } from '../config/roleConfig';
import PendingPermissionRequests from '../components/PendingPermissionRequests';
import ProductionPredictor from '../components/ProductionPredictor';
import DealAlerts from '../components/DealAlerts';
import api from '../services/api';
import './Dashboard.css';
import MorningBriefingCard from '../components/dashboard/MorningBriefingCard';
import { getUserData } from '../utils/tokenStore';

function Dashboard() {
  const navigate = useNavigate();
  const { hasPermission, userRole, effectiveRole, isRolePreview, rolePreview, exitRolePreview } = usePermissions();

  // Redirect admin users to /admin page (unless in role preview mode)
  useEffect(() => {
    // Check if we're in role preview mode - if so, don't redirect
    const rolePreview = localStorage.getItem('role_preview');
    if (rolePreview) {
      console.log('Role preview mode active - staying on dashboard');
      return; // Don't redirect when previewing a role
    }

    // Check both userRole and localStorage for admin status
    const isAdmin = userRole === 'admin' || (() => {
      try {
        const user = JSON.parse(getUserData() || '{}');
        return user.role === 'admin' || user.permission_role === 'admin';
      } catch { return false; }
    })();

    if (isAdmin) {
      navigate('/admin', { replace: true });
    }
  }, [userRole, navigate]);

  // Use React Query for cached dashboard data - instant on revisit!
  const { data: dashboardData, isLoading: loading, refetch: refetchDashboard } = useDashboard();

  // Check if current user is demo user
  const isDemoUser = () => {
    try {
      const userStr = getUserData();
      if (userStr) {
        const user = JSON.parse(userStr);
        return user.email === 'admin@perenniaai.com';
      }
    } catch (error) {
      console.error('Error checking demo user:', error);
    }
    return false;
  };

  // Dashboard data derived from React Query cache (instant on revisit!)
  const prioritizedTasks = dashboardData?.prioritized_tasks || [];
  const pipelineStats = dashboardData?.pipeline_stats || [];
  const production = dashboardData?.production || {};
  const leadMetrics = dashboardData?.lead_metrics || {};
  const loanIssues = dashboardData?.loan_issues || [];
  const aiTasks = dashboardData?.ai_tasks || { pending: [], waiting: [] };
  const referralStats = dashboardData?.referral_stats || {};
  const teamStats = dashboardData?.team_stats || {};
  const messages = dashboardData?.messages || [];
  const efficiency = dashboardData?.efficiency || {};

  // Drag and drop state
  const [draggedIndex, setDraggedIndex] = useState(null);

  // IT Tickets metrics state
  const [itTicketMetrics, setItTicketMetrics] = useState(null);

  // Check if user is admin (any admin role, not just demo email)
  const isAdminUser = () => {
    return userRole === 'admin' || userRole === 'site_admin' || effectiveRole === 'admin' || effectiveRole === 'site_admin';
  };

  // Fetch IT Ticket metrics for admin users
  useEffect(() => {
    const fetchItTicketMetrics = async () => {
      if (!isAdminUser()) return;
      try {
        const response = await api.get('/api/v1/support/metrics');
        if (response.data) {
          setItTicketMetrics(response.data);
        }
      } catch (error) {
        console.log('IT Ticket metrics not available:', error.message);
      }
    };
    fetchItTicketMetrics();
  }, [userRole, effectiveRole]);

  // Get allowed containers for the current role
  const allowedContainers = useMemo(() => {
    return getDashboardContainersForRole(effectiveRole);
  }, [effectiveRole]);

  // Container order filtered by role
  const [containerOrder, setContainerOrder] = useState(() => {
    // Start with role-specific allowed containers
    return getDashboardContainersForRole(effectiveRole || 'loan_officer');
  });
  const workflowScores = dashboardData?.workflow_scores || { statuses: [], overallScore: 0 };

  // Reload container order when role changes
  useEffect(() => {
    loadContainerOrder();
  }, [effectiveRole]);

  // React Query handles data fetching automatically - no useEffect needed!

  // Load saved container order for the current role
  const loadContainerOrder = () => {
    try {
      // Get the allowed containers for this role
      const roleContainers = getDashboardContainersForRole(effectiveRole);
      const storageKey = `dashboardOrder_${effectiveRole}`;

      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const savedOrder = JSON.parse(saved);
        // Filter to only include containers allowed for this role
        const filteredSaved = savedOrder.filter(c => roleContainers.includes(c));
        // Add any new containers from role config that weren't in saved order
        const missingContainers = roleContainers.filter(c => !filteredSaved.includes(c));
        const newOrder = [...filteredSaved, ...missingContainers];
        setContainerOrder(newOrder);
      } else {
        // No saved order, use default from role config
        setContainerOrder(roleContainers);
      }
    } catch (error) {
      console.error('Failed to load container order:', error);
      // Fallback to role defaults
      setContainerOrder(getDashboardContainersForRole(effectiveRole));
    }
  };

  // Save container order for the current role
  const saveContainerOrder = (order) => {
    try {
      const storageKey = `dashboardOrder_${effectiveRole}`;
      localStorage.setItem(storageKey, JSON.stringify(order));
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

  // Refresh dashboard data - React Query handles caching automatically
  const loadDashboard = () => {
    refetchDashboard();
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
      // PHASE 4: Show for users with production.view permission or roles that should see production
      // Always show for demo user or if container is in the allowed list for this role
      const productionRoles = ['admin', 'site_admin', 'loan_officer', 'manager', 'executive', 'sales', 'management'];
      const canViewProduction = hasPermission('production.view') ||
                                productionRoles.includes(userRole) ||
                                productionRoles.includes(effectiveRole) ||
                                isDemoUser() ||
                                allowedContainers.includes('production-tracker');
      if (!canViewProduction) {
        return null;
      }

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
            <h2>Monthly Production Tracker</h2>
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

          {/* AI Coaching Insights */}
          <div className="ai-insights-section">
            <div className="ai-insights-header">
              <h3>AI Coaching Insights</h3>
            </div>
            <div className="insights-list">
              {production.annualProgress < 75 && (
                <div className="insight-item warning">
                  <span className="insight-text">
                    You're at {production.annualProgress}% of your annual goal. Consider increasing your lead generation activities to stay on track.
                  </span>
                </div>
              )}
              {production.monthlyProgress > 100 && (
                <div className="insight-item success">
                  <span className="insight-text">
                    Excellent! You've exceeded your monthly goal by {(production.monthlyProgress - 100).toFixed(0)}%. Keep up the great work!
                  </span>
                </div>
              )}
              {production.monthlyProgress < 50 && (
                <div className="insight-item warning">
                  <span className="insight-text">
                    You're only at {production.monthlyProgress}% of your monthly goal. Focus on converting your pipeline to close more deals this month.
                  </span>
                </div>
              )}
              {production.weeklyProgress < 80 && production.weeklyProgress > 0 && (
                <div className="insight-item info">
                  <span className="insight-text">
                    Weekly progress is at {production.weeklyProgress}%. Review your pipeline and prioritize hot leads to finish strong.
                  </span>
                </div>
              )}
              {production.dailyActual === 0 && (
                <div className="insight-item info">
                  <span className="insight-text">
                    No units closed today yet. Connect with your active deals to move them towards closing.
                  </span>
                </div>
              )}
              {production.annualProgress >= 75 && production.annualProgress < 90 && (
                <div className="insight-item success">
                  <span className="insight-text">
                    You're {(100 - production.annualProgress).toFixed(0)}% away from your annual goal. Maintain your current pace to finish strong!
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (containerId === 'production-predictor') {
      return (
        <div
          key={containerId}
          className={`dashboard-block production-predictor-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <ProductionPredictor embedded={true} />
        </div>
      );
    }

    if (containerId === 'deal-alerts') {
      return (
        <div
          key={containerId}
          className={`dashboard-block deal-alerts-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <DealAlerts embedded={true} />
        </div>
      );
    }

    if (containerId === 'profitability') {
      return (
        <div
          key={containerId}
          className={`dashboard-block profitability-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header clickable-block" onClick={() => navigate('/profitability')}>
            <h2>Profitability Intelligence</h2>
          </div>
          <div className="profitability-preview">
            <div className="profitability-metrics-grid">
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=gain_on_sale')}
              >
                <div className="metric-label">Gain on Sale</div>
                <div className="metric-value">--</div>
                <div className="metric-change neutral">No data yet</div>
              </div>
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=cost_per_loan')}
              >
                <div className="metric-label">Cost per Loan</div>
                <div className="metric-value">--</div>
                <div className="metric-change neutral">No data yet</div>
              </div>
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=net_margin')}
              >
                <div className="metric-label">Net Margin</div>
                <div className="metric-value">--</div>
                <div className="metric-change neutral">No data yet</div>
              </div>
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=cash_runway')}
              >
                <div className="metric-label">Cash Runway</div>
                <div className="metric-value">--</div>
                <div className="metric-change neutral">No data yet</div>
              </div>
            </div>
            <div className="profitability-insights">
              <div className="insight-item">
                <span>Add loans to see profitability insights</span>
              </div>
            </div>
            <button
              className="btn-view-profitability"
              onClick={() => navigate('/profitability')}
            >
              View Full Analysis →
            </button>
          </div>
        </div>
      );
    }

    if (containerId === 'efficiency') {
      // Show efficiency tracker for all users
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
          <div className="block-header clickable-block" onClick={() => navigate('/dashboard/efficiency')}>
            <h2>Pipeline Efficiency Monitor</h2>
          </div>

          {/* Overall Score & Key Metrics Row */}
          <div className="efficiency-summary">
            <div className="efficiency-score-display">
              <div className="score-number">{efficiency.overallScore || 0}</div>
              <div className="score-label">Overall Efficiency</div>
              <div className={`score-trend ${(efficiency.trend || 0) >= 0 ? 'up' : 'down'}`}>
                {(efficiency.trend || 0) >= 0 ? '↑' : '↓'} {Math.abs(efficiency.trend || 0)}% vs. last period
              </div>
            </div>

            {/* Key Metrics Grid */}
            <div className="efficiency-key-metrics">
              <div className="efficiency-metric-card">
                <div className="metric-label">Avg. Time to Close</div>
                <div className="metric-value">{efficiency.avgTimeToClose || 0} days</div>
                <div className={`metric-change ${(efficiency.avgTimeToCloseChange || 0) < 0 ? 'positive' : 'negative'}`}>
                  {(efficiency.avgTimeToCloseChange || 0) < 0 ? '↓' : '↑'} {Math.abs(efficiency.avgTimeToCloseChange || 0)} days
                </div>
              </div>
              <div className="efficiency-metric-card">
                <div className="metric-label">Pull-Through Rate</div>
                <div className="metric-value">{efficiency.pullThroughRate || 0}%</div>
                <div className={`metric-change ${(efficiency.pullThroughRateChange || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {(efficiency.pullThroughRateChange || 0) >= 0 ? '↑' : '↓'} {Math.abs(efficiency.pullThroughRateChange || 0)}%
                </div>
              </div>
              <div className="efficiency-metric-card">
                <div className="metric-label">Loans Falling Behind</div>
                <div className="metric-value">{efficiency.loansFallingBehind || 0}</div>
                <div className={`metric-change ${(efficiency.loansFallingBehindChange || 0) < 0 ? 'positive' : 'negative'}`}>
                  {(efficiency.loansFallingBehindChange || 0) < 0 ? '↓' : '↑'} {Math.abs(efficiency.loansFallingBehindChange || 0)}
                </div>
              </div>
              <div className="efficiency-metric-card">
                <div className="metric-label">Automation Rate</div>
                <div className="metric-value">{efficiency.automationRate || 0}%</div>
                <div className={`metric-change ${(efficiency.automationRateChange || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {(efficiency.automationRateChange || 0) >= 0 ? '↑' : '↓'} {Math.abs(efficiency.automationRateChange || 0)}%
                </div>
              </div>
              <div className="efficiency-metric-card">
                <div className="metric-label">Customer Satisfaction Score</div>
                <div className="metric-value">{efficiency.customerSatisfaction || 0}%</div>
                <div className={`metric-change ${(efficiency.customerSatisfactionChange || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {(efficiency.customerSatisfactionChange || 0) >= 0 ? '↑' : '↓'} {Math.abs(efficiency.customerSatisfactionChange || 0)}%
                </div>
              </div>
            </div>
          </div>

          {/* Stage Performance & Team Performance Row */}
          <div className="efficiency-cards">
            {/* Stage Efficiency */}
            <div className="efficiency-card stage-efficiency">
              <h4>Stage Performance</h4>
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
              <h4>Team Performance</h4>
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
          </div>

          {/* Bottlenecks Section */}
          <div className="efficiency-bottlenecks-section">
            <h4>Active Bottlenecks ({efficiency.bottleneckCount || 0})</h4>
            <div className="bottleneck-list">
              {(efficiency.bottlenecks || []).slice(0, 4).map((bottleneck, idx) => (
                <div key={idx} className="bottleneck-item">
                  <div className="bottleneck-content">
                    <div className="bottleneck-text">{bottleneck.issue}</div>
                    <div className="bottleneck-meta">{bottleneck.stage} • {bottleneck.affectedLoans} loans • {bottleneck.avgDelay}</div>
                  </div>
                </div>
              ))}
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

    if (containerId === 'workflow-scorecards') {
      const statuses = workflowScores.statuses || [];
      const overallScore = workflowScores.overallScore || 0;

      return (
        <div
          key={containerId}
          className={`dashboard-block workflow-scorecards-block draggable-container ${isDragging ? 'dragging' : ''}`}
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
            <h2>Workflow Scorecards</h2>
            <div className="workflow-overall-score">
              <span className="score-label">Overall:</span>
              <span className={`score-value ${overallScore >= 80 ? 'good' : overallScore >= 60 ? 'warning' : 'critical'}`}>
                {overallScore}%
              </span>
            </div>
          </div>

          <div className="workflow-status-grid">
            {/* Top Row - First 5 statuses */}
            <div className="workflow-status-row">
              {statuses.slice(0, 5).map((status, idx) => (
                <div
                  key={idx}
                  className={`workflow-status-card ${status.health}`}
                  onClick={() => navigate(`/workflow/status/${status.id}`)}
                >
                  <div className="status-name">{status.name}</div>
                  <div className="status-score">{status.score}%</div>
                  <div className="status-metrics">
                    <span className="metric">{status.activeLoans} loans</span>
                    <span className="metric">{status.tasksCompleted}/{status.tasksDue} tasks</span>
                  </div>
                  <div className={`status-health-indicator ${status.health}`}></div>
                </div>
              ))}
            </div>

            {/* Bottom Row - Last 5 statuses */}
            <div className="workflow-status-row">
              {statuses.slice(5, 10).map((status, idx) => (
                <div
                  key={idx}
                  className={`workflow-status-card ${status.health}`}
                  onClick={() => navigate(`/workflow/status/${status.id}`)}
                >
                  <div className="status-name">{status.name}</div>
                  <div className="status-score">{status.score}%</div>
                  <div className="status-metrics">
                    <span className="metric">{status.activeLoans} loans</span>
                    <span className="metric">{status.tasksCompleted}/{status.tasksDue} tasks</span>
                  </div>
                  <div className={`status-health-indicator ${status.health}`}></div>
                </div>
              ))}
            </div>
          </div>
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
            <h2>AI Prioritized Tasks (Today)</h2>
            <span className="task-count">{getAggregatedTasksCount()} tasks</span>
          </div>
          <div className="task-summary-view clickable-container" onClick={() => navigate('/tasks')}>
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
            <h2>Live Loan Pipeline</h2>
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
      // PHASE 4: Show for users with referrals.view permission or roles that should see referrals
      // Always show for demo user or if container is in the allowed list for this role
      const referralRoles = ['admin', 'site_admin', 'loan_officer', 'manager', 'sales', 'management'];
      const canViewReferrals = hasPermission('referrals.view') ||
                               referralRoles.includes(userRole) ||
                               referralRoles.includes(effectiveRole) ||
                               isDemoUser() ||
                               allowedContainers.includes('referrals');
      if (!canViewReferrals) {
        return null;
      }

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
            <h2>Referral Scoreboard</h2>
          </div>
          <div className="referrals-content">
            <div className="referral-scoreboard-grid">
              {/* Left column: Top 1-10 */}
              <div className="scoreboard-column">
                {referralStats.top_partners && referralStats.top_partners
                  .filter(p => p && p.name)
                  .slice(0, 10)
                  .map((partner, idx) => (
                    <div
                      key={idx}
                      className="scoreboard-row clickable"
                      onClick={() => navigate(`/referral-partners/${partner.id || idx + 1}`)}
                    >
                      <span className="rank">{idx + 1}</span>
                      <span className="partner-name">{partner.name}</span>
                      <span className="partner-score">
                        <span className="received">↓{partner.received}</span>
                        <span className="sent">↑{partner.sent}</span>
                      </span>
                    </div>
                  ))}
              </div>
              {/* Right column: 11-25 */}
              <div className="scoreboard-column">
                {referralStats.top_partners && referralStats.top_partners
                  .filter(p => p && p.name)
                  .slice(10, 25)
                  .map((partner, idx) => (
                    <div
                      key={idx}
                      className="scoreboard-row clickable"
                      onClick={() => navigate(`/referral-partners/${partner.id || idx + 11}`)}
                    >
                      <span className="rank">{idx + 11}</span>
                      <span className="partner-name">{partner.name}</span>
                      <span className="partner-score">
                        <span className="received">↓{partner.received}</span>
                        <span className="sent">↑{partner.sent}</span>
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (containerId === 'team' && teamStats.has_team) {
      // PHASE 4: Show for users with team.view_all/team.view_team permission or management roles
      // Always show for demo user or if container is in the allowed list for this role
      const teamRoles = ['admin', 'site_admin', 'manager', 'executive', 'management'];
      const canViewTeam = hasPermission('team.view_all') ||
                          hasPermission('team.view_team') ||
                          teamRoles.includes(userRole) ||
                          teamRoles.includes(effectiveRole) ||
                          isDemoUser() ||
                          allowedContainers.includes('team');
      if (!canViewTeam) {
        return null;
      }

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
            <h2>Team Performance</h2>
          </div>
          <div className="team-content">
            <div className="team-metrics">
              <div
                className="team-metric clickable-metric"
                onClick={() => navigate('/efficiency/team/processors')}
                title="View processor files"
              >
                <div className="metric-label">Processor Workload</div>
                <div className="metric-value">{teamStats.avg_workload} files/person</div>
              </div>
              <div
                className="team-metric clickable-metric"
                onClick={() => navigate('/tasks?filter=backlog')}
                title="View task backlog"
              >
                <div className="metric-label">Task Backlog</div>
                <div className="metric-value warn">{teamStats.backlog}</div>
              </div>
              <div
                className="team-metric clickable-metric"
                onClick={() => navigate('/sla-tracking?filter=missed')}
                title="View SLA violations"
              >
                <div className="metric-label">SLA Missed</div>
                <div className="metric-value">{teamStats.sla_missed}</div>
              </div>
            </div>
            <div className="ai-coaching">
              <div className="coaching-title">AI Coaching Insights</div>
              {teamStats.insights && teamStats.insights.filter(i => i).map((insight, idx) => (
                <div key={idx} className="coaching-insight">
                  {insight}
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    // IT Tickets KPIs - Admin only
    if (containerId === 'it-tickets') {
      if (!isAdminUser()) {
        return null;
      }

      return (
        <div
          key={containerId}
          className={`dashboard-block it-tickets-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header clickable-block" onClick={() => navigate('/support')}>
            <h2>IT Support Tickets</h2>
          </div>
          <div className="it-tickets-metrics">
            <div className="it-ticket-metric" onClick={() => navigate('/support')}>
              <div className="metric-icon" style={{ background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' }}>
                <span>📊</span>
              </div>
              <div className="metric-content">
                <div className="metric-value">{itTicketMetrics?.avg_per_day?.toFixed(1) || '0.0'}</div>
                <div className="metric-label">Avg Tickets/Day</div>
              </div>
            </div>
            <div className="it-ticket-metric" onClick={() => navigate('/support')}>
              <div className="metric-icon" style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}>
                <span>⏱️</span>
              </div>
              <div className="metric-content">
                <div className="metric-value">{itTicketMetrics?.turn_time_display || '--'}</div>
                <div className="metric-label">Avg Turn Time</div>
              </div>
            </div>
            <div className="it-ticket-metric" onClick={() => navigate('/support')}>
              <div className="metric-icon" style={{ background: 'linear-gradient(135deg, #8b5cf6, #6d28d9)' }}>
                <span>📅</span>
              </div>
              <div className="metric-content">
                <div className="metric-value">{itTicketMetrics?.tickets_this_month || 0}</div>
                <div className="metric-label">This Month</div>
              </div>
            </div>
            <div className="it-ticket-metric" onClick={() => navigate('/support?status=open')}>
              <div className="metric-icon" style={{ background: 'linear-gradient(135deg, #10b981, #059669)' }}>
                <span>🎫</span>
              </div>
              <div className="metric-content">
                <div className="metric-value">{itTicketMetrics?.open_tickets || 0}</div>
                <div className="metric-label">Open Tickets</div>
              </div>
            </div>
          </div>
          <button
            className="btn-view-tickets"
            onClick={() => navigate('/support')}
          >
            View All Tickets →
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
      {/* Role Preview Banner */}
      {isRolePreview && rolePreview && (
        <div style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: 'white',
          padding: '12px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem',
          borderRadius: '8px',
          boxShadow: '0 2px 10px rgba(102, 126, 234, 0.3)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '18px' }}>👁️</span>
            <span style={{ fontWeight: '600' }}>
              Previewing as: <strong>{rolePreview.role_name}</strong>
            </span>
            <span style={{ opacity: 0.8, fontSize: '14px' }}>
              (This is how a {rolePreview.role_name} sees their dashboard)
            </span>
          </div>
          <button
            onClick={exitRolePreview}
            style={{
              background: 'white',
              color: '#667eea',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontWeight: '600',
              cursor: 'pointer',
              transition: 'transform 0.2s'
            }}
            onMouseOver={(e) => e.target.style.transform = 'scale(1.05)'}
            onMouseOut={(e) => e.target.style.transform = 'scale(1)'}
          >
            Exit Preview
          </button>
        </div>
      )}

      <MorningBriefingCard />

      <div className="dashboard-header-compact">
        <h1>Today's Command Center</h1>
        <div className="header-actions">
          <div className="header-date">
            {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
          </div>
          <button
            className="ai-landing-btn"
            onClick={() => navigate('/ai')}
            title="Open AI Assistant"
          >
            AI Assistant
          </button>
        </div>
      </div>

      {/* Permission Requests Widget - Users with team.manage_permissions or managers */}
      {(hasPermission('team.manage_permissions') || userRole === 'management') && (
        <div style={{ marginBottom: '2rem' }}>
          <PendingPermissionRequests />
        </div>
      )}

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
    { id: 1, name: 'Amy Smith (Realtor)', received: 12, sent: 10, balance: 2 },
    { id: 2, name: 'Bob Johnson (Builder)', received: 9, sent: 11, balance: -2 },
    { id: 3, name: 'Carol Davis (Realtor)', received: 8, sent: 8, balance: 0 },
    { id: 4, name: 'David Lee (Financial Advisor)', received: 7, sent: 6, balance: 1 },
    { id: 5, name: 'Emily Wilson (Realtor)', received: 6, sent: 7, balance: -1 },
    { id: 6, name: 'Frank Miller (Attorney)', received: 5, sent: 5, balance: 0 },
    { id: 7, name: 'Grace Chen (Realtor)', received: 5, sent: 4, balance: 1 },
    { id: 8, name: 'Henry Taylor (Builder)', received: 4, sent: 5, balance: -1 },
    { id: 9, name: 'Irene Martinez (Realtor)', received: 4, sent: 3, balance: 1 },
    { id: 10, name: 'Jack Brown (Insurance)', received: 3, sent: 4, balance: -1 },
    { id: 11, name: 'Karen White (Realtor)', received: 3, sent: 3, balance: 0 },
    { id: 12, name: 'Leo Garcia (CPA)', received: 3, sent: 2, balance: 1 },
    { id: 13, name: 'Maria Rodriguez (Realtor)', received: 2, sent: 3, balance: -1 },
    { id: 14, name: 'Nick Thompson (Builder)', received: 2, sent: 2, balance: 0 },
    { id: 15, name: 'Olivia Harris (Realtor)', received: 2, sent: 2, balance: 0 },
    { id: 16, name: 'Paul Anderson (Financial Advisor)', received: 2, sent: 1, balance: 1 },
    { id: 17, name: 'Quinn Moore (Realtor)', received: 1, sent: 2, balance: -1 },
    { id: 18, name: 'Rachel Clark (Attorney)', received: 1, sent: 1, balance: 0 },
    { id: 19, name: 'Steve Lewis (Builder)', received: 1, sent: 1, balance: 0 },
    { id: 20, name: 'Tina Walker (Realtor)', received: 1, sent: 1, balance: 0 },
    { id: 21, name: 'Ulysses Hall (Insurance)', received: 1, sent: 0, balance: 1 },
    { id: 22, name: 'Victoria King (Realtor)', received: 0, sent: 1, balance: -1 },
    { id: 23, name: 'Walter Scott (CPA)', received: 0, sent: 1, balance: -1 },
    { id: 24, name: 'Xena Young (Realtor)', received: 0, sent: 0, balance: 0 },
    { id: 25, name: 'Yolanda Adams (Builder)', received: 0, sent: 0, balance: 0 }
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
    type_icon: '',
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
    type_icon: '',
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
    type_icon: '',
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
    type_icon: '',
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
    type_icon: '',
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
    type_icon: '',
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
  trend: 5.2,

  // Key Metrics
  avgTimeToClose: 35.2,
  avgTimeToCloseChange: -2.3,
  pullThroughRate: 68,
  pullThroughRateChange: 4.1,
  loansFallingBehind: 12,
  loansFallingBehindChange: -3,
  automationRate: 42,
  automationRateChange: 8.5,
  customerSatisfaction: 85,
  customerSatisfactionChange: 3.2,

  // Stage Performance
  stages: [
    { name: 'Lead Generation', efficiency: 85, status: 'on-track' },
    { name: 'Pre-Qualification', efficiency: 72, status: 'slightly-delayed' },
    { name: 'Application', efficiency: 81, status: 'on-track' },
    { name: 'Processing', efficiency: 65, status: 'behind' },
    { name: 'Underwriting', efficiency: 70, status: 'slightly-delayed' },
    { name: 'Clear to Close', efficiency: 88, status: 'on-track' },
    { name: 'Closing', efficiency: 92, status: 'on-track' }
  ],

  // Team Performance
  team: [
    { role: 'Loan Officers', performance: 82 },
    { role: 'Processors', performance: 68 },
    { role: 'Underwriters', performance: 75 },
    { role: 'Closers', performance: 91 }
  ],

  // Bottlenecks
  bottleneckCount: 6,
  bottlenecks: [
    {
      issue: 'Missing Documents',
      stage: 'Processing',
      affectedLoans: 8,
      avgDelay: '4.5 days'
    },
    {
      issue: 'Income Verification Delays',
      stage: 'Pre-Qualification',
      affectedLoans: 6,
      avgDelay: '3.2 days'
    },
    {
      issue: 'Appraisal Review Backlog',
      stage: 'Underwriting',
      affectedLoans: 5,
      avgDelay: '2.8 days'
    },
    {
      issue: 'Credit Report Disputes',
      stage: 'Processing',
      affectedLoans: 4,
      avgDelay: '5.1 days'
    }
  ]
});

const mockWorkflowScores = () => ({
  overallScore: 74,
  statuses: [
    // Top Row - 5 statuses
    { id: 'new', name: 'New', score: 82, health: 'healthy', activeLoans: 15, tasksCompleted: 28, tasksDue: 32 },
    { id: 'attempted_contact', name: 'Attempted Contact', score: 68, health: 'warning', activeLoans: 8, tasksCompleted: 12, tasksDue: 20 },
    { id: 'prospect', name: 'Prospect', score: 75, health: 'healthy', activeLoans: 22, tasksCompleted: 45, tasksDue: 56 },
    { id: 'application', name: 'Application', score: 71, health: 'warning', activeLoans: 18, tasksCompleted: 36, tasksDue: 48 },
    { id: 'pre_qualified', name: 'Pre-Qualified', score: 88, health: 'healthy', activeLoans: 12, tasksCompleted: 24, tasksDue: 26 },
    // Bottom Row - 5 statuses
    { id: 'pre_approved', name: 'Pre-Approved', score: 79, health: 'healthy', activeLoans: 14, tasksCompleted: 32, tasksDue: 38 },
    { id: 'under_contract', name: 'Under Contract', score: 65, health: 'critical', activeLoans: 9, tasksCompleted: 18, tasksDue: 30 },
    { id: 'long_term_nurture', name: 'Long-Term Nurture', score: 72, health: 'warning', activeLoans: 45, tasksCompleted: 68, tasksDue: 90 },
    { id: 'withdrawn', name: 'Withdrawn', score: 90, health: 'healthy', activeLoans: 3, tasksCompleted: 6, tasksDue: 6 },
    { id: 'does_not_qualify', name: 'Does Not Qualify', score: 58, health: 'critical', activeLoans: 7, tasksCompleted: 8, tasksDue: 18 }
  ]
});

export default Dashboard;
