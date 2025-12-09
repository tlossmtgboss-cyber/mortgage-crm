import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI, mumAPI } from '../services/api';
import CalendarSidebar from '../components/CalendarSidebar';
import './Portfolio.css';

function Portfolio() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('mum-dashboard');
  const [portfolioData, setPortfolioData] = useState({
    totalLoans: 0,
    totalVolume: 0,
    commissionGenerated: 0,
    portfolioValue: 0,
    annualReturn: 0,
    loans: []
  });
  const [mumClients, setMumClients] = useState([]);
  const [mumMetrics, setMumMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterView, setFilterView] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [stats, loans, mum, metrics] = await Promise.all([
        portfolioAPI.getStats(),
        portfolioAPI.getAll(),
        mumAPI.getAll(),
        mumAPI.getMetrics()
      ]);

      const totalVolume = stats.total_volume || 0;
      const totalLoans = stats.total_loans || 0;

      // Calculate commission (1% of total volume)
      const commission = totalVolume * 0.01;

      // Calculate portfolio value (remaining balance, estimated at 90% of total volume)
      const portfolioValue = totalVolume * 0.9;

      // Calculate annual return % (commission / portfolio value * 100)
      const annualReturn = portfolioValue > 0 ? (commission / portfolioValue * 100) : 0;

      setPortfolioData({
        totalLoans: totalLoans,
        totalVolume: totalVolume,
        commissionGenerated: commission,
        portfolioValue: portfolioValue,
        annualReturn: annualReturn,
        loans: Array.isArray(loans) ? loans.map(loan => ({
          id: loan.id,
          borrower: loan.client_name || loan.borrower_name || 'Unknown',
          loanAmount: loan.loan_amount || 0,
          loanType: loan.loan_type || 'N/A',
          status: loan.status || 'Unknown',
          closeDate: loan.close_date || loan.created_at,
          rate: loan.interest_rate || 0
        })) : []
      });

      setMumClients(Array.isArray(mum) ? mum : []);
      setMumMetrics(metrics || null);
    } catch (error) {
      console.error('Failed to load portfolio data:', error);
      // Set empty data on error
      setPortfolioData({
        totalLoans: 0,
        totalVolume: 0,
        commissionGenerated: 0,
        portfolioValue: 0,
        annualReturn: 0,
        loans: []
      });
      setMumClients([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddClient = async (clientData) => {
    try {
      console.log('Creating MUM client with data:', clientData);
      await mumAPI.create(clientData);
      loadData();
      setShowAddModal(false);
    } catch (error) {
      console.error('Failed to create client:', error);
      console.error('Error response:', error.response?.data);
      const errorMsg = error.response?.data?.detail
        ? (typeof error.response.data.detail === 'string'
           ? error.response.data.detail
           : JSON.stringify(error.response.data.detail))
        : error.message || 'Unknown error';
      alert('Failed to create MUM client: ' + errorMsg);
    }
  };

  const handleDeleteClient = async (id) => {
    try {
      await mumAPI.delete(id);
      loadData();
    } catch (error) {
      console.error('Failed to delete client:', error);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  // Filter by view (all vs opportunities)
  let filteredMumClients = filterView === 'all'
    ? mumClients
    : filterView === 'opportunities'
    ? mumClients.filter(c => c.refinance_opportunity)
    : mumClients;

  // Filter by search query
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredMumClients = filteredMumClients.filter(client =>
      (client.client_name || client.name)?.toLowerCase().includes(query) ||
      client.email?.toLowerCase().includes(query) ||
      client.phone?.toLowerCase().includes(query) ||
      (client.current_loan_amount || client.loan_balance)?.toString().includes(query) ||
      (client.servicing_loan_number || client.loan_number)?.toLowerCase().includes(query)
    );
  }

  const getDaysSinceFundingColor = (days) => {
    if (days < 180) return 'recent';
    if (days < 365) return 'medium';
    return 'old';
  };

  if (loading) {
    return (
      <div className="portfolio-container">
        <div className="loading">Loading portfolio...</div>
      </div>
    );
  }

  return (
    <div className="portfolio-page-wrapper">
      <div className="portfolio-container">
        <div className="portfolio-header">
          <h1 className="portfolio-title">Portfolio</h1>
        <div className="header-actions">
          <button className="btn-totals" onClick={() => navigate('/portfolio/year-over-year')}>
            Totals
          </button>
          {activeTab === 'mum' && (
            <button className="btn-add" onClick={() => setShowAddModal(true)}>
              + Add MUM Client
            </button>
          )}
        </div>
      </div>

      <div className="portfolio-tabs">
        <button
          className={activeTab === 'mum-dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('mum-dashboard')}
        >
          MUM Dashboard
        </button>
        <button
          className={activeTab === 'mum' ? 'active' : ''}
          onClick={() => setActiveTab('mum')}
        >
          MUM Clients ({mumClients.length})
        </button>
      </div>

      {activeTab === 'mum-dashboard' && (
        <div className="mum-dashboard">
          {/* Header */}
          <div className="dashboard-section-header">
            <h2>MORTGAGES UNDER MANAGEMENT</h2>
            <p>Portfolio Performance</p>
          </div>

          {/* Top Row Stats */}
          <div className="mum-stats-grid mum-stats-row">
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=total_upb')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{formatCurrency(mumMetrics?.total_upb || 0)}</div>
              <div className="mum-stat-label">TOTAL UPB UNDER MGT</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=net_growth')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{formatCurrency(mumMetrics?.net_growth_mom || 0)}</div>
              <div className="mum-stat-sublabel">(MoM)</div>
              <div className="mum-stat-label">NET MUM GROWTH</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=portfolio_yield')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{((mumMetrics?.portfolio_yield || 0) * 100).toFixed(2)}%</div>
              <div className="mum-stat-sublabel">Annual Yield</div>
              <div className="mum-stat-label">PORTFOLIO REVENUE YIELD</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=client_ltv')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{formatCurrency(mumMetrics?.avg_annual_revenue_per_client * 5 || 0)}</div>
              <div className="mum-stat-sublabel">Avg. per Client (5yr)</div>
              <div className="mum-stat-label">CLIENT LIFETIME VALUE</div>
            </div>
          </div>

          {/* Second Row Stats */}
          <div className="mum-stats-grid mum-stats-row">
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=client_count')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{mumMetrics?.client_count || 0}</div>
              <div className="mum-stat-sublabel">Active Clients</div>
              <div className="mum-stat-label">CLIENT COUNT</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=loans_added_lost')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">+{mumMetrics?.loans_added_30d || 0} / -{mumMetrics?.loans_lost_30d || 0}</div>
              <div className="mum-stat-sublabel">Added / Lost (30d)</div>
              <div className="mum-stat-label">LOANS ADDED VS LOST</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=capture_rate')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">+41%</div>
              <div className="mum-stat-sublabel">Above Industry Avg</div>
              <div className="mum-stat-label">CAPTURE RATE ALPHA</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=attrition_risk')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">12.4%</div>
              <div className="mum-stat-sublabel">At-Risk Clients</div>
              <div className="mum-stat-label">ATTRITION RISK INDEX</div>
            </div>
          </div>

          {/* Portfolio Opportunities */}
          <div className="dashboard-section-header">
            <h2>PORTFOLIO OPPORTUNITIES</h2>
          </div>

          <div className="mum-stats-grid mum-opportunities-row">
            <div
              className="mum-stat-card opportunity-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=rate_rebound')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{mumMetrics?.rate_rebound_opportunities || 0}</div>
              <div className="mum-stat-sublabel">Clients Eligible</div>
              <div className="mum-stat-label">RATE REBOUND OPPS</div>
              <div className="opportunity-highlight">High rates ready to refi</div>
            </div>
            <div
              className="mum-stat-card opportunity-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=heloc')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{mumMetrics?.heloc_opportunities || 0}</div>
              <div className="mum-stat-sublabel">Clients with High Equity</div>
              <div className="mum-stat-label">HELOC OPPORTUNITIES</div>
              <div className="opportunity-highlight">Ready for equity access</div>
            </div>
            <div
              className="mum-stat-card opportunity-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=refinance')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{mumMetrics?.refinance_opportunities || 0}</div>
              <div className="mum-stat-sublabel">High-Priority Files</div>
              <div className="mum-stat-label">REFINANCE OPPORTUNITIES</div>
              <div className="opportunity-highlight">Rate drop opportunities</div>
            </div>
          </div>

          {/* Annual Revenue Performance */}
          <div className="dashboard-section-header">
            <h2>ANNUAL REVENUE PERFORMANCE</h2>
          </div>

          <div className="mum-stats-grid mum-revenue-row">
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=annual_revenue')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{formatCurrency(mumMetrics?.avg_annual_revenue_per_client || 0)}</div>
              <div className="mum-stat-sublabel">per Client</div>
              <div className="mum-stat-label">ANNUAL REVENUE / CL</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=referral_rate')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">0.64</div>
              <div className="mum-stat-sublabel">Referrals/yr</div>
              <div className="mum-stat-label">REFERRAL RATE / CLIENT</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=repeat_purchase')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">21%</div>
              <div className="mum-stat-sublabel">5-Yr Rolling</div>
              <div className="mum-stat-label">REPEAT PURCHASE RATE</div>
            </div>
          </div>

          {/* Portfolio Health */}
          <div className="dashboard-section-header">
            <h2>PORTFOLIO HEALTH</h2>
          </div>

          <div className="mum-stats-grid mum-health-row">
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=portfolio_stability')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">89/100</div>
              <div className="mum-stat-label">PORTFOLIO STABILITY</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=volume_variance')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">±14%</div>
              <div className="mum-stat-sublabel">Month-to-Month</div>
              <div className="mum-stat-label">VARIANCE IN VOLUME</div>
            </div>
            <div
              className="mum-stat-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=max_drawdown')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">-28%</div>
              <div className="mum-stat-sublabel">Last 12 Months</div>
              <div className="mum-stat-label">PIPELINE MAX DRAWDOWN</div>
            </div>
          </div>

          {/* Client Segments */}
          <div className="dashboard-section-header">
            <h2>CLIENT SEGMENTS</h2>
          </div>

          <div className="mum-stats-grid mum-segments-row">
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=primary_residence')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">62%</div>
              <div className="mum-stat-label">PRIMARY RESIDENCE</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=investors')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">18%</div>
              <div className="mum-stat-label">INVESTORS</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=builders')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">12%</div>
              <div className="mum-stat-label">BUILDERS / RTO</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=refinance_other')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">8%</div>
              <div className="mum-stat-label">REFINANCE / OTHER</div>
            </div>
          </div>

          {/* AI-Driven Suggestions */}
          <div className="dashboard-section-header">
            <h2>AI-DRIVEN SUGGESTIONS</h2>
          </div>

          <div className="ai-suggestions-container">
            <div className="ai-suggestion-item">
              <span className="ai-bullet">•</span>
              <span className="ai-suggestion-text">
                <strong>18 clients</strong> qualify for refinance now based on Rate Rebound
              </span>
            </div>
            <div className="ai-suggestion-item">
              <span className="ai-bullet">•</span>
              <span className="ai-suggestion-text">
                <strong>37 clients</strong> should be contacted for HELOC/cash-out education
              </span>
            </div>
            <div className="ai-suggestion-item">
              <span className="ai-bullet">•</span>
              <span className="ai-suggestion-text">
                <strong>12 high-risk attrition clients</strong> need immediate outreach
              </span>
            </div>
            <div className="ai-suggestion-item">
              <span className="ai-bullet">•</span>
              <span className="ai-suggestion-text">
                <strong>4 clients</strong> have homes listed—trigger Purchase-Next call
              </span>
            </div>
            <div className="ai-suggestion-item">
              <span className="ai-bullet">•</span>
              <span className="ai-suggestion-text">
                <strong>89 clients</strong> are 6–12 months from next mortgage event
              </span>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'mum' && (
        <div className="mum-section">
          <div className="mum-header">
            <p className="mum-subtitle">
              {mumClients.length} closed clients • {mumClients.filter(c => c.refinance_opportunity).length} refinance opportunities
            </p>
            <div className="filter-bar">
              <button
                className={filterView === 'all' ? 'active' : ''}
                onClick={() => setFilterView('all')}
              >
                All Clients ({mumClients.length})
              </button>
              <button
                className={filterView === 'opportunities' ? 'active' : ''}
                onClick={() => setFilterView('opportunities')}
              >
                Refinance Opportunities ({mumClients.filter(c => c.refinance_opportunity).length})
              </button>
            </div>
          </div>

          <div className="search-bar-container">
            <input
              type="text"
              className="search-bar"
              placeholder="Search clients by name, email, phone, or loan amount..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="clear-search" onClick={() => setSearchQuery('')}>
                ×
              </button>
            )}
          </div>

          <div className="clients-table">
            <table>
              <thead>
                <tr>
                  <th>Client Name</th>
                  <th>Loan Number</th>
                  <th>Closed Date</th>
                  <th>Days Since Funding</th>
                  <th>Original Rate</th>
                  <th>Current Rate</th>
                  <th>Loan Balance</th>
                  <th>Opportunity</th>
                  <th>Est. Savings</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredMumClients.map((client) => (
                  <tr
                    key={client.id}
                    onClick={() => navigate(`/portfolio/${client.id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      <strong>{client.client_name || client.name}</strong>
                    </td>
                    <td>{client.servicing_loan_number || client.loan_number}</td>
                    <td>
                      {client.closing_date || client.original_close_date ? new Date(client.closing_date || client.original_close_date).toLocaleDateString() : 'N/A'}
                    </td>
                    <td>
                      <span className={`days-badge ${getDaysSinceFundingColor(client.days_since_funding)}`}>
                        {client.days_since_funding} days
                      </span>
                    </td>
                    <td>{(client.interest_rate || client.current_rate) ? `${client.interest_rate || client.current_rate}%` : 'N/A'}</td>
                    <td>{(client.interest_rate || client.current_rate) ? `${client.interest_rate || client.current_rate}%` : 'N/A'}</td>
                    <td>${(client.current_loan_amount || client.loan_balance)?.toLocaleString() || 0}</td>
                    <td>
                      {client.refinance_opportunity ? (
                        <span className="opportunity-yes">Yes</span>
                      ) : (
                        <span className="opportunity-no">No</span>
                      )}
                    </td>
                    <td>
                      {client.estimated_savings ? (
                        <span className="savings">${client.estimated_savings.toLocaleString()}</span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td>
                      <div className="action-buttons">
                        <button className="btn-contact">Contact</button>
                        <button
                          className="btn-delete-small"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteClient(client.id);
                          }}
                        >
                          ×
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredMumClients.length === 0 && (
              <div className="empty-state">
                No clients found. Add your first MUM client to track post-closing opportunities.
              </div>
            )}
          </div>
        </div>
      )}

      {showAddModal && (
        <AddClientModal
          onClose={() => setShowAddModal(false)}
          onAdd={handleAddClient}
        />
      )}
      </div>
      <CalendarSidebar />
    </div>
  );
}

function AddClientModal({ onClose, onAdd }) {
  const [formData, setFormData] = useState({
    name: '',
    loan_number: '',
    original_close_date: '',
    original_rate: '',
    loan_balance: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onAdd({
      ...formData,
      original_rate: parseFloat(formData.original_rate),
      loan_balance: parseFloat(formData.loan_balance),
      original_close_date: new Date(formData.original_close_date).toISOString(),
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Add MUM Client</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Client Name *</label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Loan Number *</label>
            <input
              type="text"
              required
              value={formData.loan_number}
              onChange={(e) => setFormData({ ...formData, loan_number: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Original Close Date *</label>
            <input
              type="date"
              required
              value={formData.original_close_date}
              onChange={(e) => setFormData({ ...formData, original_close_date: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Original Interest Rate (%) *</label>
            <input
              type="number"
              step="0.001"
              required
              value={formData.original_rate}
              onChange={(e) => setFormData({ ...formData, original_rate: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Current Loan Balance ($) *</label>
            <input
              type="number"
              required
              value={formData.loan_balance}
              onChange={(e) => setFormData({ ...formData, loan_balance: e.target.value })}
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Add Client</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Portfolio;
