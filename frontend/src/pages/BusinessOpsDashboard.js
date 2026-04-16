import React, { useState, useEffect } from 'react';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import './BusinessOpsDashboard.css';
import { getToken } from '../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const BusinessOpsDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState(null);
  const [services, setServices] = useState([]);

  // Fetch dashboard data
  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      };

      const [dashboardRes, servicesRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/business-ops/dashboard`, { headers }),
        fetch(`${API_URL}/api/v1/business-ops/services`, { headers })
      ]);

      if (dashboardRes.ok) {
        setDashboardData(await dashboardRes.json());
      }
      if (servicesRes.ok) {
        setServices(await servicesRes.json());
      }
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
      // Use mock data for development
      setDashboardData(getMockDashboardData());
      setServices(getMockServices());
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'revenue', label: 'Revenue' },
    { id: 'services', label: 'Service Costs' },
    { id: 'forecasting', label: 'Forecasting' },
    { id: 'marketing', label: 'Marketing' },
  ];

  if (loading) {
    return (
      <div className="business-ops-dashboard">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading business operations data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="business-ops-dashboard">
      <header className="dashboard-header">
        <h1>Business Operations</h1>
        <p className="subtitle">Revenue, Expenses, and Business Intelligence</p>
      </header>

      <nav className="tab-nav">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="tab-content">
        {activeTab === 'overview' && (
          <OverviewTab data={dashboardData} services={services} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'revenue' && (
          <RevenueTab data={dashboardData} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'services' && (
          <ServiceCostsTab services={services} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'forecasting' && (
          <ForecastingTab data={dashboardData} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'marketing' && (
          <MarketingTab formatCurrency={formatCurrency} />
        )}
      </div>
    </div>
  );
};

// Overview Tab Component
const OverviewTab = ({ data, services, formatCurrency }) => {
  const kpis = data?.kpis || {};
  const revenue = data?.revenue || {};
  const costs = data?.costs || {};
  const alerts = data?.alerts || [];

  const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

  // Prepare pie chart data for costs by category
  const costsByCategory = Object.entries(costs.by_category || {}).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: value
  }));

  return (
    <div className="overview-tab">
      {/* KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Monthly Recurring Revenue</div>
          <div className="kpi-value">{formatCurrency(kpis.mrr || 0)}</div>
          <div className="kpi-subtext">ARR: {formatCurrency((kpis.mrr || 0) * 12)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Active Customers</div>
          <div className="kpi-value">{kpis.total_customers || 0}</div>
          <div className="kpi-subtext">Subscriptions</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Service Costs (MTD)</div>
          <div className="kpi-value">{formatCurrency(kpis.service_costs || 0)}</div>
          <div className="kpi-subtext">All services combined</div>
        </div>
        <div className="kpi-card highlight">
          <div className="kpi-label">Gross Margin</div>
          <div className="kpi-value">{(kpis.gross_margin || 0).toFixed(1)}%</div>
          <div className="kpi-subtext">Revenue - Service Costs</div>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="alerts-section">
          <h3>Budget Alerts</h3>
          <div className="alerts-list">
            {alerts.map((alert, idx) => (
              <div key={idx} className={`alert-item ${alert.threshold_percent >= 100 ? 'critical' : 'warning'}`}>
                <span className="alert-icon">{alert.threshold_percent >= 100 ? '!' : '!'}</span>
                <span>{alert.type}: {((alert.current_spend / alert.budget_amount) * 100).toFixed(0)}% of budget used</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Charts Row */}
      <div className="charts-row">
        <div className="chart-card">
          <h3>Revenue vs Expenses</h3>
          <div className="summary-bars">
            <div className="summary-bar-item">
              <div className="bar-label">
                <span>Revenue</span>
                <span>{formatCurrency(revenue.total_revenue_mtd || 0)}</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill revenue" style={{ width: '100%' }}></div>
              </div>
            </div>
            <div className="summary-bar-item">
              <div className="bar-label">
                <span>Expenses</span>
                <span>{formatCurrency(costs.total_costs_mtd || 0)}</span>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill expense"
                  style={{
                    width: `${Math.min(100, (costs.total_costs_mtd / (revenue.total_revenue_mtd || 1)) * 100)}%`
                  }}
                ></div>
              </div>
            </div>
            <div className="summary-bar-item">
              <div className="bar-label">
                <span>Net Profit</span>
                <span className={data?.pnl?.net_profit >= 0 ? 'positive' : 'negative'}>
                  {formatCurrency(data?.pnl?.net_profit || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="chart-card">
          <h3>Costs by Category</h3>
          {costsByCategory.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={costsByCategory}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {costsByCategory.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => formatCurrency(value)} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data">No cost data available</div>
          )}
        </div>
      </div>

      {/* Top Services */}
      <div className="section">
        <h3>Service Costs This Month</h3>
        <div className="services-mini-table">
          <table>
            <thead>
              <tr>
                <th>Service</th>
                <th>Category</th>
                <th>Current Month</th>
                <th>Budget</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {services.slice(0, 5).map((service, idx) => (
                <tr key={idx}>
                  <td>{service.name}</td>
                  <td><span className={`category-badge ${service.category}`}>{service.category}</span></td>
                  <td>{formatCurrency(service.current_month_cost || 0)}</td>
                  <td>{service.monthly_budget ? formatCurrency(service.monthly_budget) : '-'}</td>
                  <td>
                    {service.budget_used_percent !== null ? (
                      <span className={`status-badge ${service.budget_used_percent > 80 ? 'warning' : 'ok'}`}>
                        {service.budget_used_percent.toFixed(0)}%
                      </span>
                    ) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// Revenue Tab Component
const RevenueTab = ({ data, formatCurrency }) => {
  const revenue = data?.revenue || {};

  // Mock trend data
  const trendData = [
    { month: 'Jul', subscription: 4500, usage: 500 },
    { month: 'Aug', subscription: 5000, usage: 600 },
    { month: 'Sep', subscription: 5500, usage: 700 },
    { month: 'Oct', subscription: 6000, usage: 800 },
    { month: 'Nov', subscription: 6500, usage: 900 },
    { month: 'Dec', subscription: 7000, usage: 1000 },
  ];

  return (
    <div className="revenue-tab">
      <div className="kpi-grid">
        <div className="kpi-card large">
          <div className="kpi-label">MRR</div>
          <div className="kpi-value">{formatCurrency(revenue.mrr || 0)}</div>
        </div>
        <div className="kpi-card large">
          <div className="kpi-label">ARR</div>
          <div className="kpi-value">{formatCurrency(revenue.arr || 0)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Subscription Revenue</div>
          <div className="kpi-value">{formatCurrency(revenue.subscription_revenue_mtd || 0)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Usage Revenue</div>
          <div className="kpi-value">{formatCurrency(revenue.usage_revenue_mtd || 0)}</div>
        </div>
      </div>

      <div className="chart-card full-width">
        <h3>Revenue Trend</h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis tickFormatter={(v) => `$${v / 1000}k`} />
            <Tooltip formatter={(value) => formatCurrency(value)} />
            <Legend />
            <Area
              type="monotone"
              dataKey="subscription"
              stackId="1"
              stroke="#10b981"
              fill="#10b981"
              fillOpacity={0.6}
              name="Subscription"
            />
            <Area
              type="monotone"
              dataKey="usage"
              stackId="1"
              stroke="#3b82f6"
              fill="#3b82f6"
              fillOpacity={0.6}
              name="Usage"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="section">
        <h3>Revenue by Tier</h3>
        <div className="tier-breakdown">
          <div className="tier-item">
            <span className="tier-name">Starter ($99/mo)</span>
            <span className="tier-count">25 customers</span>
            <span className="tier-revenue">{formatCurrency(2475)}</span>
          </div>
          <div className="tier-item">
            <span className="tier-name">Professional ($199/mo)</span>
            <span className="tier-count">15 customers</span>
            <span className="tier-revenue">{formatCurrency(2985)}</span>
          </div>
          <div className="tier-item">
            <span className="tier-name">Enterprise ($399/mo)</span>
            <span className="tier-count">5 customers</span>
            <span className="tier-revenue">{formatCurrency(1995)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// Service Costs Tab Component
const ServiceCostsTab = ({ services, formatCurrency }) => {
  const [selectedCategory, setSelectedCategory] = useState('all');

  const categories = ['all', ...new Set(services.map(s => s.category))];

  const filteredServices = selectedCategory === 'all'
    ? services
    : services.filter(s => s.category === selectedCategory);

  const totalCost = services.reduce((sum, s) => sum + (s.current_month_cost || 0), 0);

  return (
    <div className="services-tab">
      <div className="kpi-grid">
        <div className="kpi-card large">
          <div className="kpi-label">Total Service Costs (MTD)</div>
          <div className="kpi-value">{formatCurrency(totalCost)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Active Services</div>
          <div className="kpi-value">{services.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Auto-Tracked</div>
          <div className="kpi-value">{services.filter(s => s.has_usage_api).length}</div>
        </div>
      </div>

      <div className="filter-bar">
        {categories.map(cat => (
          <button
            key={cat}
            className={`filter-btn ${selectedCategory === cat ? 'active' : ''}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </button>
        ))}
      </div>

      <div className="services-table">
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Category</th>
              <th>Current Month</th>
              <th>Last Month</th>
              <th>Change</th>
              <th>Budget</th>
              <th>% Used</th>
              <th>API</th>
            </tr>
          </thead>
          <tbody>
            {filteredServices.map((service, idx) => {
              const change = service.last_month_cost > 0
                ? ((service.current_month_cost - service.last_month_cost) / service.last_month_cost * 100)
                : 0;

              return (
                <tr key={idx}>
                  <td className="service-name">{service.name}</td>
                  <td><span className={`category-badge ${service.category}`}>{service.category}</span></td>
                  <td>{formatCurrency(service.current_month_cost || 0)}</td>
                  <td>{formatCurrency(service.last_month_cost || 0)}</td>
                  <td className={change >= 0 ? 'positive' : 'negative'}>
                    {change >= 0 ? '+' : ''}{change.toFixed(1)}%
                  </td>
                  <td>{service.monthly_budget ? formatCurrency(service.monthly_budget) : '-'}</td>
                  <td>
                    {service.budget_used_percent !== null ? (
                      <div className="budget-progress">
                        <div
                          className={`progress-bar ${service.budget_used_percent > 80 ? 'warning' : ''} ${service.budget_used_percent > 100 ? 'critical' : ''}`}
                          style={{ width: `${Math.min(100, service.budget_used_percent)}%` }}
                        ></div>
                        <span>{service.budget_used_percent.toFixed(0)}%</span>
                      </div>
                    ) : '-'}
                  </td>
                  <td>
                    <span className={`api-badge ${service.has_usage_api ? 'active' : 'manual'}`}>
                      {service.has_usage_api ? 'Auto' : 'Manual'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Forecasting Tab Component
const ForecastingTab = ({ data, formatCurrency }) => {
  const [months, setMonths] = useState(12);
  const [growthRate, setGrowthRate] = useState(5);
  const [churnRate, setChurnRate] = useState(2);

  // Generate mock forecast data
  const generateForecast = () => {
    const projections = [];
    let mrr = data?.revenue?.mrr || 5000;
    let customers = data?.kpis?.total_customers || 20;

    for (let i = 0; i < months; i++) {
      const newCustomers = 3;
      const churned = Math.floor(customers * (churnRate / 100));
      customers = customers + newCustomers - churned;

      const newMRR = 199 * newCustomers;
      const lostMRR = mrr * (churnRate / 100);
      mrr = mrr + newMRR - lostMRR;

      const expenses = mrr * 0.5;

      projections.push({
        month: new Date(Date.now() + i * 30 * 24 * 60 * 60 * 1000).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
        revenue: mrr,
        expenses: expenses,
        net: mrr - expenses,
        customers: customers
      });
    }
    return projections;
  };

  const forecastData = generateForecast();
  const endingMRR = forecastData[forecastData.length - 1]?.revenue || 0;
  const endingCustomers = forecastData[forecastData.length - 1]?.customers || 0;

  return (
    <div className="forecasting-tab">
      <div className="scenario-controls">
        <h3>Scenario Parameters</h3>
        <div className="controls-grid">
          <div className="control-item">
            <label>Projection Months</label>
            <input
              type="range"
              min="3"
              max="24"
              value={months}
              onChange={(e) => setMonths(parseInt(e.target.value))}
            />
            <span>{months} months</span>
          </div>
          <div className="control-item">
            <label>Monthly Growth Rate</label>
            <input
              type="range"
              min="0"
              max="20"
              value={growthRate}
              onChange={(e) => setGrowthRate(parseInt(e.target.value))}
            />
            <span>{growthRate}%</span>
          </div>
          <div className="control-item">
            <label>Monthly Churn Rate</label>
            <input
              type="range"
              min="0"
              max="10"
              value={churnRate}
              onChange={(e) => setChurnRate(parseInt(e.target.value))}
            />
            <span>{churnRate}%</span>
          </div>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card projection">
          <div className="kpi-label">Projected MRR ({months} mo)</div>
          <div className="kpi-value">{formatCurrency(endingMRR)}</div>
          <div className="kpi-subtext">ARR: {formatCurrency(endingMRR * 12)}</div>
        </div>
        <div className="kpi-card projection">
          <div className="kpi-label">Projected Customers</div>
          <div className="kpi-value">{endingCustomers}</div>
        </div>
      </div>

      <div className="chart-card full-width">
        <h3>Revenue & Expense Projection</h3>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={forecastData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip formatter={(value) => formatCurrency(value)} />
            <Legend />
            <Line type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={2} name="Revenue" />
            <Line type="monotone" dataKey="expenses" stroke="#ef4444" strokeWidth={2} name="Expenses" />
            <Line type="monotone" dataKey="net" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 5" name="Net Profit" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// Marketing Tab Component
const MarketingTab = ({ formatCurrency }) => {
  // Mock marketing data
  const channelData = [
    { channel: 'Google Ads', spend: 2500, leads: 45, conversions: 8, revenue: 6400, roas: 2.56 },
    { channel: 'LinkedIn', spend: 1500, leads: 25, conversions: 4, revenue: 3200, roas: 2.13 },
    { channel: 'Facebook', spend: 800, leads: 30, conversions: 3, revenue: 2400, roas: 3.00 },
    { channel: 'Email', spend: 200, leads: 15, conversions: 5, revenue: 4000, roas: 20.00 },
    { channel: 'Referral', spend: 0, leads: 20, conversions: 10, revenue: 8000, roas: Infinity },
  ];

  const totalSpend = channelData.reduce((s, c) => s + c.spend, 0);
  const totalConversions = channelData.reduce((s, c) => s + c.conversions, 0);
  const overallCAC = totalSpend / totalConversions;

  return (
    <div className="marketing-tab">
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Total Marketing Spend</div>
          <div className="kpi-value">{formatCurrency(totalSpend)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Customer Acquisition Cost</div>
          <div className="kpi-value">{formatCurrency(overallCAC)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Total Conversions</div>
          <div className="kpi-value">{totalConversions}</div>
        </div>
        <div className="kpi-card highlight">
          <div className="kpi-label">LTV:CAC Ratio</div>
          <div className="kpi-value">5.2x</div>
          <div className="kpi-subtext">Target: 3x+</div>
        </div>
      </div>

      <div className="chart-card full-width">
        <h3>Channel Performance</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={channelData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => `$${v}`} />
            <YAxis dataKey="channel" type="category" width={100} />
            <Tooltip formatter={(value) => formatCurrency(value)} />
            <Legend />
            <Bar dataKey="spend" fill="#ef4444" name="Spend" />
            <Bar dataKey="revenue" fill="#10b981" name="Revenue" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="section">
        <h3>Channel Breakdown</h3>
        <div className="channel-table">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Spend</th>
                <th>Leads</th>
                <th>Conversions</th>
                <th>CAC</th>
                <th>Revenue</th>
                <th>ROAS</th>
              </tr>
            </thead>
            <tbody>
              {channelData.map((channel, idx) => (
                <tr key={idx}>
                  <td>{channel.channel}</td>
                  <td>{formatCurrency(channel.spend)}</td>
                  <td>{channel.leads}</td>
                  <td>{channel.conversions}</td>
                  <td>{channel.conversions > 0 ? formatCurrency(channel.spend / channel.conversions) : '-'}</td>
                  <td>{formatCurrency(channel.revenue)}</td>
                  <td className={channel.roas >= 3 ? 'positive' : channel.roas >= 1 ? 'neutral' : 'negative'}>
                    {channel.roas === Infinity ? '∞' : `${channel.roas.toFixed(2)}x`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// Mock data functions
const getMockDashboardData = () => ({
  kpis: {
    mrr: 7500,
    arr: 90000,
    total_customers: 45,
    service_costs: 2500,
    gross_margin: 66.7,
    churn_rate: 2.5,
  },
  revenue: {
    mrr: 7500,
    arr: 90000,
    subscription_revenue_mtd: 7500,
    usage_revenue_mtd: 1200,
    total_revenue_mtd: 8700,
    subscription_count: 45,
    active_customers: 45,
  },
  costs: {
    total_costs_mtd: 2500,
    service_costs_mtd: 2500,
    by_category: {
      ai: 800,
      communications: 600,
      storage: 200,
      hosting: 400,
      payments: 300,
      monitoring: 100,
      email: 100,
    },
  },
  pnl: {
    total_revenue: 8700,
    total_expenses: 2500,
    gross_profit: 6200,
    gross_margin: 71.3,
    net_profit: 6200,
    net_margin: 71.3,
  },
  alerts: [],
});

const getMockServices = () => [
  { name: 'Anthropic Claude', category: 'ai', provider_type: 'anthropic', current_month_cost: 350, last_month_cost: 280, monthly_budget: 500, budget_used_percent: 70, has_usage_api: true },
  { name: 'OpenAI', category: 'ai', provider_type: 'openai', current_month_cost: 280, last_month_cost: 250, monthly_budget: 400, budget_used_percent: 70, has_usage_api: true },
  { name: 'Telnyx', category: 'communications', provider_type: 'telnyx', current_month_cost: 450, last_month_cost: 400, monthly_budget: 600, budget_used_percent: 75, has_usage_api: true },
  { name: 'Vapi.ai', category: 'communications', provider_type: 'vapi', current_month_cost: 150, last_month_cost: 120, monthly_budget: null, budget_used_percent: null, has_usage_api: false },
  { name: 'SendGrid', category: 'email', provider_type: 'sendgrid', current_month_cost: 100, last_month_cost: 95, monthly_budget: 150, budget_used_percent: 67, has_usage_api: true },
  { name: 'AWS S3', category: 'storage', provider_type: 'aws_s3', current_month_cost: 180, last_month_cost: 160, monthly_budget: 250, budget_used_percent: 72, has_usage_api: true },
  { name: 'Railway', category: 'hosting', provider_type: 'railway', current_month_cost: 250, last_month_cost: 200, monthly_budget: 300, budget_used_percent: 83, has_usage_api: false },
  { name: 'Vercel', category: 'hosting', provider_type: 'vercel', current_month_cost: 150, last_month_cost: 150, monthly_budget: 200, budget_used_percent: 75, has_usage_api: false },
  { name: 'Stripe', category: 'payments', provider_type: 'stripe', current_month_cost: 300, last_month_cost: 260, monthly_budget: null, budget_used_percent: null, has_usage_api: true },
  { name: 'Sentry', category: 'monitoring', provider_type: 'sentry', current_month_cost: 99, last_month_cost: 99, monthly_budget: 100, budget_used_percent: 99, has_usage_api: false },
  { name: 'Pinecone', category: 'ai', provider_type: 'pinecone', current_month_cost: 70, last_month_cost: 70, monthly_budget: 100, budget_used_percent: 70, has_usage_api: false },
  { name: 'Deepgram', category: 'communications', provider_type: 'deepgram', current_month_cost: 80, last_month_cost: 60, monthly_budget: 150, budget_used_percent: 53, has_usage_api: true },
];

export default BusinessOpsDashboard;
