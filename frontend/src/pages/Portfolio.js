import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI, mumAPI } from '../services/api';
import CalendarSidebar from '../components/CalendarSidebar';
import RateMonitorWidget from '../components/RateMonitorWidget';
import { getUserEffectiveRole } from '../config/roleConfig';
import './Portfolio.css';
import { toast } from '../utils/toast';

function Portfolio() {
  const navigate = useNavigate();

  // Determine user's effective role to show/hide MUM Dashboard tab
  const userRole = useMemo(() => {
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        return getUserEffectiveRole(user.permission_role, user.role);
      }
    } catch (e) {
      console.error('Error parsing user from localStorage:', e);
    }
    return 'loan_officer'; // Default fallback
  }, []);

  // Only loan officers and admins see the MUM Dashboard tab
  const showDashboardTab = userRole === 'loan_officer' || userRole === 'admin';

  // Default to 'mum' (clients list) if user doesn't have dashboard access
  const [activeTab, setActiveTab] = useState(showDashboardTab ? 'mum-dashboard' : 'mum');
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
  const [clientSegments, setClientSegments] = useState({});
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterView, setFilterView] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusDropdown, setStatusDropdown] = useState({ show: false, clientId: null, position: { top: 0, left: 0 } });
  const [sortColumn, setSortColumn] = useState('closing_date');
  const [sortDirection, setSortDirection] = useState('desc');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      // Use Promise.allSettled to handle partial failures gracefully
      const results = await Promise.allSettled([
        portfolioAPI.getStats(),
        portfolioAPI.getAll(),
        mumAPI.getAll(),
        mumAPI.getMetrics()
      ]);

      const stats = results[0].status === 'fulfilled' ? results[0].value : {};
      const loans = results[1].status === 'fulfilled' ? results[1].value : [];
      const mum = results[2].status === 'fulfilled' ? results[2].value : [];
      const metrics = results[3].status === 'fulfilled' ? results[3].value : null;

      // Log any failures for debugging
      results.forEach((result, idx) => {
        if (result.status === 'rejected') {
          console.warn(`Portfolio data load ${idx} failed:`, result.reason);
        }
      });

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

      const mumClientsList = Array.isArray(mum) ? mum : [];
      setMumClients(mumClientsList);
      setMumMetrics(metrics || null);

      // Calculate client segments from MUM data
      calculateClientSegments(mumClientsList);
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

  // Calculate client segments from MUM client data
  const calculateClientSegments = (clients) => {
    if (!clients || clients.length === 0) {
      setClientSegments({
        primary_residence: '0%',
        second_home: '0%',
        investment_property: '0%',
        new_construction: '0%',
        first_time_buyer: '0%',
        conventional_mi: '0%',
        fha: '0%',
        va: '0%',
        usda: '0%',
        aio: '0%'
      });
      return;
    }

    const total = clients.length;
    const counts = {
      primary_residence: 0,
      second_home: 0,
      investment_property: 0,
      new_construction: 0,
      first_time_buyer: 0,
      conventional_mi: 0,
      fha: 0,
      va: 0,
      usda: 0,
      aio: 0
    };

    clients.forEach(client => {
      // Occupancy type segmentation
      const occupancy = (client.occupancy_type || client.occupancy || '').toLowerCase();
      if (occupancy.includes('primary') || occupancy === 'owner occupied' || occupancy === 'owner_occupied') {
        counts.primary_residence++;
      } else if (occupancy.includes('second') || occupancy === 'second_home') {
        counts.second_home++;
      } else if (occupancy.includes('invest') || occupancy === 'investment' || occupancy === 'non_owner_occupied') {
        counts.investment_property++;
      }

      // New construction check
      const propertyType = (client.property_type || '').toLowerCase();
      const isNewConstruction = client.is_new_construction || client.new_construction ||
        propertyType.includes('new construction') || propertyType.includes('new_construction') ||
        (client.loan_purpose || '').toLowerCase().includes('construction');
      if (isNewConstruction) {
        counts.new_construction++;
      }

      // First time home buyer check
      const isFirstTimeBuyer = client.is_first_time_buyer || client.first_time_buyer ||
        client.first_time_homebuyer || client.is_first_time_homebuyer ||
        (client.buyer_type || '').toLowerCase().includes('first');
      if (isFirstTimeBuyer) {
        counts.first_time_buyer++;
      }

      // Loan type segmentation — check loan_type first, then program as fallback
      const loanType = (client.loan_type || client.program || '').toLowerCase();
      const hasMI = client.has_mi || client.has_pmi || client.mi_amount > 0 || client.pmi_amount > 0;

      if (loanType.includes('fha')) {
        counts.fha++;
      } else if (loanType.includes('va')) {
        counts.va++;
      } else if (loanType.includes('usda')) {
        counts.usda++;
      } else if (loanType.includes('aio') || loanType.includes('all-in-one') || loanType.includes('heloc')) {
        counts.aio++;
      } else if ((loanType.includes('conv') || loanType.includes('conventional')) && hasMI) {
        counts.conventional_mi++;
      }
    });

    // Calculate percentages
    const toPercent = (count) => `${Math.round((count / total) * 100)}%`;

    setClientSegments({
      primary_residence: toPercent(counts.primary_residence),
      second_home: toPercent(counts.second_home),
      investment_property: toPercent(counts.investment_property),
      new_construction: toPercent(counts.new_construction),
      first_time_buyer: toPercent(counts.first_time_buyer),
      conventional_mi: toPercent(counts.conventional_mi),
      fha: toPercent(counts.fha),
      va: toPercent(counts.va),
      usda: toPercent(counts.usda),
      aio: toPercent(counts.aio)
    });
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
      toast.error('Failed to create MUM client: ' + errorMsg);
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

  // Sort by selected column
  const handleSort = (column) => {
    if (sortColumn === column) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  filteredMumClients = [...filteredMumClients].sort((a, b) => {
    let aVal, bVal;
    switch (sortColumn) {
      case 'client_name':
        aVal = (a.client_name || a.name || '').toLowerCase();
        bVal = (b.client_name || b.name || '').toLowerCase();
        break;
      case 'loan_number':
        aVal = (a.servicing_loan_number || a.loan_number || '').toLowerCase();
        bVal = (b.servicing_loan_number || b.loan_number || '').toLowerCase();
        break;
      case 'closing_date':
        aVal = a.closing_date || a.original_close_date || '';
        bVal = b.closing_date || b.original_close_date || '';
        break;
      case 'days_since_funding':
        aVal = a.days_since_funding || 0;
        bVal = b.days_since_funding || 0;
        break;
      case 'current_rate':
        aVal = a.current_rate || a.interest_rate || 0;
        bVal = b.current_rate || b.interest_rate || 0;
        break;
      case 'loan_balance':
        aVal = a.current_loan_amount || a.loan_balance || 0;
        bVal = b.current_loan_amount || b.loan_balance || 0;
        break;
      default:
        aVal = a.closing_date || '';
        bVal = b.closing_date || '';
    }
    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  // Status options — all stages across Lead, Active Loan, and MUM
  const statusOptions = [
    // Lead stages
    { label: 'Lead Stages', isHeader: true },
    'New',
    'Attempted Contact',
    'Prospect',
    'Application',
    'Pre-Qualified',
    'Pre-Approved',
    'Long-Term Nurture',
    'Withdrawn',
    'Does Not Qualify',
    // Active Loan stages
    { label: 'Active Loan Stages', isHeader: true },
    'Disclosed',
    'Processing',
    'Submitted',
    'Underwriting',
    'UW Received',
    'Conditional Approval',
    'Approved',
    'Suspended',
    'CTC',
    'Clear to Close',
    'Closing',
    'Docs',
    'Docs Out',
    'Cancelled',
    'Denied',
    'Dead',
    // MUM (Funded)
    { label: 'MUM / Closed', isHeader: true },
    'Funded',
  ];

  const getStatusColor = (status) => {
    const colors = {
      // Lead stages
      'New': '#2196F3',
      'Attempted Contact': '#FF9800',
      'Prospect': '#9C27B0',
      'Application': '#00BCD4',
      'Pre-Qualified': '#4CAF50',
      'Pre-Approved': '#8BC34A',
      'Long-Term Nurture': '#607D8B',
      'Withdrawn': '#F44336',
      'Does Not Qualify': '#795548',
      // Active Loan stages
      'Disclosed': '#00C853',
      'Processing': '#FF9800',
      'Submitted': '#FF9800',
      'Underwriting': '#FFC107',
      'UW Received': '#FFC107',
      'Conditional Approval': '#00BCD4',
      'Approved': '#4CAF50',
      'Suspended': '#F44336',
      'CTC': '#4CAF50',
      'Clear to Close': '#4CAF50',
      'Closing': '#4CAF50',
      'Docs': '#4CAF50',
      'Docs Out': '#4CAF50',
      'Cancelled': '#F44336',
      'Denied': '#F44336',
      'Dead': '#9E9E9E',
      // MUM
      'Funded': '#FFD700',
    };
    return colors[status] || '#999';
  };

  const handleStatusClick = (e, clientId) => {
    e.stopPropagation();
    const rect = e.target.getBoundingClientRect();
    setStatusDropdown({
      show: true,
      clientId,
      position: {
        top: rect.bottom + window.scrollY + 5,
        left: rect.left + window.scrollX,
      },
    });
  };

  const closeStatusDropdown = () => {
    setStatusDropdown({ show: false, clientId: null, position: { top: 0, left: 0 } });
  };

  const handleStatusChange = async (newStatus) => {
    const clientId = statusDropdown.clientId;
    closeStatusDropdown();
    try {
      await mumAPI.update(clientId, { stage: newStatus });
      loadData();
      toast.success(`Status updated to ${newStatus}`);
    } catch (err) {
      console.error('Failed to update status:', err);
      toast.error('Failed to update status');
    }
  };

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
          <h1 className="portfolio-title">MUM Clients</h1>
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

      {/* Only show tabs if user has access to dashboard; otherwise just show clients list */}
      {showDashboardTab ? (
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
      ) : null}

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

          {/* Occupancy Type Segments */}
          <div className="mum-stats-grid mum-segments-row">
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=primary_residence')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.primary_residence || '0%'}</div>
              <div className="mum-stat-label">PRIMARY RESIDENCE</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=second_home')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.second_home || '0%'}</div>
              <div className="mum-stat-label">SECOND HOME</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=investment_property')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.investment_property || '0%'}</div>
              <div className="mum-stat-label">INVESTMENT PROPERTY</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=new_construction')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.new_construction || '0%'}</div>
              <div className="mum-stat-label">NEW CONSTRUCTION</div>
            </div>
          </div>

          {/* Loan Type Segments */}
          <div className="mum-stats-grid mum-segments-row" style={{ marginTop: '16px' }}>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=conventional_mi')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.conventional_mi || '0%'}</div>
              <div className="mum-stat-label">CONVENTIONAL W/MI</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=fha')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.fha || '0%'}</div>
              <div className="mum-stat-label">FHA</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=va')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.va || '0%'}</div>
              <div className="mum-stat-label">VA</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=usda')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.usda || '0%'}</div>
              <div className="mum-stat-label">USDA</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=aio')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.aio || '0%'}</div>
              <div className="mum-stat-label">AIO</div>
            </div>
            <div
              className="mum-stat-card segment-card clickable"
              onClick={() => navigate('/portfolio/detail?metric=first_time_buyer')}
              style={{ cursor: 'pointer' }}
            >
              <div className="mum-stat-value">{clientSegments?.first_time_buyer || '0%'}</div>
              <div className="mum-stat-label">FIRST TIME BUYERS</div>
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

          {/* Rate Monitor Widget */}
          <div className="dashboard-section-header">
            <h2>RATE MONITOR</h2>
            <p>Track refinance opportunities when rates hit your targets</p>
          </div>
          <RateMonitorWidget />
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
                  <th onClick={() => handleSort('client_name')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                    Client Name {sortColumn === 'client_name' ? (sortDirection === 'asc' ? '▲' : '▼') : ''}
                  </th>
                  <th onClick={() => handleSort('loan_number')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                    Loan Number {sortColumn === 'loan_number' ? (sortDirection === 'asc' ? '▲' : '▼') : ''}
                  </th>
                  <th onClick={() => handleSort('closing_date')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                    Closed Date {sortColumn === 'closing_date' ? (sortDirection === 'asc' ? '▲' : '▼') : '▼'}
                  </th>
                  <th onClick={() => handleSort('days_since_funding')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                    Days Since Funding {sortColumn === 'days_since_funding' ? (sortDirection === 'asc' ? '▲' : '▼') : ''}
                  </th>
                  <th onClick={() => handleSort('current_rate')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                    Current Rate {sortColumn === 'current_rate' ? (sortDirection === 'asc' ? '▲' : '▼') : ''}
                  </th>
                  <th onClick={() => handleSort('loan_balance')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                    Loan Balance {sortColumn === 'loan_balance' ? (sortDirection === 'asc' ? '▲' : '▼') : ''}
                  </th>
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
                    <td>{(client.current_rate || client.interest_rate) ? `${client.current_rate || client.interest_rate}%` : 'N/A'}</td>
                    <td>${(client.current_loan_amount || client.loan_balance || 0).toLocaleString()}</td>
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

      {/* Status Dropdown Popup */}
      {statusDropdown.show && (
        <>
          <div
            style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 999 }}
            onClick={closeStatusDropdown}
          />
          <div
            style={{
              position: 'absolute',
              top: statusDropdown.position.top,
              left: statusDropdown.position.left,
              backgroundColor: 'white',
              borderRadius: '8px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
              zIndex: 1000,
              minWidth: '200px',
              maxHeight: '400px',
              overflowY: 'auto',
            }}
          >
            <div style={{ padding: '10px 14px', fontWeight: 600, fontSize: '13px', borderBottom: '1px solid #e5e7eb' }}>
              Change Status
            </div>
            {statusOptions.map((status, idx) => (
              status.isHeader ? (
                <div
                  key={status.label}
                  style={{
                    padding: '8px 14px',
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    color: '#6b7280',
                    borderTop: idx > 0 ? '1px solid #e5e7eb' : 'none',
                    marginTop: idx > 0 ? '4px' : 0,
                    letterSpacing: '0.05em',
                    background: '#fafafa',
                  }}
                >
                  {status.label}
                </div>
              ) : (
                <button
                  key={status}
                  onClick={() => handleStatusChange(status)}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '10px 14px',
                    border: 'none',
                    background: 'white',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontSize: '13px',
                    borderLeft: `4px solid ${getStatusColor(status)}`,
                    transition: 'background 0.2s',
                  }}
                  onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                  onMouseLeave={(e) => e.target.style.background = 'white'}
                >
                  {status}
                </button>
              )
            ))}
          </div>
        </>
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
