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
        const user = getUserData() || {};
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
    return { annualGoal: 0, monthlyGoal: 0, weeklyGoal: 0, dailyGoal: 0 };
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

export default Dashboard;
