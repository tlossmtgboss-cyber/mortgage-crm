import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { mumAPI } from '../services/api';
import './PortfolioDetail.css';

function PortfolioDetail() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const metric = searchParams.get('metric');

  const [clients, setClients] = useState([]);
  const [filteredClients, setFilteredClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadClients();
  }, [metric]);

  const loadClients = async () => {
    try {
      setLoading(true);
      const data = await mumAPI.getAll();
      setClients(data);

      // Filter based on metric
      const filtered = filterClientsByMetric(data, metric);
      setFilteredClients(filtered);
    } catch (error) {
      console.error('Failed to load clients:', error);
    } finally {
      setLoading(false);
    }
  };

  const filterClientsByMetric = (clientList, metricType) => {
    switch (metricType) {
      case 'total_upb':
      case 'client_count':
      case 'net_growth':
      case 'portfolio_yield':
      case 'client_ltv':
      case 'annual_revenue':
        // Show all clients
        return clientList;

      case 'refinance':
        // Show only clients with refinance opportunities
        return clientList.filter(c => c.refinance_opportunity);

      case 'heloc':
        // Show only clients with HELOC opportunities
        return clientList.filter(c => c.heloc_opportunity);

      case 'rate_rebound':
        // Show only clients with rate rebound opportunities
        return clientList.filter(c => c.rate_rebound_opportunity);

      case 'high_equity':
        // Show only clients with high equity opportunities
        return clientList.filter(c => c.high_equity_opportunity);

      case 'loans_added_lost':
        // Show all clients (could add date filtering for last 30 days)
        return clientList;

      case 'capture_rate':
      case 'attrition_risk':
      case 'referral_rate':
      case 'repeat_purchase':
      case 'portfolio_stability':
      case 'volume_variance':
      case 'max_drawdown':
      case 'primary_residence':
      case 'investors':
      case 'builders':
      case 'refinance_other':
        // Show all clients (metrics not yet fully implemented)
        return clientList;

      default:
        return clientList;
    }
  };

  // Filter by search query
  let displayedClients = filteredClients;
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    displayedClients = filteredClients.filter(client =>
      client.client_name?.toLowerCase().includes(query) ||
      client.email?.toLowerCase().includes(query) ||
      client.phone?.toLowerCase().includes(query) ||
      client.servicing_loan_number?.toLowerCase().includes(query) ||
      client.current_loan_amount?.toString().includes(query)
    );
  }

  const getMetricTitle = (metricType) => {
    const titles = {
      total_upb: 'Total UPB Under Management',
      net_growth: 'NET MUM Growth',
      portfolio_yield: 'Portfolio Revenue Yield',
      client_ltv: 'Client Lifetime Value',
      client_count: 'All Clients',
      loans_added_lost: 'Loans Added vs Lost',
      capture_rate: 'Capture Rate Alpha',
      attrition_risk: 'Attrition Risk Index',
      refinance: 'Refinance Opportunities',
      heloc: 'HELOC Opportunities',
      rate_rebound: 'Rate Rebound Opportunities',
      high_equity: 'High Equity Opportunities',
      annual_revenue: 'Annual Revenue per Client',
      referral_rate: 'Referral Rate per Client',
      repeat_purchase: 'Repeat Purchase Rate',
      portfolio_stability: 'Portfolio Stability',
      volume_variance: 'Variance in Volume',
      max_drawdown: 'Pipeline Max Drawdown',
      primary_residence: 'Primary Residence Clients',
      investors: 'Investor Clients',
      builders: 'Builder / RTO Clients',
      refinance_other: 'Refinance / Other Clients'
    };
    return titles[metricType] || 'Portfolio Detail';
  };

  const getMetricDescription = (metricType) => {
    const descriptions = {
      total_upb: 'All loans in your portfolio by current unpaid principal balance',
      net_growth: 'Monthly growth in total portfolio value',
      portfolio_yield: 'Annual revenue yield from servicing portfolio',
      client_ltv: 'Estimated 5-year lifetime value per client',
      client_count: 'All active clients in your portfolio',
      refinance: 'Clients who may benefit from refinancing to a lower rate',
      heloc: 'Clients with sufficient equity for HELOC opportunities',
      rate_rebound: 'Clients with high rates ready to refinance when rates drop',
      high_equity: 'Clients with significant equity available'
    };
    return descriptions[metricType] || 'Detailed view of portfolio metrics';
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const getDaysSinceFundingColor = (days) => {
    if (days < 180) return 'recent';
    if (days < 365) return 'medium';
    return 'old';
  };

  if (loading) {
    return (
      <div className="portfolio-detail-container">
        <div className="loading">Loading clients...</div>
      </div>
    );
  }

  return (
    <div className="portfolio-detail-container">
      {/* Header */}
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/portfolio')}>
          ← Back to Portfolio
        </button>
        <div className="detail-title-section">
          <h1>{getMetricTitle(metric)}</h1>
          <p className="detail-description">{getMetricDescription(metric)}</p>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="detail-stats">
        <div className="detail-stat-card">
          <div className="stat-value">{displayedClients.length}</div>
          <div className="stat-label">Total Clients</div>
        </div>
        <div className="detail-stat-card">
          <div className="stat-value">
            {formatCurrency(displayedClients.reduce((sum, c) => sum + (parseFloat(c.current_loan_amount) || 0), 0))}
          </div>
          <div className="stat-label">Total UPB</div>
        </div>
        <div className="detail-stat-card">
          <div className="stat-value">
            {formatCurrency(displayedClients.reduce((sum, c) => sum + (parseFloat(c.equity_amount) || 0), 0))}
          </div>
          <div className="stat-label">Total Equity</div>
        </div>
        <div className="detail-stat-card">
          <div className="stat-value">
            {formatCurrency(displayedClients.reduce((sum, c) => sum + (parseFloat(c.annual_servicing_revenue) || 0), 0))}
          </div>
          <div className="stat-label">Annual Revenue</div>
        </div>
      </div>

      {/* Search Bar */}
      <div className="search-bar-container">
        <input
          type="text"
          className="search-bar"
          placeholder="Search clients by name, email, phone, or loan number..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button className="clear-search" onClick={() => setSearchQuery('')}>
            ×
          </button>
        )}
      </div>

      {/* Clients Table */}
      <div className="clients-table-container">
        <table className="clients-table">
          <thead>
            <tr>
              <th>Client Name</th>
              <th>Loan Number</th>
              <th>Loan Type</th>
              <th>Closing Date</th>
              <th>Days Since Funding</th>
              <th>Interest Rate</th>
              <th>Current Balance</th>
              <th>Current Value</th>
              <th>LTV</th>
              <th>Equity</th>
              <th>Annual Revenue</th>
            </tr>
          </thead>
          <tbody>
            {displayedClients.map((client) => (
              <tr
                key={client.id}
                onClick={() => navigate(`/portfolio/${client.id}`)}
                style={{ cursor: 'pointer' }}
                className="client-row"
              >
                <td>
                  <div className="client-name-cell">
                    <strong>{client.client_name}</strong>
                    {client.refinance_opportunity && <span className="opp-badge refi">Refi</span>}
                    {client.heloc_opportunity && <span className="opp-badge heloc">HELOC</span>}
                    {client.rate_rebound_opportunity && <span className="opp-badge rebound">Rebound</span>}
                    {client.high_equity_opportunity && <span className="opp-badge equity">High Equity</span>}
                  </div>
                </td>
                <td className="mono">{client.servicing_loan_number}</td>
                <td>{client.loan_type}</td>
                <td>{new Date(client.closing_date).toLocaleDateString()}</td>
                <td>
                  <span className={`days-badge ${getDaysSinceFundingColor(client.days_since_funding)}`}>
                    {client.days_since_funding} days
                  </span>
                </td>
                <td>{client.interest_rate ? `${client.interest_rate}%` : 'N/A'}</td>
                <td className="currency">{formatCurrency(client.current_loan_amount)}</td>
                <td className="currency">{formatCurrency(client.current_property_value)}</td>
                <td>{client.ltv ? `${(client.ltv * 100).toFixed(1)}%` : 'N/A'}</td>
                <td className="currency positive">{formatCurrency(client.equity_amount)}</td>
                <td className="currency">{formatCurrency(client.annual_servicing_revenue)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {displayedClients.length === 0 && (
          <div className="empty-state">
            {searchQuery ? 'No clients match your search.' : 'No clients found for this metric.'}
          </div>
        )}
      </div>
    </div>
  );
}

export default PortfolioDetail;
