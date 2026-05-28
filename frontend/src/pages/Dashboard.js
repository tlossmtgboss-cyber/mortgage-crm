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
import BriefingErrorBoundary from '../components/briefing/BriefingErrorBoundary';
import { getUserData } from '../utils/tokenStore';

function Dashboard() {
  const navigate = useNavigate();
  const { hasPermission, userRole, effectiveRole, isRolePreview, rolePreview, exitRolePreview } = usePermissions();

  // Dashboard view toggle for manager/admin roles
  const isManagerOrAdmin = ['admin', 'site_admin', 'manager', 'executive', 'management'].includes(userRole) ||
    ['admin', 'site_admin', 'manager', 'executive', 'management'].includes(effectiveRole);

  const [dashboardView, setDashboardView] = useState(() => {
    if (!isManagerOrAdmin) return 'personal';
    return localStorage.getItem('dashboardView') || 'personal';
  });

  // Use React Query for cached dashboard data - instant on revisit!
  const { data: dashboardData, isLoading: loading, refetch: refetchDashboard } = useDashboard();

  // Auto-refetch dashboard when any CRM mutation occurs (lead/loan/task changes)
  useEffect(() => {
    const handleMutation = () => {
      refetchDashboard();
    };
    window.addEventListener('crm-mutation', handleMutation);
    return () => window.removeEventListener('crm-mutation', handleMutation);
  }, [refetchDashboard]);

  const isPlatformAdmin = () => {
    try {
      const user = getUserData();
      if (user) {
        return ['admin@perenniaai.com', 'tloss@cmgfi.com'].includes(user.email);
      }
    } catch (error) {
      console.error('Error checking platform admin:', error);
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
  const mumSummary = dashboardData?.mum_summary || {};

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

  // Get allowed containers based on view toggle
  const activeRole = useMemo(() => {
    if (!isManagerOrAdmin) return effectiveRole;
    return dashboardView === 'manager' ? 'manager' : 'loan_officer';
  }, [effectiveRole, dashboardView, isManagerOrAdmin]);

  const allowedContainers = useMemo(() => {
    return getDashboardContainersForRole(activeRole);
  }, [activeRole]);

  // Container order filtered by role
  const [containerOrder, setContainerOrder] = useState(() => {
    return getDashboardContainersForRole(activeRole || 'loan_officer');
  });
  const workflowScores = dashboardData?.workflow_scores || { statuses: [], overallScore: 0 };
  const profitability = dashboardData?.profitability || {};
  const loanIssuesList = dashboardData?.loan_issues || [];

  // Reload container order when role or view changes
  useEffect(() => {
    loadContainerOrder();
  }, [activeRole]);

  // React Query handles data fetching automatically - no useEffect needed!

  // Load saved container order for the current view
  const loadContainerOrder = () => {
    try {
      const roleContainers = getDashboardContainersForRole(activeRole);
      const storageKey = `dashboardOrder_${activeRole}`;

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
      setContainerOrder(getDashboardContainersForRole(activeRole));
    }
  };

  const handleViewToggle = (view) => {
    setDashboardView(view);
    localStorage.setItem('dashboardView', view);
  };

  // Save container order for the current view
  const saveContainerOrder = (order) => {
    try {
      const storageKey = `dashboardOrder_${activeRole}`;
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
      // Always show for platform admin or if container is in the allowed list for this role
      const productionRoles = ['admin', 'site_admin', 'loan_officer', 'manager', 'executive', 'sales', 'management'];
      const canViewProduction = hasPermission('production.view') ||
                                productionRoles.includes(userRole) ||
                                productionRoles.includes(effectiveRole) ||
                                isPlatformAdmin() ||
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
                <div className="metric-value">{profitability.gain_on_sale_display || 'No data yet'}</div>
                <div className={`metric-change ${profitability.gain_on_sale > 0 ? 'positive' : 'neutral'}`}>
                  {profitability.gain_on_sale > 0 ? `${profitability.funded_ytd} loans YTD` : 'No data yet'}
                </div>
              </div>
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=cost_per_loan')}
              >
                <div className="metric-label">Revenue / Loan</div>
                <div className="metric-value">{profitability.revenue_per_loan_display || 'No data yet'}</div>
                <div className={`metric-change ${profitability.revenue_per_loan > 0 ? 'positive' : 'neutral'}`}>
                  {profitability.avg_loan_size > 0 ? `Avg size: $${(profitability.avg_loan_size / 1000).toFixed(0)}K` : 'No data yet'}
                </div>
              </div>
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=net_margin')}
              >
                <div className="metric-label">Net Margin</div>
                <div className="metric-value">{profitability.net_margin || 'No data yet'}</div>
                <div className={`metric-change ${profitability.avg_points > 0 ? 'positive' : 'neutral'}`}>
                  {profitability.avg_points > 0 ? `Avg points: ${profitability.avg_points}` : ''}
                </div>
              </div>
              <div
                className="profitability-metric clickable"
                onClick={() => navigate('/profitability?metric=volume')}
              >
                <div className="metric-label">Total Volume</div>
                <div className="metric-value">
                  {profitability.total_volume > 0
                    ? `$${(profitability.total_volume / 1000000).toFixed(1)}M`
                    : 'No data yet'}
                </div>
                <div className={`metric-change ${profitability.funded_ytd > 0 ? 'positive' : 'neutral'}`}>
                  {profitability.funded_ytd > 0 ? `${profitability.funded_ytd} funded YTD` : 'No data yet'}
                </div>
              </div>
            </div>
            <div className="profitability-insights">
              {(profitability.insights || []).length > 0 ? (
                profitability.insights.map((insight, idx) => (
                  <div key={idx} className="insight-item">
                    <span>{insight}</span>
                  </div>
                ))
              ) : (
                <div className="insight-item">
                  <span>Fund loans to see profitability insights</span>
                </div>
              )}
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
              {efficiency.customerSatisfaction != null && (
                <div className="efficiency-metric-card">
                  <div className="metric-label">Customer Satisfaction Score</div>
                  <div className="metric-value">{efficiency.customerSatisfaction}%</div>
                  <div className={`metric-change ${(efficiency.customerSatisfactionChange || 0) >= 0 ? 'positive' : 'negative'}`}>
                    {(efficiency.customerSatisfactionChange || 0) >= 0 ? '↑' : '↓'} {Math.abs(efficiency.customerSatisfactionChange || 0)}%
                  </div>
                </div>
              )}
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
      const taskCount = getAggregatedTasksCount();
      const hasTaskDetails = prioritizedTasks.length > 0 || loanIssuesList.length > 0;

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
            <span className="task-count">{taskCount} tasks</span>
          </div>

          {hasTaskDetails ? (
            <div className="task-detail-list">
              {prioritizedTasks.slice(0, 8).map((task, idx) => (
                <div
                  key={idx}
                  className={`task-detail-row priority-${(task.urgency || 'medium').toLowerCase()}`}
                  onClick={() => navigate('/tasks')}
                >
                  <div className="task-priority-indicator"></div>
                  <div className="task-detail-content">
                    <div className="task-detail-title">{task.title}</div>
                    <div className="task-detail-meta">
                      {task.borrower && <span className="task-borrower">{task.borrower}</span>}
                      {task.stage && <span className="task-stage">{task.stage}</span>}
                      {task.urgency && <span className={`task-urgency ${task.urgency.toLowerCase()}`}>{task.urgency}</span>}
                    </div>
                  </div>
                </div>
              ))}
              {loanIssuesList.slice(0, 4).map((issue, idx) => (
                <div
                  key={`issue-${idx}`}
                  className="task-detail-row priority-high"
                  onClick={() => navigate(`/loans/${issue.id}`)}
                >
                  <div className="task-priority-indicator"></div>
                  <div className="task-detail-content">
                    <div className="task-detail-title">{issue.issue}</div>
                    <div className="task-detail-meta">
                      <span className="task-borrower">{issue.borrower_name}</span>
                      <span className="task-stage">{issue.stage}</span>
                      <span className="task-urgency high">{issue.days_in_stage}d in stage</span>
                    </div>
                  </div>
                </div>
              ))}
              {taskCount > 8 && (
                <div className="task-view-more" onClick={() => navigate('/tasks')}>
                  View all {taskCount} tasks →
                </div>
              )}
            </div>
          ) : (
            <div className="task-summary-view clickable-container" onClick={() => navigate('/tasks')}>
              <div className="task-count-display">
                <div className="count-number">{taskCount}</div>
                <div className="count-label">Outstanding Tasks</div>
              </div>
              <div className="click-to-view">
                <p>Click to view all tasks →</p>
              </div>
            </div>
          )}
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
      // Always show for platform admin or if container is in the allowed list for this role
      const referralRoles = ['admin', 'site_admin', 'loan_officer', 'manager', 'sales', 'management'];
      const canViewReferrals = hasPermission('referrals.view') ||
                               referralRoles.includes(userRole) ||
                               referralRoles.includes(effectiveRole) ||
                               isPlatformAdmin() ||
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

    if (containerId === 'mum') {
      return (
        <div
          key={containerId}
          className={`dashboard-block mum-block draggable-container ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => handleDragOver(e, index)}
          onDragEnd={handleDragEnd}
        >
          <div
            className="drag-handle"
            title="Drag to reorder"
            draggable="true"
            onDragStart={() => handleDragStart(index)}
          >⋮⋮</div>
          <div className="block-header clickable-block" onClick={() => navigate('/portfolio')}>
            <h2>Mortgages Under Management</h2>
          </div>
          <div className="mum-metrics-grid">
            <div className="mum-metric" onClick={() => navigate('/portfolio')}>
              <div className="metric-label">Loans Managed</div>
              <div className="metric-value">{mumSummary.loan_count || 0}</div>
            </div>
            <div className="mum-metric" onClick={() => navigate('/portfolio')}>
              <div className="metric-label">Total Volume</div>
              <div className="metric-value">
                {mumSummary.total_volume > 0
                  ? `$${(mumSummary.total_volume / 1000000).toFixed(1)}M`
                  : 'No data yet'}
              </div>
            </div>
            <div className="mum-metric" onClick={() => navigate('/portfolio')}>
              <div className="metric-label">Annual Commission</div>
              <div className="metric-value">
                {mumSummary.annual_commission > 0
                  ? `$${mumSummary.annual_commission.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
                  : 'No data yet'}
              </div>
            </div>
            <div className="mum-metric" onClick={() => navigate('/portfolio')}>
              <div className="metric-label">Annual Return</div>
              <div className="metric-value">
                {mumSummary.annual_return_pct > 0
                  ? `${mumSummary.annual_return_pct}%`
                  : 'No data yet'}
              </div>
            </div>
          </div>
          <button
            className="btn-view-portfolio"
            onClick={() => navigate('/portfolio')}
          >
            View Full Portfolio →
          </button>
        </div>
      );
    }

    if (containerId === 'team' && teamStats.has_team) {
      // PHASE 4: Show for users with team.view_all/team.view_team permission or management roles
      // Always show for platform admin or if container is in the allowed list for this role
      const teamRoles = ['admin', 'site_admin', 'manager', 'executive', 'management'];
      const canViewTeam = hasPermission('team.view_all') ||
                          hasPermission('team.view_team') ||
                          teamRoles.includes(userRole) ||
                          teamRoles.includes(effectiveRole) ||
                          isPlatformAdmin() ||
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
                <div className="metric-value">{itTicketMetrics?.turn_time_display || '0h'}</div>
                <div className="metric-label">Avg Turn Time</div>
              </div>
            </div>
            <div className="it-ticket-metric" onClick={() => navigate('/support')}>
              <div className="metric-icon" style={{ background: 'linear-gradient(135deg, #B8924A, #8A6D30)' }}>
                <span>📅</span>
              </div>
              <div className="metric-content">
                <div className="metric-value">{itTicketMetrics?.tickets_this_month || 0}</div>
                <div className="metric-label">This Month</div>
              </div>
            </div>
            <div className="it-ticket-metric" onClick={() => navigate('/support?status=open')}>
              <div className="metric-icon" style={{ background: 'linear-gradient(135deg, #2D7A52, #2D7A52)' }}>
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

  const userData = getUserData();
  const firstName = userData?.first_name || 'there';
  const todayFormatted = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  const todayShort = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

  const goalData = loadGoalTrackerData();
  const annualPct = goalData.annualGoal > 0 ? Math.round((production.annualActual || 0) / goalData.annualGoal * 100) : (production.annualProgress || 0);
  const monthlyPct = goalData.monthlyGoal > 0 ? Math.round((production.monthlyActual || 0) / goalData.monthlyGoal * 100) : (production.monthlyProgress || 0);
  const weeklyPct = goalData.weeklyGoal > 0 ? Math.round((production.weeklyActual || 0) / goalData.weeklyGoal * 100) : (production.weeklyProgress || 0);
  const dailyPct = goalData.dailyGoal > 0 ? Math.round((production.dailyActual || 0) / goalData.dailyGoal * 100) : (production.dailyProgress || 0);

  if (dashboardView === 'manager' && isManagerOrAdmin) {
    return (
      <div className="dashboard">
        <div className="dashboard-header-compact">
          <h1>Manager Command Center</h1>
          <div className="header-actions">
            <div className="dashboard-view-toggle">
              <button className="view-toggle-btn" onClick={() => handleViewToggle('personal')}>My Dashboard</button>
              <button className="view-toggle-btn active" onClick={() => handleViewToggle('manager')}>Manager Dashboard</button>
            </div>
          </div>
        </div>
        {(hasPermission('team.manage_permissions') || userRole === 'management') && (
          <div style={{ marginBottom: '2rem' }}><PendingPermissionRequests /></div>
        )}
        <div className="draggable-containers-wrapper">
          {containerOrder.map((containerId, index) => renderDraggableContainer(containerId, index))}
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard cream-dashboard">
      {isRolePreview && rolePreview && (
        <div className="cream-role-preview-banner">
          <div className="preview-info">
            Previewing as: <strong>{rolePreview.role_name}</strong>
            <span className="preview-hint">(This is how a {rolePreview.role_name} sees their dashboard)</span>
          </div>
          <button className="btn btn-outline" onClick={exitRolePreview}>Exit Preview</button>
        </div>
      )}

      <div className="cream-page-header">
        <div>
          <div className="cream-page-title">Dashboard</div>
          <div className="cream-page-subtitle">Good morning, {firstName}. Here's your pipeline at a glance.</div>
        </div>
        <div className="cream-header-actions">
          {isManagerOrAdmin && (
            <div className="dashboard-view-toggle">
              <button className="view-toggle-btn active" onClick={() => handleViewToggle('personal')}>My Dashboard</button>
              <button className="view-toggle-btn" onClick={() => handleViewToggle('manager')}>Manager Dashboard</button>
            </div>
          )}
          <button className="btn btn-outline btn-sm" onClick={() => navigate('/briefing')}>View Morning Briefing</button>
        </div>
      </div>

      {/* AI Alerts */}
      <div className="cream-card cream-clickable" onClick={() => navigate('/tasks')} style={{ marginBottom: 16 }}>
        <div className="cream-card-header"><h3>AI Alerts</h3></div>
        <div className="cream-card-body" style={{ padding: 0 }}>
          {(leadMetrics.alerts || []).filter(a => a).length > 0 ? (
            (leadMetrics.alerts || []).filter(a => a).map((alert, idx) => (
              <div key={idx} className="cream-alert-row">
                <span className={`cream-alert-dot ${idx === 0 ? 'red' : idx === 1 ? 'amber' : idx === 2 ? 'green' : 'blue'}`}></span>
                <span>{alert}</span>
              </div>
            ))
          ) : (
            <div className="cream-alert-row">
              <span className="cream-alert-dot green"></span>
              <span>No active alerts. Your pipeline is looking healthy!</span>
            </div>
          )}
        </div>
      </div>

      {/* Production Tracker */}
      <div className="cream-card cream-clickable" onClick={() => navigate('/goal-tracker')} style={{ marginBottom: 16 }}>
        <div className="cream-card-header"><h3>Monthly Production Tracker</h3></div>
        <div className="cream-card-body">
          <div className="cream-metrics-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Annual Goal</div>
              <div className="cream-metric-value" style={{ fontSize: 22 }}>{formatGoalNumber(goalData.annualGoal || production.annualGoal)}</div>
              <div style={{ marginTop: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--bt-text-muted)', marginBottom: 3 }}>
                  <span>Actual: {formatGoalNumber(production.annualActual)}</span><span>{annualPct}%</span>
                </div>
                <div className="cream-progress-bar"><div className="cream-progress-fill green" style={{ width: `${Math.min(annualPct, 100)}%` }}></div></div>
              </div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Monthly Goal</div>
              <div className="cream-metric-value" style={{ fontSize: 22 }}>{formatGoalNumber(goalData.monthlyGoal || production.monthlyGoal)}</div>
              <div style={{ marginTop: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--bt-text-muted)', marginBottom: 3 }}>
                  <span>Actual: {formatGoalNumber(production.monthlyActual)}</span><span>{monthlyPct}%</span>
                </div>
                <div className="cream-progress-bar"><div className="cream-progress-fill green" style={{ width: `${Math.min(monthlyPct, 100)}%` }}></div></div>
              </div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Weekly Goal</div>
              <div className="cream-metric-value" style={{ fontSize: 22 }}>{formatGoalNumber(goalData.weeklyGoal || production.weeklyGoal)}</div>
              <div style={{ marginTop: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--bt-text-muted)', marginBottom: 3 }}>
                  <span>Actual: {formatGoalNumber(production.weeklyActual)}</span><span>{weeklyPct}%</span>
                </div>
                <div className="cream-progress-bar"><div className="cream-progress-fill green" style={{ width: `${Math.min(weeklyPct, 100)}%` }}></div></div>
              </div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Daily Goal</div>
              <div className="cream-metric-value" style={{ fontSize: 22 }}>{formatGoalNumber(goalData.dailyGoal || production.dailyGoal)}</div>
              <div style={{ marginTop: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--bt-text-muted)', marginBottom: 3 }}>
                  <span>Actual: {formatGoalNumber(production.dailyActual)}</span><span>{dailyPct}%</span>
                </div>
                <div className="cream-progress-bar"><div className="cream-progress-fill green" style={{ width: `${Math.min(dailyPct, 100)}%` }}></div></div>
              </div>
            </div>
          </div>
          {annualPct < 75 && (
            <div className="cream-alert-row" style={{ background: 'var(--bt-primary-tint)', borderRadius: 'var(--bt-radius-sm)', marginTop: 8 }}>
              <span className="cream-alert-dot blue"></span>
              <span style={{ fontSize: 12 }}><strong>AI Coaching:</strong> You're at {annualPct}% of your annual goal. Maintain your current pace and focus on converting pipeline deals to stay on track.</span>
            </div>
          )}
        </div>
      </div>

      {/* Mortgages Under Management */}
      <div className="cream-card cream-clickable" onClick={() => navigate('/portfolio')} style={{ marginBottom: 16 }}>
        <div className="cream-card-header"><h3>Mortgages Under Management</h3></div>
        <div className="cream-card-body">
          <div className="cream-metrics-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Total Clients</div>
              <div className="cream-metric-value">{mumSummary.loan_count || 0}</div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Portfolio Volume</div>
              <div className="cream-metric-value" style={{ fontSize: 20 }}>
                {mumSummary.total_volume > 0 ? `$${(mumSummary.total_volume / 1000000).toFixed(1)}M` : '$0'}
              </div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Monthly Payments</div>
              <div className="cream-metric-value" style={{ fontSize: 20 }}>
                {mumSummary.monthly_payments > 0 ? `$${(mumSummary.monthly_payments / 1000).toFixed(1)}K` : '$0'}
              </div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Refi Opportunities</div>
              <div className="cream-metric-value" style={{ color: 'var(--bt-success)' }}>{mumSummary.refi_opportunities || 0}</div>
            </div>
            <div className="cream-metric-card">
              <div className="cream-metric-label">Commission Opp.</div>
              <div className="cream-metric-value" style={{ fontSize: 20 }}>
                {mumSummary.annual_commission > 0 ? `$${Math.round(mumSummary.annual_commission / 1000)}K` : '$0'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline Efficiency + Today's Activity side by side */}
      <div className="cream-dash-grid">
        {/* Pipeline Efficiency */}
        <div className="cream-card cream-clickable" onClick={() => navigate('/scorecard')}>
          <div className="cream-card-header"><h3>Pipeline Efficiency Monitor</h3></div>
          <div className="cream-card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 14 }}>
              <div style={{ textAlign: 'center' }}>
                <div className={`cream-score-circle ${(efficiency.overallScore || 0) >= 80 ? '' : (efficiency.overallScore || 0) >= 60 ? 'warning' : 'critical'}`}>
                  {efficiency.overallScore || 0}
                </div>
                <div style={{ fontSize: 11, color: 'var(--bt-text-muted)' }}>Overall Score</div>
              </div>
              <div style={{ flex: 1 }}>
                <div className="cream-metrics-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <div className="cream-metric-label">Avg Time to Close</div>
                    <div style={{ fontWeight: 600 }}>{efficiency.avgTimeToClose || 0} days</div>
                    <div className={`cream-metric-change ${(efficiency.avgTimeToCloseChange || 0) < 0 ? 'up' : 'down'}`}>
                      {(efficiency.avgTimeToCloseChange || 0) < 0 ? '' : '+'}{efficiency.avgTimeToCloseChange || 0} days
                    </div>
                  </div>
                  <div>
                    <div className="cream-metric-label">Pull-Through Rate</div>
                    <div style={{ fontWeight: 600 }}>{efficiency.pullThroughRate || 0}%</div>
                    <div className={`cream-metric-change ${(efficiency.pullThroughRateChange || 0) >= 0 ? 'up' : 'down'}`}>
                      {(efficiency.pullThroughRateChange || 0) >= 0 ? '+' : ''}{efficiency.pullThroughRateChange || 0}%
                    </div>
                  </div>
                  <div>
                    <div className="cream-metric-label">Loans Falling Behind</div>
                    <div style={{ fontWeight: 600, color: (efficiency.loansFallingBehind || 0) > 0 ? 'var(--bt-warning)' : undefined }}>
                      {efficiency.loansFallingBehind || 0}
                    </div>
                  </div>
                  <div>
                    <div className="cream-metric-label">Automation Rate</div>
                    <div style={{ fontWeight: 600 }}>{efficiency.automationRate || 0}%</div>
                    <div className={`cream-metric-change ${(efficiency.automationRateChange || 0) >= 0 ? 'up' : 'down'}`}>
                      {(efficiency.automationRateChange || 0) >= 0 ? '+' : ''}{efficiency.automationRateChange || 0}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div>
              {(efficiency.stages || []).map((stage, idx) => (
                <div key={idx} className="cream-eff-row">
                  <span className="cream-eff-label">{stage.name}</span>
                  <div className="cream-eff-bar-bg">
                    <div className={`cream-eff-bar ${stage.status}`} style={{ width: `${stage.efficiency}%` }}></div>
                  </div>
                  <span className="cream-eff-pct">{stage.efficiency}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Today's Activity */}
        <div className="cream-card cream-clickable" onClick={() => navigate('/calendar')}>
          <div className="cream-card-header">
            <h3>Today's Activity</h3>
            <span style={{ fontSize: 11, color: 'var(--bt-text-muted)' }}>{todayShort}</span>
          </div>
          <div className="cream-card-body" style={{ padding: 0 }}>
            {(prioritizedTasks || []).slice(0, 5).map((task, idx) => {
              const colors = ['var(--bt-error)', 'var(--bt-accent)', 'var(--bt-primary)', 'var(--bt-info)', 'var(--bt-success)'];
              return (
                <div key={idx} className="cream-task-item" style={{ borderLeft: `3px solid ${colors[idx % colors.length]}` }}>
                  <div style={{ flex: 1 }}>
                    <div className="cream-task-title">{task.title}</div>
                    <div className="cream-task-meta">
                      {task.borrower && <span>{task.borrower}</span>}
                      {task.stage && <span>{task.stage}</span>}
                      {task.urgency && <span style={{ color: task.urgency === 'Critical' ? 'var(--bt-error)' : undefined }}>{task.urgency}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
            {(prioritizedTasks || []).length === 0 && (
              <div style={{ padding: '16px', fontSize: 13, color: 'var(--bt-text-muted)', textAlign: 'center' }}>
                No tasks scheduled for today
              </div>
            )}
            {(prioritizedTasks || []).length > 5 && (
              <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--bt-text-muted)', textAlign: 'center', borderTop: '1px solid var(--bt-border)' }}>
                {prioritizedTasks.length - 5} more items on your calendar
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Workflow Scorecards */}
      <div className="cream-card cream-clickable" onClick={() => navigate('/loans')} style={{ marginBottom: 16 }}>
        <div className="cream-card-header">
          <h3>Workflow Scorecards</h3>
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            Overall: <span style={{ color: (workflowScores.overallScore || 0) >= 80 ? 'var(--bt-success)' : (workflowScores.overallScore || 0) >= 60 ? 'var(--bt-warning)' : 'var(--bt-error)' }}>
              {workflowScores.overallScore || 0}%
            </span>
          </span>
        </div>
        <div className="cream-card-body">
          <div className="cream-workflow-grid">
            {(workflowScores.statuses || []).slice(0, 5).map((status, idx) => (
              <div key={idx} className={`cream-workflow-card ${status.health}`}>
                <div className="wf-name">{status.name}</div>
                <div className="wf-score" style={{ color: status.health === 'good' ? 'var(--bt-success)' : status.health === 'warning' ? 'var(--bt-warning)' : 'var(--bt-error)' }}>
                  {status.score}%
                </div>
                <div className="wf-meta">{status.activeLoans} loans &middot; {status.tasksCompleted}/{status.tasksDue} tasks</div>
              </div>
            ))}
          </div>
          {(workflowScores.statuses || []).length > 5 && (
            <div className="cream-workflow-grid">
              {(workflowScores.statuses || []).slice(5, 10).map((status, idx) => (
                <div key={idx} className={`cream-workflow-card ${status.health}`}>
                  <div className="wf-name">{status.name}</div>
                  <div className="wf-score" style={{ color: status.health === 'good' ? 'var(--bt-success)' : status.health === 'warning' ? 'var(--bt-warning)' : 'var(--bt-error)' }}>
                    {status.score}%
                  </div>
                  <div className="wf-meta">{status.activeLoans} loans &middot; {status.tasksCompleted}/{status.tasksDue} tasks</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Referral Scoreboard */}
      <div className="cream-dash-grid">
        <div className="cream-card cream-clickable" onClick={() => navigate('/referral-partners')}>
          <div className="cream-card-header"><h3>Referral Scoreboard</h3></div>
          <div className="cream-card-body">
            <table className="cream-data-table">
              <thead>
                <tr><th>Partner</th><th>Referrals</th><th>Closed</th><th>Pipeline</th></tr>
              </thead>
              <tbody>
                {(referralStats.top_partners || []).filter(p => p && p.name).slice(0, 5).map((partner, idx) => (
                  <tr key={idx}>
                    <td className="name-cell">{partner.name}</td>
                    <td>{partner.received || 0}</td>
                    <td>{partner.closed || partner.sent || 0}</td>
                    <td>{partner.pipeline_volume ? `$${(partner.pipeline_volume / 1000).toFixed(0)}K` : '-'}</td>
                  </tr>
                ))}
                {(referralStats.top_partners || []).filter(p => p && p.name).length === 0 && (
                  <tr><td colSpan="4" style={{ textAlign: 'center', color: 'var(--bt-text-muted)' }}>No referral partners yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Morning Briefing Card */}
      <BriefingErrorBoundary>
        <MorningBriefingCard />
      </BriefingErrorBoundary>
    </div>
  );
}

export default Dashboard;
