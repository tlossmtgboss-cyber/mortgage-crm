import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getDashboardOverview,
  getUserCosts,
  getTeamCosts,
  getOrganizationTrend,
  getProjections,
  getPricingRecommendation,
  getAIModelCosts,
  getUsageAlerts,
  formatCurrency,
  formatNumber,
  formatPercent
} from '../services/usageIntelligenceApi';
import { usePermissions } from '../contexts/PermissionContext';
import './UsageIntelligenceDashboard.css';

/**
 * Usage Intelligence Dashboard
 *
 * Owner-only dashboard for tracking per-user costs, projections,
 * and pricing recommendations for 200% profit margin.
 */
function UsageIntelligenceDashboard() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - owner/admin only
  const canAccessUsageIntel = isAdmin || hasAnyPermission(['admin.manage', 'usage.view', 'billing.view', 'system.admin']) || userRole === 'admin';

  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data states
  const [overview, setOverview] = useState(null);
  const [users, setUsers] = useState(null);
  const [teams, setTeams] = useState(null);
  const [trend, setTrend] = useState(null);
  const [projections, setProjections] = useState(null);
  const [pricing, setPricing] = useState(null);
  const [aiModels, setAIModels] = useState(null);
  const [alerts, setAlerts] = useState(null);

  // Filter states
  const [periodDays, setPeriodDays] = useState(30);
  const [projectionPeriod, setProjectionPeriod] = useState(30);
  const [targetMargin, setTargetMargin] = useState(200);

  // Load initial data
  useEffect(() => {
    loadOverview();
  }, []);

  // Load data when tab changes
  useEffect(() => {
    switch (activeTab) {
      case 'overview':
        loadOverview();
        break;
      case 'users':
        loadUsers();
        break;
      case 'teams':
        loadTeams();
        break;
      case 'projections':
        loadProjections();
        break;
      case 'pricing':
        loadPricing();
        break;
      case 'ai-models':
        loadAIModels();
        break;
      default:
        break;
    }
  }, [activeTab, periodDays]);

  const loadOverview = async () => {
    try {
      setLoading(true);
      const [overviewData, trendData, alertsData] = await Promise.all([
        getDashboardOverview(),
        getOrganizationTrend(periodDays),
        getUsageAlerts('active', 5)
      ]);
      setOverview(overviewData);
      setTrend(trendData);
      setAlerts(alertsData);
      setError(null);
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      setLoading(true);
      const data = await getUserCosts(periodDays, 50);
      setUsers(data);
      setError(null);
    } catch (err) {
      setError('Failed to load user costs');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadTeams = async () => {
    try {
      setLoading(true);
      const data = await getTeamCosts(periodDays);
      setTeams(data);
      setError(null);
    } catch (err) {
      setError('Failed to load team costs');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadProjections = async () => {
    try {
      setLoading(true);
      const data = await getProjections('organization', null, projectionPeriod);
      setProjections(data);
      setError(null);
    } catch (err) {
      setError('Failed to load projections');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadPricing = async () => {
    try {
      setLoading(true);
      const data = await getPricingRecommendation(targetMargin, periodDays);
      setPricing(data);
      setError(null);
    } catch (err) {
      setError('Failed to load pricing recommendations');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadAIModels = async () => {
    try {
      setLoading(true);
      const data = await getAIModelCosts(periodDays);
      setAIModels(data);
      setError(null);
    } catch (err) {
      setError('Failed to load AI model costs');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Render KPI Card
  const KPICard = ({ title, value, subtext, trend: trendVal, icon }) => (
    <div className="ui-kpi-card">
      <div className="ui-kpi-icon">
        <i className={`fas ${icon}`}></i>
      </div>
      <div className="ui-kpi-content">
        <div className="ui-kpi-title">{title}</div>
        <div className="ui-kpi-value">{value}</div>
        {subtext && <div className="ui-kpi-subtext">{subtext}</div>}
        {trendVal !== undefined && (
          <div className={`ui-kpi-trend ${trendVal >= 0 ? 'positive' : 'negative'}`}>
            <i className={`fas fa-arrow-${trendVal >= 0 ? 'up' : 'down'}`}></i>
            {formatPercent(trendVal)} vs last month
          </div>
        )}
      </div>
    </div>
  );

  // Overview Tab
  const renderOverview = () => {
    if (!overview) return null;

    return (
      <div className="ui-overview">
        <div className="ui-kpi-grid">
          <KPICard
            title="MTD Cost"
            value={formatCurrency(overview.kpis.mtd_cost)}
            subtext={`${overview.kpis.days_elapsed} days`}
            icon="fa-dollar-sign"
          />
          <KPICard
            title="Projected Monthly"
            value={formatCurrency(overview.kpis.projected_monthly)}
            trend={overview.kpis.mom_change_pct}
            icon="fa-chart-line"
          />
          <KPICard
            title="Avg Daily Cost"
            value={formatCurrency(overview.kpis.avg_daily_cost)}
            icon="fa-calendar-day"
          />
          <KPICard
            title="Active Users"
            value={overview.kpis.active_users}
            icon="fa-users"
          />
        </div>

        <div className="ui-overview-grid">
          <div className="ui-card">
            <h3>Cost Breakdown</h3>
            <div className="ui-cost-breakdown">
              <div className="ui-cost-item">
                <span className="ui-cost-label">AI Tokens</span>
                <span className="ui-cost-value">{formatCurrency(overview.cost_breakdown.ai_tokens)}</span>
              </div>
              <div className="ui-cost-item">
                <span className="ui-cost-label">Communications</span>
                <span className="ui-cost-value">{formatCurrency(overview.cost_breakdown.communications)}</span>
              </div>
              <div className="ui-cost-item">
                <span className="ui-cost-label">Storage</span>
                <span className="ui-cost-value">{formatCurrency(overview.cost_breakdown.storage)}</span>
              </div>
            </div>
          </div>

          <div className="ui-card">
            <h3>30-Day Projection</h3>
            <div className="ui-projection-summary">
              <div className="ui-projection-main">
                <div className="ui-projection-value">{formatCurrency(overview.projection_30d.projected_cost)}</div>
                <div className="ui-projection-range">
                  Range: {formatCurrency(overview.projection_30d.confidence_low)} - {formatCurrency(overview.projection_30d.confidence_high)}
                </div>
              </div>
              <div className={`ui-trend-badge ${overview.projection_30d.trend_direction}`}>
                <i className={`fas fa-arrow-${overview.projection_30d.trend_direction === 'increasing' ? 'up' : overview.projection_30d.trend_direction === 'decreasing' ? 'down' : 'right'}`}></i>
                {overview.projection_30d.trend_direction} ({formatPercent(overview.projection_30d.trend_percentage)})
              </div>
            </div>
          </div>

          {alerts && alerts.alerts.length > 0 && (
            <div className="ui-card ui-alerts-card">
              <h3>Active Alerts</h3>
              <div className="ui-alerts-list">
                {alerts.alerts.map(alert => (
                  <div key={alert.id} className={`ui-alert-item ${alert.severity}`}>
                    <i className={`fas fa-${alert.severity === 'critical' ? 'exclamation-circle' : 'exclamation-triangle'}`}></i>
                    <div className="ui-alert-content">
                      <div className="ui-alert-title">{alert.title}</div>
                      <div className="ui-alert-message">{alert.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {trend && trend.data && trend.data.length > 0 && (
          <div className="ui-card ui-trend-card">
            <h3>Cost Trend ({periodDays} Days)</h3>
            <div className="ui-simple-chart">
              {trend.data.map((day, idx) => (
                <div key={idx} className="ui-chart-bar-container">
                  <div
                    className="ui-chart-bar"
                    style={{ height: `${Math.min(100, (day.total_cost / Math.max(...trend.data.map(d => d.total_cost))) * 100)}%` }}
                    title={`${day.date}: ${formatCurrency(day.total_cost)}`}
                  ></div>
                  <span className="ui-chart-label">{day.date.slice(-2)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // Users Tab
  const renderUsers = () => {
    if (!users) return null;

    return (
      <div className="ui-users">
        <div className="ui-section-header">
          <h3>User Cost Ranking</h3>
          <div className="ui-total">Total: {formatCurrency(users.total_cost)}</div>
        </div>

        <table className="ui-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>User</th>
              <th>Total Cost</th>
              <th>% of Total</th>
              <th>Tokens Used</th>
              <th>Requests</th>
              <th>Active Days</th>
              <th>Avg Daily</th>
            </tr>
          </thead>
          <tbody>
            {users.users.map(user => (
              <tr key={user.user_id}>
                <td className="ui-rank">#{user.rank}</td>
                <td>
                  <div className="ui-user-info">
                    <div className="ui-user-name">{user.name}</div>
                    <div className="ui-user-email">{user.email}</div>
                  </div>
                </td>
                <td className="ui-cost">{formatCurrency(user.total_cost)}</td>
                <td>
                  <div className="ui-pct-bar">
                    <div className="ui-pct-fill" style={{ width: `${user.pct_of_total}%` }}></div>
                    <span>{user.pct_of_total}%</span>
                  </div>
                </td>
                <td>{formatNumber(user.total_tokens)}</td>
                <td>{formatNumber(user.request_count)}</td>
                <td>{user.active_days}</td>
                <td>{formatCurrency(user.avg_daily_cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // Teams Tab
  const renderTeams = () => {
    if (!teams) return null;

    return (
      <div className="ui-teams">
        <div className="ui-section-header">
          <h3>Team Cost Breakdown</h3>
          <div className="ui-total">Total: {formatCurrency(teams.total_cost)}</div>
        </div>

        <div className="ui-team-cards">
          {teams.teams.map(team => (
            <div key={team.team_id} className="ui-team-card">
              <div className="ui-team-header">
                <h4>{team.team_name}</h4>
                <span className="ui-team-pct">{team.pct_of_total}%</span>
              </div>
              <div className="ui-team-cost">{formatCurrency(team.total_cost)}</div>
              <div className="ui-team-details">
                <div><span>Users:</span> {team.user_count}</div>
                <div><span>Cost/User:</span> {formatCurrency(team.cost_per_user)}</div>
              </div>
              <div className="ui-team-breakdown">
                <div className="ui-breakdown-item">
                  <span>AI</span>
                  <span>{formatCurrency(team.ai_cost)}</span>
                </div>
                <div className="ui-breakdown-item">
                  <span>Comm</span>
                  <span>{formatCurrency(team.communications_cost)}</span>
                </div>
                <div className="ui-breakdown-item">
                  <span>Storage</span>
                  <span>{formatCurrency(team.storage_cost)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // Projections Tab
  const renderProjections = () => {
    if (!projections) return null;

    return (
      <div className="ui-projections">
        <div className="ui-projection-controls">
          <button
            className={projectionPeriod === 30 ? 'active' : ''}
            onClick={() => { setProjectionPeriod(30); }}
          >
            30 Days
          </button>
          <button
            className={projectionPeriod === 60 ? 'active' : ''}
            onClick={() => { setProjectionPeriod(60); }}
          >
            60 Days
          </button>
          <button
            className={projectionPeriod === 90 ? 'active' : ''}
            onClick={() => { setProjectionPeriod(90); }}
          >
            90 Days
          </button>
        </div>

        <div className="ui-projection-main-card">
          <h3>{projectionPeriod}-Day Projection</h3>
          <div className="ui-projection-big-value">
            {formatCurrency(projections.projected_cost)}
          </div>
          <div className="ui-projection-confidence">
            95% Confidence Interval:
            <span>{formatCurrency(projections.confidence_interval_low)}</span> -
            <span>{formatCurrency(projections.confidence_interval_high)}</span>
          </div>
          <div className={`ui-projection-trend ${projections.trend_direction}`}>
            <i className={`fas fa-arrow-${projections.trend_direction === 'increasing' ? 'up' : projections.trend_direction === 'decreasing' ? 'down' : 'right'}`}></i>
            Trend: {projections.trend_direction} ({formatPercent(projections.trend_percentage)})
          </div>
          <div className="ui-projection-confidence-score">
            Confidence Score: {projections.confidence_score}%
          </div>
        </div>

        {projections.projected_by_category && (
          <div className="ui-card">
            <h3>Projection by Category</h3>
            <div className="ui-category-projections">
              {Object.entries(projections.projected_by_category).map(([category, data]) => (
                <div key={category} className="ui-category-item">
                  <div className="ui-category-name">{category.replace('_', ' ')}</div>
                  <div className="ui-category-value">{formatCurrency(data.projected)}</div>
                  <div className={`ui-category-trend ${data.trend}`}>
                    {data.trend} ({formatPercent(data.pct)})
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {projections.alerts && projections.alerts.length > 0 && (
          <div className="ui-card ui-projection-alerts">
            <h3>Projection Alerts</h3>
            {projections.alerts.map((alert, idx) => (
              <div key={idx} className="ui-projection-alert">{alert}</div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Pricing Tab
  const renderPricing = () => {
    if (!pricing) return null;

    return (
      <div className="ui-pricing">
        <div className="ui-pricing-controls">
          <label>
            Target Margin:
            <select value={targetMargin} onChange={e => setTargetMargin(Number(e.target.value))}>
              <option value={100}>100% (2x cost)</option>
              <option value={150}>150% (2.5x cost)</option>
              <option value={200}>200% (3x cost)</option>
              <option value={250}>250% (3.5x cost)</option>
              <option value={300}>300% (4x cost)</option>
            </select>
          </label>
          <button onClick={loadPricing}>Recalculate</button>
        </div>

        <div className="ui-pricing-grid">
          <div className="ui-card ui-pricing-summary">
            <h3>Actual Costs ({pricing.period_days} days)</h3>
            <div className="ui-pricing-metric">
              <span>Total Cost</span>
              <span className="ui-big-value">{formatCurrency(pricing.total_actual_cost)}</span>
            </div>
            <div className="ui-pricing-metric">
              <span>Cost Per User</span>
              <span>{formatCurrency(pricing.avg_cost_per_user)}</span>
            </div>
            <div className="ui-pricing-metric">
              <span>Cost Per Active User</span>
              <span>{formatCurrency(pricing.avg_cost_per_active_user)}</span>
            </div>
            <div className="ui-pricing-metric">
              <span>Total Users</span>
              <span>{pricing.total_users}</span>
            </div>
            <div className="ui-pricing-metric">
              <span>Active Users</span>
              <span>{pricing.active_users}</span>
            </div>
          </div>

          <div className="ui-card ui-pricing-recommendation">
            <h3>Recommended Pricing ({pricing.target_margin_pct}% margin)</h3>
            <div className="ui-pricing-main">
              <div className="ui-recommended-price">
                <span>Base Price</span>
                <span className="ui-big-value">{formatCurrency(pricing.recommended_base_price)}/mo</span>
              </div>
              <div className="ui-recommended-price">
                <span>Per User</span>
                <span className="ui-big-value">{formatCurrency(pricing.recommended_per_user_price)}/mo</span>
              </div>
            </div>
            <div className="ui-pricing-projection">
              <div className="ui-pricing-metric">
                <span>Projected Revenue</span>
                <span className="ui-positive">{formatCurrency(pricing.projected_revenue_at_recommended)}</span>
              </div>
              <div className="ui-pricing-metric">
                <span>Projected Profit</span>
                <span className="ui-positive">{formatCurrency(pricing.projected_profit_at_recommended)}</span>
              </div>
              <div className="ui-pricing-metric">
                <span>Actual Margin</span>
                <span>{pricing.actual_margin_at_recommended}%</span>
              </div>
            </div>
          </div>

          <div className="ui-card">
            <h3>Cost Breakdown</h3>
            <div className="ui-cost-breakdown-table">
              {Object.entries(pricing.cost_breakdown).map(([category, data]) => (
                <div key={category} className="ui-breakdown-row">
                  <span className="ui-breakdown-category">{category.replace('_', ' ')}</span>
                  <span className="ui-breakdown-total">{formatCurrency(data.total)}</span>
                  <span className="ui-breakdown-per-user">{formatCurrency(data.per_user)}/user</span>
                  <span className="ui-breakdown-pct">{data.pct_of_total.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="ui-card">
            <h3>Recommended Usage Fees</h3>
            <div className="ui-usage-fees">
              {Object.entries(pricing.recommended_usage_fees).map(([key, value]) => (
                <div key={key} className="ui-fee-item">
                  <span>{key.replace(/_/g, ' ')}</span>
                  <span>{formatCurrency(value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {pricing.recommendations && pricing.recommendations.length > 0 && (
          <div className="ui-card ui-pricing-recommendations">
            <h3>Recommendations</h3>
            <ul>
              {pricing.recommendations.map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  // AI Models Tab
  const renderAIModels = () => {
    if (!aiModels) return null;

    return (
      <div className="ui-ai-models">
        <div className="ui-section-header">
          <h3>AI Model Usage</h3>
          <div className="ui-total">Total: {formatCurrency(aiModels.total_cost)}</div>
        </div>

        <table className="ui-table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Model</th>
              <th>Total Cost</th>
              <th>% of Total</th>
              <th>Input Tokens</th>
              <th>Output Tokens</th>
              <th>Requests</th>
              <th>Cost/Request</th>
              <th>Avg Latency</th>
            </tr>
          </thead>
          <tbody>
            {aiModels.models.map((model, idx) => (
              <tr key={idx}>
                <td className="ui-provider">{model.provider}</td>
                <td className="ui-model-name">{model.model}</td>
                <td className="ui-cost">{formatCurrency(model.total_cost)}</td>
                <td>
                  <div className="ui-pct-bar">
                    <div className="ui-pct-fill" style={{ width: `${model.pct_of_total}%` }}></div>
                    <span>{model.pct_of_total}%</span>
                  </div>
                </td>
                <td>{formatNumber(model.input_tokens)}</td>
                <td>{formatNumber(model.output_tokens)}</td>
                <td>{formatNumber(model.request_count)}</td>
                <td>{formatCurrency(model.cost_per_request)}</td>
                <td>{model.avg_latency_ms}ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // Access denied if user doesn't have admin permissions
  if (!canAccessUsageIntel) {
    return (
      <div className="usage-intelligence-dashboard">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to view Usage Intelligence.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="usage-intelligence-dashboard">
      <div className="ui-header">
        <h1>Usage Intelligence</h1>
        <p>Cost tracking and pricing recommendations for profit margin analysis</p>
      </div>

      <div className="ui-controls">
        <div className="ui-tabs">
          <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>
            Overview
          </button>
          <button className={activeTab === 'users' ? 'active' : ''} onClick={() => setActiveTab('users')}>
            User Costs
          </button>
          <button className={activeTab === 'teams' ? 'active' : ''} onClick={() => setActiveTab('teams')}>
            Team Costs
          </button>
          <button className={activeTab === 'projections' ? 'active' : ''} onClick={() => setActiveTab('projections')}>
            Projections
          </button>
          <button className={activeTab === 'pricing' ? 'active' : ''} onClick={() => setActiveTab('pricing')}>
            Pricing Calculator
          </button>
          <button className={activeTab === 'ai-models' ? 'active' : ''} onClick={() => setActiveTab('ai-models')}>
            AI Models
          </button>
        </div>

        <div className="ui-period-select">
          <label>Period:</label>
          <select value={periodDays} onChange={e => setPeriodDays(Number(e.target.value))}>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="ui-error">
          <i className="fas fa-exclamation-circle"></i>
          {error}
        </div>
      )}

      {loading ? (
        <div className="ui-loading">
          <i className="fas fa-spinner fa-spin"></i>
          Loading...
        </div>
      ) : (
        <div className="ui-content">
          {activeTab === 'overview' && renderOverview()}
          {activeTab === 'users' && renderUsers()}
          {activeTab === 'teams' && renderTeams()}
          {activeTab === 'projections' && renderProjections()}
          {activeTab === 'pricing' && renderPricing()}
          {activeTab === 'ai-models' && renderAIModels()}
        </div>
      )}
    </div>
  );
}

export default UsageIntelligenceDashboard;
