import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI, mumAPI } from '../services/api';
import './Portfolio.css';

// Generate mock portfolio loans
const generateMockPortfolioLoans = () => {
  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth();

  return [
    { id: 1, borrower: 'Thomas Anderson', loanAmount: 425000, loanType: '30-Year Fixed', status: 'Active', closeDate: new Date(currentYear, currentMonth - 2, 15).toISOString(), rate: 6.875 },
    { id: 2, borrower: 'Sarah Connor', loanAmount: 380000, loanType: '15-Year Fixed', status: 'Active', closeDate: new Date(currentYear, currentMonth - 4, 22).toISOString(), rate: 6.25 },
    { id: 3, borrower: 'John McClane', loanAmount: 520000, loanType: '30-Year Fixed', status: 'Active', closeDate: new Date(currentYear, currentMonth - 6, 10).toISOString(), rate: 7.0 },
    { id: 4, borrower: 'Ellen Ripley', loanAmount: 295000, loanType: 'FHA 30-Year', status: 'Active', closeDate: new Date(currentYear, currentMonth - 8, 5).toISOString(), rate: 6.5 },
    { id: 5, borrower: 'Luke Skywalker', loanAmount: 615000, loanType: 'Jumbo 30-Year', status: 'Active', closeDate: new Date(currentYear, currentMonth - 10, 18).toISOString(), rate: 7.25 },
    { id: 6, borrower: 'Princess Leia', loanAmount: 340000, loanType: 'VA 30-Year', status: 'Active', closeDate: new Date(currentYear, currentMonth - 12, 30).toISOString(), rate: 6.0 },
    { id: 7, borrower: 'Han Solo', loanAmount: 450000, loanType: '30-Year Fixed', status: 'Active', closeDate: new Date(currentYear - 1, 11, 15).toISOString(), rate: 6.75 },
    { id: 8, borrower: 'Indiana Jones', loanAmount: 385000, loanType: '20-Year Fixed', status: 'Active', closeDate: new Date(currentYear - 1, 9, 8).toISOString(), rate: 6.5 },
    { id: 9, borrower: 'Marty McFly', loanAmount: 495000, loanType: '30-Year Fixed', status: 'Active', closeDate: new Date(currentYear - 1, 7, 22).toISOString(), rate: 6.875 },
    { id: 10, borrower: 'Tony Stark', loanAmount: 725000, loanType: 'Jumbo 15-Year', status: 'Active', closeDate: new Date(currentYear - 1, 5, 12).toISOString(), rate: 6.375 },
    { id: 11, borrower: 'Bruce Wayne', loanAmount: 850000, loanType: 'Jumbo 30-Year', status: 'Active', closeDate: new Date(currentYear - 1, 3, 28).toISOString(), rate: 7.125 },
    { id: 12, borrower: 'Diana Prince', loanAmount: 415000, loanType: '30-Year Fixed', status: 'Active', closeDate: new Date(currentYear - 1, 1, 14).toISOString(), rate: 6.625 },
    { id: 13, borrower: 'Peter Parker', loanAmount: 325000, loanType: 'FHA 30-Year', status: 'Active', closeDate: new Date(currentYear - 2, 10, 20).toISOString(), rate: 6.25 },
    { id: 14, borrower: 'Clark Kent', loanAmount: 565000, loanType: '30-Year Fixed', status: 'Active', closeDate: new Date(currentYear - 2, 8, 5).toISOString(), rate: 6.5 },
    { id: 15, borrower: 'Natasha Romanoff', loanAmount: 395000, loanType: '15-Year Fixed', status: 'Active', closeDate: new Date(currentYear - 2, 6, 18).toISOString(), rate: 5.875 },
  ];
};

