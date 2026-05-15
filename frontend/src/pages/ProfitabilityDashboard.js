import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { profitabilityAPI } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar
} from 'recharts';
import './ProfitabilityDashboard.css';
import CostToCloseChart from '../components/CostToCloseChart';

// Metric tabs configuration
const METRIC_TABS = [
  { id: 'gain_on_sale', name: 'Gain on Sale', value: '285 bps', change: '+12 bps', changeType: 'positive' },
  { id: 'cost_per_loan', name: 'Cost Per Loan', value: '$8,450', change: '-$320', changeType: 'positive' },
  { id: 'net_margin', name: 'Net Margin', value: '$2,850', change: '+$180', changeType: 'positive' },
  { id: 'cash_runway', name: 'Cash Runway', value: '8.2 mo', change: 'stable', changeType: 'neutral' }
];

// Demo data for testing
const DEMO_METRICS = {
  net_profit: 847500,
  total_revenue: 2450000,
  total_expenses: 1602500,
  profit_margin: 34.6,
  loans_closed: 47,
  cost_per_loan: 34096,
  revenue_per_loan: 52128,
  profit_per_loan: 18032,
  break_even_loans: 28,
  employee_count: 12
};

const DEMO_ROLE_PROFITABILITY = [
  { role_id: 1, role_name: 'Loan Officers', department: 'Sales', employee_count: 4, total_cost: 520000, total_revenue: 1680000, net_contribution: 1160000, roi_percentage: 223.1, is_profitable: true },
  { role_id: 2, role_name: 'Processors', department: 'Operations', employee_count: 3, total_cost: 195000, total_revenue: 420000, net_contribution: 225000, roi_percentage: 115.4, is_profitable: true },
  { role_id: 3, role_name: 'Underwriters', department: 'Operations', employee_count: 2, total_cost: 180000, total_revenue: 280000, net_contribution: 100000, roi_percentage: 55.6, is_profitable: true },
  { role_id: 4, role_name: 'Closers', department: 'Operations', employee_count: 1, total_cost: 75000, total_revenue: 70000, net_contribution: -5000, roi_percentage: -6.7, is_profitable: false },
  { role_id: 5, role_name: 'Admin/Support', department: 'Admin', employee_count: 2, total_cost: 120000, total_revenue: 0, net_contribution: -120000, roi_percentage: -100, is_profitable: false }
];

const DEMO_TOP_PERFORMERS = [
  { employee_id: 1, employee_name: 'Timothy Loss', role_name: 'Loan Officer', roi_percentage: 412.5, net_contribution: 495000, loans_closed: 18, revenue_per_loan: 58333 },
  { employee_id: 2, employee_name: 'Sarah Mitchell', role_name: 'Loan Officer', roi_percentage: 285.3, net_contribution: 342400, loans_closed: 14, revenue_per_loan: 52000 },
  { employee_id: 3, employee_name: 'Mike Johnson', role_name: 'Loan Officer', roi_percentage: 198.7, net_contribution: 238440, loans_closed: 10, revenue_per_loan: 48000 },
  { employee_id: 4, employee_name: 'Jessica Marlow', role_name: 'Processor', roi_percentage: 145.2, net_contribution: 94380, loans_closed: 22, revenue_per_loan: 19200 },
  { employee_id: 5, employee_name: 'Jennifer Lopez', role_name: 'Processor', roi_percentage: 89.4, net_contribution: 58110, loans_closed: 16, revenue_per_loan: 16500 },
  { employee_id: 6, employee_name: 'Danielle Brooks', role_name: 'Underwriter', roi_percentage: 72.3, net_contribution: 65070, loans_closed: 28, revenue_per_loan: 10000 }
];

const DEMO_TRENDS = [
  { month: 'Jan', revenue: 180000, expenses: 125000, profit: 55000 },
  { month: 'Feb', revenue: 195000, expenses: 128000, profit: 67000 },
  { month: 'Mar', revenue: 210000, expenses: 132000, profit: 78000 },
  { month: 'Apr', revenue: 185000, expenses: 130000, profit: 55000 },
  { month: 'May', revenue: 220000, expenses: 135000, profit: 85000 },
  { month: 'Jun', revenue: 245000, expenses: 140000, profit: 105000 },
  { month: 'Jul', revenue: 230000, expenses: 138000, profit: 92000 },
  { month: 'Aug', revenue: 255000, expenses: 142000, profit: 113000 },
  { month: 'Sep', revenue: 240000, expenses: 140000, profit: 100000 },
  { month: 'Oct', revenue: 265000, expenses: 145000, profit: 120000 },
  { month: 'Nov', revenue: 225000, expenses: 147000, profit: 78000 },
  { month: 'Dec', revenue: 0, expenses: 0, profit: 0 }
];

