import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { profitabilityAPI } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar
} from 'recharts';
import './ProfitabilityDashboard.css';
import CostToCloseChart from '../components/CostToCloseChart';

const ProfitabilityDashboard = () => {
  const navigate = useNavigate();
  const { hasPermission, userRole } = usePermissions();

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedMonth, setSelectedMonth] = useState('');
  const [metrics, setMetrics] = useState(null);
  const [roleProfitability, setRoleProfitability] = useState([]);
  const [topPerformers, setTopPerformers] = useState([]);
  const [trends, setTrends] = useState([]);
  const [gapsGains, setGapsGains] = useState([]);
  const [insights, setInsights] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');

  // AI Assistant State
  const [aiQuery, setAiQuery] = useState('');
  const [aiResponse, setAiResponse] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [recommendations, setRecommendations] = useState([]);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [hiringRole, setHiringRole] = useState('');
  const [hiringSalary, setHiringSalary] = useState('');
  const [hiringAnalysis, setHiringAnalysis] = useState(null);

  // Get current month in YYYY-MM format
  const getCurrentMonth = () => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  };

  // Load dashboard data
  useEffect(() => {
    const month = selectedMonth || getCurrentMonth();
    fetchDashboardData(month);
  }, [selectedMonth]);

  const fetchDashboardData = async (month) => {
    try {
      setLoading(true);
      setError('');

      const data = await profitabilityAPI.getDashboard(month);

      setMetrics(data.metrics);
      setRoleProfitability(data.role_profitability || []);
      setTopPerformers(data.top_performers || []);
      setTrends(data.trends || []);
      setGapsGains(data.gaps_and_gains || []);
      setInsights(data.insights || []);
    } catch (err) {
      console.error('Failed to load profitability data:', err);
      setError('Failed to load profitability data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0
    }).format(amount);
  };

  // Format percentage
  const formatPercent = (value) => {
    if (value === null || value === undefined) return '0%';
    return `${Number(value).toFixed(1)}%`;
  };

  // Get status color class
  const getStatusClass = (value, threshold = 0) => {
    if (value > threshold) return 'positive';
    if (value < threshold) return 'negative';
    return 'neutral';
  };

  // Generate month options for selector
  const getMonthOptions = () => {
    const options = [];
    const now = new Date();
    for (let i = 0; i < 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      const label = date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      options.push({ value, label });
    }
    return options;
  };

  // Acknowledge insight
  const handleAcknowledgeInsight = async (id) => {
    try {
      await profitabilityAPI.acknowledgeInsight(id);
      setInsights(insights.filter(i => i.id !== id));
    } catch (err) {
      console.error('Failed to acknowledge insight:', err);
    }
  };

  // AI Assistant functions
  const handleAIQuery = async (question = null) => {
    const queryText = question || aiQuery;
    if (!queryText.trim()) return;

    try {
      setAiLoading(true);
      const response = await profitabilityAPI.queryAI(queryText, selectedMonth || null);
      setAiResponse(response);
      setAiQuery('');
    } catch (err) {
      console.error('AI query failed:', err);
      setAiResponse({
        question: queryText,
        answer: 'Sorry, I was unable to process your question. Please try again.',
        error: true
      });
    } finally {
      setAiLoading(false);
    }
  };

  const loadRecommendations = async () => {
    try {
      setAiLoading(true);
      const data = await profitabilityAPI.getAIRecommendations(selectedMonth || null);
      setRecommendations(data.recommendations || []);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
    } finally {
      setAiLoading(false);
    }
  };

  const loadSuggestedQuestions = async () => {
    try {
      const data = await profitabilityAPI.getSuggestedQuestions();
      setSuggestedQuestions(data.questions || []);
    } catch (err) {
      console.error('Failed to load suggested questions:', err);
    }
  };

  const handleHiringAnalysis = async () => {
    if (!hiringRole || !hiringSalary) return;

    try {
      setAiLoading(true);
      const response = await profitabilityAPI.analyzeHiring(
        hiringRole,
        parseFloat(hiringSalary),
        selectedMonth || null
      );
      setHiringAnalysis(response);
    } catch (err) {
      console.error('Hiring analysis failed:', err);
    } finally {
      setAiLoading(false);
    }
  };

  // Load suggested questions on mount
  useEffect(() => {
    loadSuggestedQuestions();
  }, []);

  if (loading) {
    return (
      <div className="profitability-dashboard">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading profitability data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="profitability-dashboard">
        <div className="error-container">
          <p>{error}</p>
          <button onClick={() => fetchDashboardData(selectedMonth || getCurrentMonth())}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="profitability-dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-content">
          <h1>Profitability Intelligence</h1>
          <p className="header-subtitle">Real-time business performance analytics</p>
        </div>
        <div className="header-actions">
          <select
            value={selectedMonth || getCurrentMonth()}
            onChange={(e) => setSelectedMonth(e.target.value)}
            className="month-selector"
          >
            {getMonthOptions().map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            className="btn-secondary"
            onClick={() => navigate('/profitability/scenarios')}
          >
            Scenario Modeling
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="dashboard-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab ${activeTab === 'roles' ? 'active' : ''}`}
          onClick={() => setActiveTab('roles')}
        >
          Role Analysis
        </button>
        <button
          className={`tab ${activeTab === 'employees' ? 'active' : ''}`}
          onClick={() => setActiveTab('employees')}
        >
          Top Performers
        </button>
        <button
          className={`tab ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveTab('insights')}
        >
          Insights {insights.length > 0 && <span className="badge">{insights.length}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'ai' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai')}
        >
          AI Assistant
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && metrics && (
        <>
          {/* Key Metrics Cards */}
          <div className="metrics-grid">
            <div className="metric-card primary">
              <div className="metric-icon">$</div>
              <div className="metric-content">
                <span className="metric-value">{formatCurrency(metrics.net_profit)}</span>
                <span className="metric-label">Net Profit</span>
              </div>
              <span className={`metric-badge ${getStatusClass(metrics.net_profit)}`}>
                {formatPercent(metrics.profit_margin)} margin
              </span>
            </div>

            <div className="metric-card">
              <div className="metric-icon">$</div>
              <div className="metric-content">
                <span className="metric-value">{formatCurrency(metrics.total_revenue)}</span>
                <span className="metric-label">Total Revenue</span>
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-icon">$</div>
              <div className="metric-content">
                <span className="metric-value">{formatCurrency(metrics.total_expenses)}</span>
                <span className="metric-label">Total Expenses</span>
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-icon">#</div>
              <div className="metric-content">
                <span className="metric-value">{metrics.loans_closed}</span>
                <span className="metric-label">Loans Closed</span>
              </div>
            </div>
          </div>

          {/* Cost Analysis Row */}
          <div className="analysis-row">
            <div className="analysis-card">
              <h3>Cost Per Loan</h3>
              <div className="analysis-value">{formatCurrency(metrics.cost_per_loan)}</div>
              <p className="analysis-detail">
                Revenue per loan: {formatCurrency(metrics.revenue_per_loan)}
              </p>
              <p className="analysis-detail">
                Profit per loan: <span className={getStatusClass(metrics.profit_per_loan)}>
                  {formatCurrency(metrics.profit_per_loan)}
                </span>
              </p>
            </div>

            <div className="analysis-card">
              <h3>Break-Even Analysis</h3>
              <div className="analysis-value">{metrics.break_even_loans} loans</div>
              <p className="analysis-detail">
                Current: {metrics.loans_closed} loans
              </p>
              <p className="analysis-detail">
                {metrics.loans_closed >= metrics.break_even_loans ? (
                  <span className="positive">
                    {metrics.loans_closed - metrics.break_even_loans} above break-even
                  </span>
                ) : (
                  <span className="negative">
                    {metrics.break_even_loans - metrics.loans_closed} below break-even
                  </span>
                )}
              </p>
            </div>

            <div className="analysis-card">
              <h3>Team Size</h3>
              <div className="analysis-value">{metrics.employee_count}</div>
              <p className="analysis-detail">Active employees</p>
              <p className="analysis-detail">
                Avg cost: {formatCurrency(metrics.total_expenses / (metrics.employee_count || 1))}
              </p>
            </div>
          </div>

          {/* Real-time Cost to Close Chart */}
          <div className="chart-container">
            <CostToCloseChart
              refreshInterval={60000}
              showLiveIndicator={true}
              height={280}
            />
          </div>

          {/* Trends Chart */}
          {trends.length > 0 && (
            <div className="chart-container">
              <h3>12-Month Trends</h3>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={trends}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
                  <Tooltip
                    formatter={(value) => formatCurrency(value)}
                    labelStyle={{ color: '#374151' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="revenue"
                    stackId="1"
                    stroke="#10b981"
                    fill="#d1fae5"
                    name="Revenue"
                  />
                  <Area
                    type="monotone"
                    dataKey="expenses"
                    stackId="2"
                    stroke="#ef4444"
                    fill="#fee2e2"
                    name="Expenses"
                  />
                  <Line
                    type="monotone"
                    dataKey="profit"
                    stroke="#d97757"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    name="Profit"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Gaps & Gains */}
          {gapsGains.length > 0 && (
            <div className="gaps-gains-section">
              <h3>Gaps & Opportunities</h3>
              <div className="gaps-gains-grid">
                {gapsGains.slice(0, 6).map((item, index) => (
                  <div key={index} className={`gap-gain-card ${item.type}`}>
                    <div className="card-header">
                      <span className={`type-badge ${item.type}`}>
                        {item.type === 'gap' ? 'Gap' : 'Gain'}
                      </span>
                      <span className={`priority-badge ${item.priority}`}>
                        {item.priority}
                      </span>
                    </div>
                    <h4>{item.title}</h4>
                    <p>{item.description}</p>
                    <div className="card-footer">
                      <span className="impact">
                        Impact: {formatCurrency(item.impact)}
                      </span>
                      <span className="action">{item.action}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Role Analysis Tab */}
      {activeTab === 'roles' && (
        <div className="roles-section">
          <h3>Role Profitability Analysis</h3>
          {roleProfitability.length > 0 ? (
            <div className="roles-table-container">
              <table className="roles-table">
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Department</th>
                    <th>Employees</th>
                    <th>Total Cost</th>
                    <th>Revenue</th>
                    <th>Net Contribution</th>
                    <th>ROI</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {roleProfitability.map((role) => (
                    <tr key={role.role_id} className={role.is_profitable ? 'profitable' : 'unprofitable'}>
                      <td className="role-name">{role.role_name}</td>
                      <td>{role.department || '-'}</td>
                      <td>{role.employee_count}</td>
                      <td>{formatCurrency(role.total_cost)}</td>
                      <td>{formatCurrency(role.total_revenue)}</td>
                      <td className={getStatusClass(role.net_contribution)}>
                        {formatCurrency(role.net_contribution)}
                      </td>
                      <td className={getStatusClass(role.roi_percentage)}>
                        {formatPercent(role.roi_percentage)}
                      </td>
                      <td>
                        <span className={`status-badge ${role.is_profitable ? 'profitable' : 'unprofitable'}`}>
                          {role.is_profitable ? 'Profitable' : 'Loss'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="no-data">No role data available. Add roles and employee costs to see analysis.</p>
          )}

          {/* Role Profitability Chart */}
          {roleProfitability.length > 0 && (
            <div className="chart-container">
              <h4>Net Contribution by Role</h4>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={roleProfitability} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                  <YAxis dataKey="role_name" type="category" width={120} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value) => formatCurrency(value)} />
                  <Bar
                    dataKey="net_contribution"
                    fill="#d97757"
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Top Performers Tab */}
      {activeTab === 'employees' && (
        <div className="performers-section">
          <h3>Top Performing Employees</h3>
          {topPerformers.length > 0 ? (
            <div className="performers-grid">
              {topPerformers.map((emp, index) => (
                <div key={emp.employee_id} className="performer-card">
                  <div className="performer-rank">#{index + 1}</div>
                  <div className="performer-info">
                    <h4>{emp.employee_name}</h4>
                    <span className="performer-role">{emp.role_name || 'N/A'}</span>
                  </div>
                  <div className="performer-metrics">
                    <div className="perf-metric">
                      <span className="perf-value">{formatPercent(emp.roi_percentage)}</span>
                      <span className="perf-label">ROI</span>
                    </div>
                    <div className="perf-metric">
                      <span className="perf-value">{formatCurrency(emp.net_contribution)}</span>
                      <span className="perf-label">Net Contribution</span>
                    </div>
                    <div className="perf-metric">
                      <span className="perf-value">{emp.loans_closed}</span>
                      <span className="perf-label">Loans</span>
                    </div>
                    <div className="perf-metric">
                      <span className="perf-value">{formatCurrency(emp.revenue_per_loan)}</span>
                      <span className="perf-label">Revenue/Loan</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-data">No employee performance data available.</p>
          )}
        </div>
      )}

      {/* Insights Tab */}
      {activeTab === 'insights' && (
        <div className="insights-section">
          <h3>AI-Powered Insights</h3>
          {insights.length > 0 ? (
            <div className="insights-list">
              {insights.map((insight) => (
                <div key={insight.id} className={`insight-card ${insight.severity}`}>
                  <div className="insight-header">
                    <span className={`insight-type ${insight.insight_type}`}>
                      {insight.insight_type}
                    </span>
                    <span className={`insight-severity ${insight.severity}`}>
                      {insight.severity}
                    </span>
                  </div>
                  <h4>{insight.title}</h4>
                  <p>{insight.description}</p>
                  {insight.data_json?.action && (
                    <p className="insight-action">
                      <strong>Action:</strong> {insight.data_json.action}
                    </p>
                  )}
                  <div className="insight-footer">
                    <span className="insight-date">
                      {new Date(insight.created_at).toLocaleDateString()}
                    </span>
                    <button
                      className="btn-acknowledge"
                      onClick={() => handleAcknowledgeInsight(insight.id)}
                    >
                      Acknowledge
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-data">No active insights. Great job keeping up with your metrics!</p>
          )}
          <button
            className="btn-primary"
            onClick={() => profitabilityAPI.generateInsights(selectedMonth || getCurrentMonth())
              .then(() => fetchDashboardData(selectedMonth || getCurrentMonth()))}
          >
            Generate New Insights
          </button>
        </div>
      )}

      {/* AI Assistant Tab */}
      {activeTab === 'ai' && (
        <div className="ai-assistant-section">
          <div className="ai-grid">
            {/* Query Section */}
            <div className="ai-query-section">
              <h3>Ask About Your Profitability</h3>
              <div className="query-input-group">
                <input
                  type="text"
                  value={aiQuery}
                  onChange={(e) => setAiQuery(e.target.value)}
                  placeholder="e.g., Who are my top 3 loan officers by ROI?"
                  onKeyPress={(e) => e.key === 'Enter' && handleAIQuery()}
                  disabled={aiLoading}
                />
                <button
                  className="btn-primary"
                  onClick={() => handleAIQuery()}
                  disabled={aiLoading || !aiQuery.trim()}
                >
                  {aiLoading ? 'Analyzing...' : 'Ask AI'}
                </button>
              </div>

              {/* Suggested Questions */}
              {suggestedQuestions.length > 0 && !aiResponse && (
                <div className="suggested-questions">
                  <h4>Try asking:</h4>
                  {suggestedQuestions.map((category, idx) => (
                    <div key={idx} className="question-category">
                      <span className="category-label">{category.category}</span>
                      <div className="question-chips">
                        {category.questions.map((q, qIdx) => (
                          <button
                            key={qIdx}
                            className="question-chip"
                            onClick={() => handleAIQuery(q)}
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* AI Response */}
              {aiResponse && (
                <div className={`ai-response ${aiResponse.error ? 'error' : ''}`}>
                  <div className="response-question">
                    <strong>Q:</strong> {aiResponse.question}
                  </div>
                  <div className="response-answer">
                    <strong>A:</strong>
                    <div className="answer-content">
                      {aiResponse.answer.split('\n').map((line, i) => (
                        <p key={i}>{line}</p>
                      ))}
                    </div>
                  </div>
                  <button
                    className="btn-secondary"
                    onClick={() => setAiResponse(null)}
                  >
                    Ask Another Question
                  </button>
                </div>
              )}
            </div>

            {/* Recommendations Section */}
            <div className="ai-recommendations-section">
              <div className="section-header">
                <h3>AI Recommendations</h3>
                <button
                  className="btn-secondary"
                  onClick={loadRecommendations}
                  disabled={aiLoading}
                >
                  {aiLoading ? 'Loading...' : 'Generate'}
                </button>
              </div>

              {recommendations.length > 0 ? (
                <div className="recommendations-list">
                  {recommendations.map((rec, idx) => (
                    <div key={idx} className={`recommendation-card priority-${rec.priority}`}>
                      <div className="rec-header">
                        <h4>{rec.title}</h4>
                        <span className={`priority-badge ${rec.priority}`}>
                          {rec.priority}
                        </span>
                      </div>
                      <p className="rec-action">{rec.action}</p>
                      <p className="rec-impact"><strong>Impact:</strong> {rec.impact}</p>
                      <p className="rec-rationale">{rec.rationale}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="no-data">Click "Generate" to get AI-powered recommendations based on your data.</p>
              )}
            </div>
          </div>

          {/* Hiring Analysis Section */}
          <div className="hiring-analysis-section">
            <h3>Hiring Decision Analysis</h3>
            <div className="hiring-inputs">
              <input
                type="text"
                value={hiringRole}
                onChange={(e) => setHiringRole(e.target.value)}
                placeholder="Role (e.g., Loan Officer)"
              />
              <input
                type="number"
                value={hiringSalary}
                onChange={(e) => setHiringSalary(e.target.value)}
                placeholder="Annual Salary"
              />
              <button
                className="btn-primary"
                onClick={handleHiringAnalysis}
                disabled={aiLoading || !hiringRole || !hiringSalary}
              >
                {aiLoading ? 'Analyzing...' : 'Analyze Hire'}
              </button>
            </div>

            {hiringAnalysis && (
              <div className="hiring-result">
                <h4>Analysis for {hiringAnalysis.role} at {formatCurrency(hiringAnalysis.proposed_salary)}/year</h4>
                <div className="analysis-content">
                  {hiringAnalysis.analysis.split('\n').map((line, i) => (
                    <p key={i}>{line}</p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfitabilityDashboard;