// Generate mock MUM clients
const generateMockMumClients = () => {
  const currentDate = new Date();

  return [
    {
      id: 1,
      name: 'Thomas Anderson',
      email: 'tanderson@email.com',
      phone: '(555) 111-2222',
      loan_amount: 425000,
      close_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 2, 15).toISOString(),
      days_since_funding: 60,
      next_touchpoint: new Date(currentDate.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 85,
      refinance_opportunity: true,
      last_contact: new Date(currentDate.getTime() - 14 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 2,
      anniversary_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 2, 15).toISOString(),
    },
    {
      id: 2,
      name: 'Sarah Connor',
      email: 'sconnor@email.com',
      phone: '(555) 222-3333',
      loan_amount: 380000,
      close_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 4, 22).toISOString(),
      days_since_funding: 120,
      next_touchpoint: new Date(currentDate.getTime() + 3 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 92,
      refinance_opportunity: false,
      last_contact: new Date(currentDate.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 1,
      anniversary_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 4, 22).toISOString(),
    },
    {
      id: 3,
      name: 'John McClane',
      email: 'jmcclane@email.com',
      phone: '(555) 333-4444',
      loan_amount: 520000,
      close_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 6, 10).toISOString(),
      days_since_funding: 180,
      next_touchpoint: new Date(currentDate.getTime() + 14 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 78,
      refinance_opportunity: true,
      last_contact: new Date(currentDate.getTime() - 21 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 3,
      anniversary_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 6, 10).toISOString(),
    },
    {
      id: 4,
      name: 'Ellen Ripley',
      email: 'eripley@email.com',
      phone: '(555) 444-5555',
      loan_amount: 295000,
      close_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 8, 5).toISOString(),
      days_since_funding: 240,
      next_touchpoint: new Date(currentDate.getTime() + 5 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 88,
      refinance_opportunity: false,
      last_contact: new Date(currentDate.getTime() - 10 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 0,
      anniversary_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 8, 5).toISOString(),
    },
    {
      id: 5,
      name: 'Luke Skywalker',
      email: 'lskywalker@email.com',
      phone: '(555) 555-6666',
      loan_amount: 615000,
      close_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 10, 18).toISOString(),
      days_since_funding: 300,
      next_touchpoint: new Date(currentDate.getTime() + 2 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 95,
      refinance_opportunity: true,
      last_contact: new Date(currentDate.getTime() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 4,
      anniversary_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 10, 18).toISOString(),
    },
    {
      id: 6,
      name: 'Princess Leia',
      email: 'pleia@email.com',
      phone: '(555) 666-7777',
      loan_amount: 340000,
      close_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 12, 30).toISOString(),
      days_since_funding: 360,
      next_touchpoint: new Date(currentDate.getTime() + 1 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 90,
      refinance_opportunity: false,
      last_contact: new Date(currentDate.getTime() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 2,
      anniversary_date: new Date(currentDate.getFullYear(), currentDate.getMonth() - 12, 30).toISOString(),
    },
    {
      id: 7,
      name: 'Han Solo',
      email: 'hsolo@email.com',
      phone: '(555) 777-8888',
      loan_amount: 450000,
      close_date: new Date(currentDate.getFullYear() - 1, 11, 15).toISOString(),
      days_since_funding: 395,
      next_touchpoint: new Date(currentDate.getTime() + 10 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 82,
      refinance_opportunity: true,
      last_contact: new Date(currentDate.getTime() - 28 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 1,
      anniversary_date: new Date(currentDate.getFullYear() - 1, 11, 15).toISOString(),
    },
    {
      id: 8,
      name: 'Indiana Jones',
      email: 'ijones@email.com',
      phone: '(555) 888-9999',
      loan_amount: 385000,
      close_date: new Date(currentDate.getFullYear() - 1, 9, 8).toISOString(),
      days_since_funding: 455,
      next_touchpoint: new Date(currentDate.getTime() + 20 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 75,
      refinance_opportunity: false,
      last_contact: new Date(currentDate.getTime() - 35 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 0,
      anniversary_date: new Date(currentDate.getFullYear() - 1, 9, 8).toISOString(),
    },
    {
      id: 9,
      name: 'Marty McFly',
      email: 'mmcfly@email.com',
      phone: '(555) 999-0000',
      loan_amount: 495000,
      close_date: new Date(currentDate.getFullYear() - 1, 7, 22).toISOString(),
      days_since_funding: 500,
      next_touchpoint: new Date(currentDate.getTime() + 4 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 87,
      refinance_opportunity: true,
      last_contact: new Date(currentDate.getTime() - 12 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 2,
      anniversary_date: new Date(currentDate.getFullYear() - 1, 7, 22).toISOString(),
    },
    {
      id: 10,
      name: 'Tony Stark',
      email: 'tstark@email.com',
      phone: '(555) 000-1111',
      loan_amount: 725000,
      close_date: new Date(currentDate.getFullYear() - 1, 5, 12).toISOString(),
      days_since_funding: 560,
      next_touchpoint: new Date(currentDate.getTime() + 6 * 24 * 60 * 60 * 1000).toISOString(),
      engagement_score: 98,
      refinance_opportunity: false,
      last_contact: new Date(currentDate.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      referrals_sent: 5,
      anniversary_date: new Date(currentDate.getFullYear() - 1, 5, 12).toISOString(),
    },
  ];
};

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
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterView, setFilterView] = useState('all');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [stats, loans, mum] = await Promise.all([
        portfolioAPI.getStats(),
        portfolioAPI.getAll(),
        mumAPI.getAll()
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
    } catch (error) {
      console.error('Failed to load portfolio data:', error);
      // Use mock data on error
      const mockLoans = generateMockPortfolioLoans();
      const mockMum = generateMockMumClients();

      const totalVolume = mockLoans.reduce((sum, loan) => sum + loan.loanAmount, 0);
      const commission = totalVolume * 0.01;
      const portfolioValue = totalVolume * 0.9;
      const annualReturn = portfolioValue > 0 ? (commission / portfolioValue * 100) : 0;

      setPortfolioData({
        totalLoans: mockLoans.length,
        totalVolume: totalVolume,
        commissionGenerated: commission,
        portfolioValue: portfolioValue,
        annualReturn: annualReturn,
        loans: mockLoans
      });

      setMumClients(mockMum);
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
    if (!window.confirm('Delete this client?')) return;
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

  const filteredMumClients = filterView === 'all'
    ? mumClients
    : filterView === 'opportunities'
    ? mumClients.filter(c => c.refinance_opportunity)
    : mumClients;

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

      <div className="portfolio-stats">
        <div className="stat-card">
          <div className="stat-value">{portfolioData.totalLoans}</div>
          <div className="stat-label">TOTAL LOANS</div>
        </div>

        <div className="stat-card">
          <div className="stat-value">{formatCurrency(portfolioData.totalVolume)}</div>
          <div className="stat-label">TOTAL VOLUME</div>
        </div>

        <div className="stat-card">
          <div className="stat-value">{formatCurrency(portfolioData.commissionGenerated)}</div>
          <div className="stat-label">COMMISSION GENERATED</div>
        </div>

        <div className="stat-card">
          <div className="stat-value">{formatCurrency(portfolioData.portfolioValue)}</div>
          <div className="stat-label">PORTFOLIO VALUE</div>
        </div>

        <div className="stat-card">
          <div className="stat-value">{portfolioData.annualReturn.toFixed(2)}%</div>
          <div className="stat-label">ANNUAL RETURN %</div>
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
          className={activeTab === 'loans' ? 'active' : ''}
          onClick={() => setActiveTab('loans')}
        >
          Loan History
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
            <div className="mum-stat-card">
              <div className="mum-stat-value">$184,250,000</div>
              <div className="mum-stat-label">TOTAL UPB UNDER MGT</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">+$3.4M</div>
              <div className="mum-stat-sublabel">(MoM)</div>
              <div className="mum-stat-label">NET MUM GROWTH</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">1.82%</div>
              <div className="mum-stat-sublabel">Annual Yield</div>
              <div className="mum-stat-label">PORTFOLIO REVENUE YIELD</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">$12,480</div>
              <div className="mum-stat-sublabel">Avg. per Client</div>
              <div className="mum-stat-label">CLIENT LIFETIME VALUE</div>
            </div>
          </div>

          {/* Second Row Stats */}
          <div className="mum-stats-grid mum-stats-row">
            <div className="mum-stat-card">
              <div className="mum-stat-value">487</div>
              <div className="mum-stat-sublabel">Active Clients</div>
              <div className="mum-stat-label">CLIENT COUNT</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">+22 / -5</div>
              <div className="mum-stat-sublabel">Added / Lost</div>
              <div className="mum-stat-label">LOANS ADDED VS LOST</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">+41%</div>
              <div className="mum-stat-sublabel">Above Industry Avg</div>
              <div className="mum-stat-label">CAPTURE RATE ALPHA</div>
            </div>
            <div className="mum-stat-card">
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
            <div className="mum-stat-card opportunity-card">
              <div className="mum-stat-value">74</div>
              <div className="mum-stat-sublabel">Clients Eligible</div>
              <div className="mum-stat-label">RATE REBOUND OPPS</div>
              <div className="opportunity-highlight">18 High-Priority</div>
            </div>
            <div className="mum-stat-card opportunity-card">
              <div className="mum-stat-value">112</div>
              <div className="mum-stat-sublabel">Clients > $150K Equity</div>
              <div className="mum-stat-label">EQUITY ACCESS OPPS</div>
              <div className="opportunity-highlight">37 Ready Now</div>
            </div>
            <div className="mum-stat-card opportunity-card">
              <div className="mum-stat-value">32</div>
              <div className="mum-stat-sublabel">High-Priority Files</div>
              <div className="mum-stat-label">HELOC / REFI HEATMAP</div>
              <div className="opportunity-highlight">rate drop + equity + LTV</div>
            </div>
          </div>

          {/* Annual Revenue Performance */}
          <div className="dashboard-section-header">
            <h2>ANNUAL REVENUE PERFORMANCE</h2>
          </div>

          <div className="mum-stats-grid mum-revenue-row">
            <div className="mum-stat-card">
              <div className="mum-stat-value">$2,180</div>
              <div className="mum-stat-sublabel">per Client</div>
              <div className="mum-stat-label">ANNUAL REVENUE / CL</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">0.64</div>
              <div className="mum-stat-sublabel">Referrals/yr</div>
              <div className="mum-stat-label">REFERRAL RATE / CLIENT</div>
            </div>
            <div className="mum-stat-card">
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
            <div className="mum-stat-card">
              <div className="mum-stat-value">89/100</div>
              <div className="mum-stat-label">PORTFOLIO STABILITY</div>
            </div>
            <div className="mum-stat-card">
              <div className="mum-stat-value">±14%</div>
              <div className="mum-stat-sublabel">Month-to-Month</div>
              <div className="mum-stat-label">VARIANCE IN VOLUME</div>
            </div>
            <div className="mum-stat-card">
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
            <div className="mum-stat-card segment-card">
              <div className="mum-stat-value">62%</div>
              <div className="mum-stat-label">PRIMARY RESIDENCE</div>
            </div>
            <div className="mum-stat-card segment-card">
              <div className="mum-stat-value">18%</div>
              <div className="mum-stat-label">INVESTORS</div>
            </div>
            <div className="mum-stat-card segment-card">
              <div className="mum-stat-value">12%</div>
              <div className="mum-stat-label">BUILDERS / RTO</div>
            </div>
            <div className="mum-stat-card segment-card">
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

      {activeTab === 'loans' && (
        <div className="loans-table-container">
          <h2>Closed Loans</h2>
          <table className="loans-table">
            <thead>
              <tr>
                <th>Borrower</th>
                <th>Loan Amount</th>
                <th>Type</th>
                <th>Rate</th>
                <th>Status</th>
                <th>Close Date</th>
              </tr>
            </thead>
            <tbody>
              {portfolioData.loans.map((loan) => (
                <tr
                  key={loan.id}
                  onClick={() => navigate(`/loans/${loan.id}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{loan.borrower}</td>
                  <td>{formatCurrency(loan.loanAmount)}</td>
                  <td>{loan.loanType}</td>
                  <td>{loan.rate}%</td>
                  <td>
                    <span className={`status-badge status-${loan.status.toLowerCase()}`}>
                      {loan.status}
                    </span>
                  </td>
                  <td>{new Date(loan.closeDate).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {portfolioData.loans.length === 0 && (
            <div className="empty-state">No closed loans found.</div>
          )}
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
                      <strong>{client.name}</strong>
                    </td>
                    <td>{client.loan_number}</td>
                    <td>
                      {new Date(client.original_close_date).toLocaleDateString()}
                    </td>
                    <td>
                      <span className={`days-badge ${getDaysSinceFundingColor(client.days_since_funding)}`}>
                        {client.days_since_funding} days
                      </span>
                    </td>
                    <td>{client.original_rate ? `${client.original_rate}%` : 'N/A'}</td>
                    <td>{client.current_rate ? `${client.current_rate}%` : 'N/A'}</td>
                    <td>${client.loan_balance?.toLocaleString() || 0}</td>
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
                          onClick={() => handleDeleteClient(client.id)}
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