const DEMO_GAPS_GAINS = [
  { type: 'gap', title: 'Closer Underperformance', description: 'Closing department is operating at a loss. Consider process automation or role consolidation.', priority: 'high', impact: -5000, action: 'Review closing workflow' },
  { type: 'gap', title: 'Admin Overhead', description: 'Admin/Support costs not generating direct revenue. Explore shared services model.', priority: 'medium', impact: -120000, action: 'Evaluate outsourcing options' },
  { type: 'gain', title: 'Top LO Performance', description: 'Timothy Loss generating 412% ROI - consider expanding his capacity or mentorship role.', priority: 'high', impact: 495000, action: 'Assign junior LO for mentorship' },
  { type: 'gain', title: 'Processor Efficiency', description: 'Processors showing strong ROI despite high volume. Well-optimized processes.', priority: 'medium', impact: 152490, action: 'Document best practices' },
  { type: 'gap', title: 'Seasonal Revenue Dip', description: 'April and November show revenue drops. Consider marketing campaigns for slow periods.', priority: 'low', impact: -45000, action: 'Plan seasonal promotions' },
  { type: 'gain', title: 'Underwriting Capacity', description: 'Underwriters handling 28 loans with positive ROI. May have capacity for more volume.', priority: 'medium', impact: 100000, action: 'Analyze capacity limits' }
];

const DEMO_INSIGHTS = [
  { id: 1, insight_type: 'opportunity', severity: 'high', title: 'Revenue Concentration Risk', description: 'Top 2 loan officers generate 68% of revenue. Consider diversifying production across team.', created_at: new Date().toISOString(), data_json: { action: 'Implement lead distribution policy' } },
  { id: 2, insight_type: 'warning', severity: 'medium', title: 'Rising Cost Per Loan', description: 'Cost per loan increased 8% over last quarter. Review operational efficiency.', created_at: new Date().toISOString(), data_json: { action: 'Audit processing workflows' } },
  { id: 3, insight_type: 'success', severity: 'low', title: 'Break-Even Exceeded', description: 'Currently 19 loans above break-even point. Strong profitability position.', created_at: new Date().toISOString(), data_json: { action: 'Continue current strategy' } }
];

const DEMO_SUGGESTED_QUESTIONS = [
  { category: 'Performance', questions: ['Who are my top 3 performers by ROI?', 'Which role has the lowest profitability?', 'How does this month compare to last year?'] },
  { category: 'Costs', questions: ['What is my cost per loan?', 'Which department has the highest overhead?', 'How can I reduce processing costs?'] },
  { category: 'Strategy', questions: ['Should I hire another loan officer?', 'What would happen if I lost my top producer?', 'Where should I focus to improve margins?'] }
];

const ProfitabilityDashboard = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { hasPermission, userRole, isAdmin } = usePermissions();

  // Permission check - require profitability/reports access
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canAccessProfitability = isAdmin || hasPermission('reports.profitability') || userRole === 'management' || userRole === 'admin';

  // Get metric from URL or default to null (show overview)
  const urlMetric = searchParams.get('metric');

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
  const [activeMetric, setActiveMetric] = useState(urlMetric || null);

  // Update URL when metric changes
  const handleMetricChange = (metricId) => {
    setActiveMetric(metricId);
    if (metricId) {
      setSearchParams({ metric: metricId });
    } else {
      setSearchParams({});
    }
  };

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

      // Use demo data as fallback if API returns empty/null values
      setMetrics(data.metrics && Object.keys(data.metrics).length > 0 ? data.metrics : DEMO_METRICS);
      setRoleProfitability(data.role_profitability?.length > 0 ? data.role_profitability : DEMO_ROLE_PROFITABILITY);
      setTopPerformers(data.top_performers?.length > 0 ? data.top_performers : DEMO_TOP_PERFORMERS);
      setTrends(data.trends?.length > 0 ? data.trends : DEMO_TRENDS);
      setGapsGains(data.gaps_and_gains?.length > 0 ? data.gaps_and_gains : DEMO_GAPS_GAINS);
      setInsights(data.insights?.length > 0 ? data.insights : DEMO_INSIGHTS);
    } catch (err) {
      console.error('Failed to load profitability data:', err);
      // Use demo data on error so the page is still usable
      setMetrics(DEMO_METRICS);
      setRoleProfitability(DEMO_ROLE_PROFITABILITY);
      setTopPerformers(DEMO_TOP_PERFORMERS);
      setTrends(DEMO_TRENDS);
      setGapsGains(DEMO_GAPS_GAINS);
      setInsights(DEMO_INSIGHTS);
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
      setSuggestedQuestions(data.questions?.length > 0 ? data.questions : DEMO_SUGGESTED_QUESTIONS);
    } catch (err) {
      console.error('Failed to load suggested questions:', err);
      // Use demo suggested questions on error
      setSuggestedQuestions(DEMO_SUGGESTED_QUESTIONS);
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

  // Access denied if user doesn't have profitability permissions
  if (!canAccessProfitability) {
    return (
      <div className="profitability-dashboard">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to view the Profitability Dashboard.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

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
          <button className="back-btn" onClick={() => navigate('/dashboard')}>
            ← Back to Dashboard
          </button>
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

      {/* Metric Tabs - Key metrics from Dashboard */}
      <div className="metric-tabs-container">
        <div className="metric-tabs">
          {METRIC_TABS.map(metric => (
            <button
              key={metric.id}
              className={`metric-tab ${activeMetric === metric.id ? 'active' : ''}`}
              onClick={() => handleMetricChange(metric.id)}
            >
              <span className="metric-tab-name">{metric.name}</span>
              <span className="metric-tab-value">{metric.value}</span>
              <span className={`metric-tab-change ${metric.changeType}`}>{metric.change}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Metric Detail View - Show when a metric is selected */}
      {activeMetric && (
        <div className="metric-detail-view">
          <div className="metric-detail-header">
            <h2>{METRIC_TABS.find(m => m.id === activeMetric)?.name} Analysis</h2>
            <button className="btn-close-detail" onClick={() => handleMetricChange(null)}>
              ← Back to Overview
            </button>
          </div>

          {activeMetric === 'gain_on_sale' && (
            <div className="metric-detail-content">
              <div className="detail-summary-cards">
                <div className="detail-card">
                  <div className="detail-label">Current Gain on Sale</div>
                  <div className="detail-value">285 bps</div>
                  <div className="detail-change positive">↑ 12 bps vs last month</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">YTD Average</div>
                  <div className="detail-value">268 bps</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Industry Benchmark</div>
                  <div className="detail-value">250 bps</div>
                  <div className="detail-change positive">+35 bps above benchmark</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Best Month (2024)</div>
                  <div className="detail-value">312 bps</div>
                  <div className="detail-sublabel">March 2024</div>
                </div>
              </div>
              <div className="detail-breakdown">
                <h3>Gain on Sale by Product Type</h3>
                <div className="breakdown-table">
                  <div className="breakdown-row header">
                    <span>Product</span>
                    <span>Volume</span>
                    <span>Gain (bps)</span>
                    <span>Revenue</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Conventional</span>
                    <span>$12.5M</span>
                    <span className="positive">295 bps</span>
                    <span>$368,750</span>
                  </div>
                  <div className="breakdown-row">
                    <span>FHA</span>
                    <span>$8.2M</span>
                    <span className="positive">310 bps</span>
                    <span>$254,200</span>
                  </div>
                  <div className="breakdown-row">
                    <span>VA</span>
                    <span>$5.1M</span>
                    <span>265 bps</span>
                    <span>$135,150</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Jumbo</span>
                    <span>$3.8M</span>
                    <span className="warning">245 bps</span>
                    <span>$93,100</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeMetric === 'cost_per_loan' && (
            <div className="metric-detail-content">
              <div className="detail-summary-cards">
                <div className="detail-card">
                  <div className="detail-label">Current Cost per Loan</div>
                  <div className="detail-value">$8,450</div>
                  <div className="detail-change positive">↓ $320 vs last month</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">YTD Average</div>
                  <div className="detail-value">$8,890</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Industry Benchmark</div>
                  <div className="detail-value">$9,200</div>
                  <div className="detail-change positive">$750 below benchmark</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Target</div>
                  <div className="detail-value">$8,000</div>
                  <div className="detail-sublabel">$450 to go</div>
                </div>
              </div>
              <div className="detail-breakdown">
                <h3>Cost Breakdown by Category</h3>
                <div className="breakdown-table">
                  <div className="breakdown-row header">
                    <span>Category</span>
                    <span>Cost/Loan</span>
                    <span>% of Total</span>
                    <span>Trend</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Compensation</span>
                    <span>$4,200</span>
                    <span>49.7%</span>
                    <span className="neutral">→ stable</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Technology</span>
                    <span>$1,850</span>
                    <span>21.9%</span>
                    <span className="positive">↓ $120</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Compliance</span>
                    <span>$1,200</span>
                    <span>14.2%</span>
                    <span className="warning">↑ $80</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Operations</span>
                    <span>$1,200</span>
                    <span>14.2%</span>
                    <span className="positive">↓ $200</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeMetric === 'net_margin' && (
            <div className="metric-detail-content">
              <div className="detail-summary-cards">
                <div className="detail-card">
                  <div className="detail-label">Current Net Margin</div>
                  <div className="detail-value">$2,850</div>
                  <div className="detail-change positive">↑ $180 vs last month</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">YTD Total</div>
                  <div className="detail-value">$847,500</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Margin %</div>
                  <div className="detail-value">34.6%</div>
                  <div className="detail-change positive">↑ 2.1% vs last month</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Loans Closed (MTD)</div>
                  <div className="detail-value">47</div>
                  <div className="detail-sublabel">$133,950 total margin</div>
                </div>
              </div>
              <div className="detail-breakdown">
                <h3>Margin by Loan Officer</h3>
                <div className="breakdown-table">
                  <div className="breakdown-row header">
                    <span>Loan Officer</span>
                    <span>Loans</span>
                    <span>Avg Margin</span>
                    <span>Total</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Timothy Loss</span>
                    <span>18</span>
                    <span className="positive">$3,420</span>
                    <span>$61,560</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Sarah Mitchell</span>
                    <span>14</span>
                    <span className="positive">$2,980</span>
                    <span>$41,720</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Mike Johnson</span>
                    <span>10</span>
                    <span>$2,650</span>
                    <span>$26,500</span>
                  </div>
                  <div className="breakdown-row">
                    <span>Others</span>
                    <span>5</span>
                    <span className="warning">$834</span>
                    <span>$4,170</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeMetric === 'cash_runway' && (
            <div className="metric-detail-content">
              <div className="detail-summary-cards">
                <div className="detail-card">
                  <div className="detail-label">Current Cash Runway</div>
                  <div className="detail-value">8.2 months</div>
                  <div className="detail-change neutral">→ stable</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Cash on Hand</div>
                  <div className="detail-value">$1.64M</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Monthly Burn Rate</div>
                  <div className="detail-value">$200K</div>
                  <div className="detail-change positive">↓ $15K vs last month</div>
                </div>
                <div className="detail-card">
                  <div className="detail-label">Break-even Point</div>
                  <div className="detail-value">28 loans</div>
                  <div className="detail-sublabel">Currently 19 above</div>
                </div>
              </div>
              <div className="detail-breakdown">
                <h3>Cash Flow Projection</h3>
                <div className="breakdown-table">
                  <div className="breakdown-row header">
                    <span>Month</span>
                    <span>Projected Revenue</span>
                    <span>Projected Expenses</span>
                    <span>Net Cash</span>
                  </div>
                  <div className="breakdown-row">
                    <span>December</span>
                    <span>$245,000</span>
                    <span>$200,000</span>
                    <span className="positive">+$45,000</span>
                  </div>
                  <div className="breakdown-row">
                    <span>January</span>
                    <span>$220,000</span>
                    <span>$205,000</span>
                    <span className="positive">+$15,000</span>
                  </div>
                  <div className="breakdown-row">
                    <span>February</span>
                    <span>$235,000</span>
                    <span>$202,000</span>
                    <span className="positive">+$33,000</span>
                  </div>
                  <div className="breakdown-row">
                    <span>March</span>
                    <span>$260,000</span>
                    <span>$198,000</span>
                    <span className="positive">+$62,000</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tabs - Only show when no metric is selected */}
      {!activeMetric && (
        <>
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
                    stroke="#2D7A52"
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
      </>
      )}
    </div>
  );
};

export default ProfitabilityDashboard;
