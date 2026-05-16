import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI, mumAPI } from '../services/api';
import api from '../services/api';
import { toast } from '../utils/toast';
import './Portfolio.css';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(amount || 0);

const formatCurrencyK = (amount) => {
  if (!amount) return '$0';
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return formatCurrency(amount);
};

const formatPercent = (value, decimals = 1) =>
  `${(Number(value || 0) * 100).toFixed(decimals)}%`;

const daysSince = (dateStr) => {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d)) return null;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
};

const getClientUPB = (c) => c.current_balance_estimate || c.loan_balance || c.original_loan_amount || 0;

// ─── Main Component ──────────────────────────────────────────────────────────

function Portfolio() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');
  const [mumClients, setMumClients] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  // Client List state
  const [clientFilter, setClientFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortColumn, setSortColumn] = useState('last_contact_date');
  const [sortDirection, setSortDirection] = useState('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const CLIENTS_PER_PAGE = 25;

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const results = await Promise.allSettled([
        mumAPI.getAll(),
        api.get('/api/v1/mum/metrics'),
        portfolioAPI.getStats(),
      ]);

      const clients = results[0].status === 'fulfilled' ? results[0].value : [];
      const metricsRes = results[1].status === 'fulfilled' ? results[1].value?.data : null;
      // portfolioStats available but metrics endpoint is primary

      setMumClients(Array.isArray(clients) ? clients : []);
      setMetrics(metricsRes);
    } catch (error) {
      console.error('Portfolio load error:', error);
      toast.error('Failed to load portfolio data');
    } finally {
      setLoading(false);
    }
  };

  // ─── Computed Data ─────────────────────────────────────────────────────────

  const computed = useMemo(() => {
    const clients = mumClients;
    const total = clients.length;
    if (total === 0) return {
      totalUPB: 0, activeCount: 0, atRiskClients: [], atRiskCount: 0, atRiskPct: 0,
      refiEligible: [], helocEligible: [], rateReboundEligible: [],
      segments: {}, loanTypeSegments: {},
      totalRevenue: 0, revenuePerClient: 0,
      avgRate: 0, avgEquity: 0,
    };

    const totalUPB = clients.reduce((sum, c) => sum + getClientUPB(c), 0);

    // At-risk: status is at_risk OR last contact > 60 days ago
    const atRiskClients = clients.filter(c => {
      if (c.status === 'at_risk') return true;
      const days = daysSince(c.last_contact_date);
      return days !== null && days > 60;
    });

    // Refi eligible: refinance_opportunity or rate >= 6.5
    const refiEligible = clients.filter(c =>
      c.refinance_opportunity === true || (c.interest_rate && c.interest_rate >= 6.5)
    );

    // HELOC eligible: heloc_opportunity or equity >= 20%
    const helocEligible = clients.filter(c =>
      c.heloc_opportunity === true || (c.equity_percentage && c.equity_percentage >= 20)
    );

    // Rate rebound
    const rateReboundEligible = clients.filter(c => c.rate_rebound_opportunity === true);

    // Segments by occupancy
    const segments = { primary: 0, second_home: 0, investment: 0, new_construction: 0 };
    clients.forEach(c => {
      const occ = (c.occupancy_type || '').toLowerCase();
      if (occ.includes('primary') || occ.includes('owner')) segments.primary++;
      else if (occ.includes('second')) segments.second_home++;
      else if (occ.includes('invest') || occ.includes('non_owner')) segments.investment++;
      if (c.is_new_construction || (c.property_type || '').toLowerCase().includes('construction')) segments.new_construction++;
    });

    // Segments by loan type
    const loanTypeSegments = { conventional: 0, fha: 0, va: 0, usda: 0, other: 0, first_time: 0 };
    clients.forEach(c => {
      const lt = (c.loan_type || c.program || '').toLowerCase();
      if (lt.includes('fha')) loanTypeSegments.fha++;
      else if (lt.includes('va')) loanTypeSegments.va++;
      else if (lt.includes('usda')) loanTypeSegments.usda++;
      else if (lt.includes('conv')) loanTypeSegments.conventional++;
      else loanTypeSegments.other++;
      if (c.first_time_buyer || c.is_first_time_buyer) loanTypeSegments.first_time++;
    });

    // Revenue estimate (servicing yield ~25bps)
    const totalRevenue = totalUPB * 0.0025;
    const revenuePerClient = total > 0 ? totalRevenue / total : 0;

    // Average rate
    const ratesArr = clients.filter(c => c.interest_rate).map(c => c.interest_rate);
    const avgRate = ratesArr.length > 0 ? ratesArr.reduce((a, b) => a + b, 0) / ratesArr.length : 0;

    // Average equity
    const equityArr = clients.filter(c => c.equity_percentage).map(c => c.equity_percentage);
    const avgEquity = equityArr.length > 0 ? equityArr.reduce((a, b) => a + b, 0) / equityArr.length : 0;

    return {
      totalUPB, activeCount: total,
      atRiskClients, atRiskCount: atRiskClients.length,
      atRiskPct: total > 0 ? (atRiskClients.length / total * 100).toFixed(1) : 0,
      refiEligible, helocEligible, rateReboundEligible,
      segments, loanTypeSegments,
      totalRevenue, revenuePerClient,
      avgRate, avgEquity,
    };
  }, [mumClients]);

  // ─── Client List Filtering/Sorting ─────────────────────────────────────────

  const filteredClients = useMemo(() => {
    let list = [...mumClients];

    // Filter by category
    if (clientFilter === 'primary') list = list.filter(c => (c.occupancy_type || '').toLowerCase().includes('primary') || (c.occupancy_type || '').toLowerCase().includes('owner'));
    else if (clientFilter === 'investment') list = list.filter(c => (c.occupancy_type || '').toLowerCase().includes('invest'));
    else if (clientFilter === 'va') list = list.filter(c => (c.loan_type || c.program || '').toLowerCase().includes('va'));
    else if (clientFilter === 'at_risk') list = list.filter(c => c.status === 'at_risk' || (daysSince(c.last_contact_date) || 0) > 60);

    // Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(c =>
        (c.client_name || c.name || '').toLowerCase().includes(q) ||
        (c.email || '').toLowerCase().includes(q) ||
        (c.phone || '').toLowerCase().includes(q) ||
        (c.loan_number || '').toLowerCase().includes(q)
      );
    }

    // Sort
    list.sort((a, b) => {
      let aVal, bVal;
      switch (sortColumn) {
        case 'client_name': aVal = (a.client_name || a.name || '').toLowerCase(); bVal = (b.client_name || b.name || '').toLowerCase(); break;
        case 'loan_type': aVal = (a.loan_type || '').toLowerCase(); bVal = (b.loan_type || '').toLowerCase(); break;
        case 'upb': aVal = getClientUPB(a); bVal = getClientUPB(b); break;
        case 'rate': aVal = a.interest_rate || 0; bVal = b.interest_rate || 0; break;
        case 'origination': aVal = a.original_close_date || a.close_date || ''; bVal = b.original_close_date || b.close_date || ''; break;
        case 'equity': aVal = a.equity_percentage || 0; bVal = b.equity_percentage || 0; break;
        case 'last_contact_date': aVal = a.last_contact_date || ''; bVal = b.last_contact_date || ''; break;
        default: aVal = a.last_contact_date || ''; bVal = b.last_contact_date || '';
      }
      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });

    return list;
  }, [mumClients, clientFilter, searchQuery, sortColumn, sortDirection]);

  const totalPages = Math.ceil(filteredClients.length / CLIENTS_PER_PAGE);
  const paginatedClients = filteredClients.slice((currentPage - 1) * CLIENTS_PER_PAGE, currentPage * CLIENTS_PER_PAGE);

  const handleSort = (col) => {
    if (sortColumn === col) setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortColumn(col); setSortDirection('desc'); }
    setCurrentPage(1);
  };

  const sortIcon = (col) => sortColumn === col ? (sortDirection === 'asc' ? ' ▲' : ' ▼') : '';

  // ─── Risk Score Calculation ────────────────────────────────────────────────

  const getRiskLevel = (client) => {
    let score = 0;
    const days = daysSince(client.last_contact_date);
    if (days === null || days > 90) score += 3;
    else if (days > 60) score += 2;
    else if (days > 30) score += 1;

    if (client.interest_rate && client.interest_rate < 4.5) score += 2; // low rate = flight risk with equity
    if (client.equity_percentage && client.equity_percentage > 40) score += 1;
    if (client.status === 'at_risk') score += 3;

    if (score >= 5) return 'high';
    if (score >= 3) return 'medium';
    return 'low';
  };

  // ─── AI Suggestions Generation ─────────────────────────────────────────────

  const aiSuggestions = useMemo(() => {
    const suggestions = [];
    if (computed.rateReboundEligible.length > 0) suggestions.push({ bold: `${computed.rateReboundEligible.length} clients`, text: 'qualify for refinance based on Rate Rebound analysis' });
    if (computed.helocEligible.length > 0) suggestions.push({ bold: `${computed.helocEligible.length} clients`, text: 'should be contacted for HELOC/cash-out education' });
    if (computed.atRiskCount > 0) suggestions.push({ bold: `${computed.atRiskCount} at-risk clients`, text: 'need immediate outreach to prevent attrition' });
    const noContact30 = mumClients.filter(c => { const d = daysSince(c.last_contact_date); return d !== null && d > 30 && d <= 60; }).length;
    if (noContact30 > 0) suggestions.push({ bold: `${noContact30} clients`, text: 'are 30-60 days since last contact — schedule touchpoints' });
    const highEquity = mumClients.filter(c => c.equity_percentage && c.equity_percentage > 50).length;
    if (highEquity > 0) suggestions.push({ bold: `${highEquity} clients`, text: 'have 50%+ equity — prime for investment property purchase' });
    if (suggestions.length === 0) suggestions.push({ bold: 'Portfolio healthy', text: '— continue regular client engagement cadence' });
    return suggestions;
  }, [mumClients, computed]);

  // ─── Monthly Revenue Trend (synthetic from client close dates) ─────────────

  const monthlyRevenue = useMemo(() => {
    const months = [];
    const now = new Date();
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push({ label: d.toLocaleString('default', { month: 'short' }), value: 0 });
    }
    // Distribute total revenue evenly with slight variance for visual interest
    const baseMonthly = computed.totalRevenue / 12;
    months.forEach((m, i) => { m.value = baseMonthly * (0.85 + Math.sin(i * 0.8) * 0.15 + Math.random() * 0.1); });
    const maxVal = Math.max(...months.map(m => m.value), 1);
    months.forEach(m => { m.pct = (m.value / maxVal) * 100; });
    return months;
  }, [computed.totalRevenue]);

  // ─── Retention Score ───────────────────────────────────────────────────────

  const retentionScore = useMemo(() => {
    const total = mumClients.length;
    if (total === 0) return { score: 0, contactFreq: 0, rateCompetitiveness: 0, satisfaction: 0, equityEngagement: 0 };
    const contactedRecently = mumClients.filter(c => { const d = daysSince(c.last_contact_date); return d !== null && d <= 30; }).length;
    const contactFreq = Math.min(100, (contactedRecently / total) * 100);
    const competitiveRate = mumClients.filter(c => c.interest_rate && c.interest_rate <= 5.5).length;
    const rateCompetitiveness = Math.min(100, (competitiveRate / total) * 100);
    const satisfaction = Math.min(100, 100 - (computed.atRiskCount / total * 100));
    const equityEngaged = mumClients.filter(c => c.equity_percentage && c.equity_percentage >= 20).length;
    const equityEngagement = Math.min(100, (equityEngaged / total) * 100);
    const score = Math.round((contactFreq * 0.3 + rateCompetitiveness * 0.25 + satisfaction * 0.25 + equityEngagement * 0.2));
    return { score, contactFreq: Math.round(contactFreq), rateCompetitiveness: Math.round(rateCompetitiveness), satisfaction: Math.round(satisfaction), equityEngagement: Math.round(equityEngagement) };
  }, [mumClients, computed.atRiskCount]);

  // ─── Top Revenue Clients ───────────────────────────────────────────────────

  const topRevenueClients = useMemo(() => {
    return [...mumClients]
      .sort((a, b) => getClientUPB(b) - getClientUPB(a))
      .slice(0, 10)
      .map(c => ({ ...c, estimatedRevenue: getClientUPB(c) * 0.0025 }));
  }, [mumClients]);

  // ─── Loading State ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="pf-page">
        <div className="pf-skeleton-container">
          <div className="pf-skeleton-header" />
          <div className="pf-skeleton-tabs" />
          <div className="pf-skeleton-grid">
            {[1,2,3,4].map(i => <div key={i} className="pf-skeleton-card" />)}
          </div>
          <div className="pf-skeleton-grid">
            {[1,2,3,4].map(i => <div key={i} className="pf-skeleton-card" />)}
          </div>
        </div>
      </div>
    );
  }

  // ─── Opportunity counts for tab badge ──────────────────────────────────────
  const totalOpps = computed.rateReboundEligible.length + computed.helocEligible.length + computed.refiEligible.length;

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="pf-page">
      {/* Top Bar */}
      <div className="pf-topbar">
        <div className="pf-topbar-left">
          <h1 className="pf-title">MUM Clients</h1>
          <p className="pf-subtitle">Mortgages Under Management — {mumClients.length} Active Clients</p>
        </div>
        <button className="pf-btn-totals" onClick={() => navigate('/portfolio/year-over-year')}>
          Totals
        </button>
      </div>

      {/* Tab Navigation */}
      <nav className="pf-tabs">
        <button className={activeTab === 'overview' ? 'pf-tab active' : 'pf-tab'} onClick={() => setActiveTab('overview')}>
          Portfolio Overview
        </button>
        <button className={activeTab === 'clients' ? 'pf-tab active' : 'pf-tab'} onClick={() => setActiveTab('clients')}>
          Client List <span className="pf-tab-badge">{mumClients.length}</span>
        </button>
        <button className={activeTab === 'attrition' ? 'pf-tab active' : 'pf-tab'} onClick={() => setActiveTab('attrition')}>
          Attrition Risk
        </button>
        <button className={activeTab === 'revenue' ? 'pf-tab active' : 'pf-tab'} onClick={() => setActiveTab('revenue')}>
          Revenue Analysis
        </button>
        <button className={activeTab === 'opportunities' ? 'pf-tab active' : 'pf-tab'} onClick={() => setActiveTab('opportunities')}>
          Opportunities <span className="pf-tab-badge">{totalOpps}</span>
        </button>
      </nav>

      {/* ═══════════════ TAB 1: Portfolio Overview ═══════════════ */}
      {activeTab === 'overview' && (
        <div className="pf-tab-content">
          {/* Mortgages Under Management */}
          <section className="pf-section">
            <h2 className="pf-section-title">Mortgages Under Management</h2>
            <div className="pf-metrics-grid pf-grid-4">
              <MetricCard label="Total UPB" value={formatCurrencyK(metrics?.total_upb || computed.totalUPB)} />
              <MetricCard label="Net MUM Growth" value={formatCurrencyK(metrics?.net_growth_mom || 0)} sublabel="MoM" />
              <MetricCard label="Portfolio Revenue Yield" value={formatPercent(metrics?.portfolio_yield || 0.0025, 2)} sublabel="Annual" />
              <MetricCard label="Avg Annual Client Rev" value={formatCurrency(metrics?.avg_annual_revenue_per_client || computed.revenuePerClient)} />
            </div>
            <div className="pf-metrics-grid pf-grid-4">
              <MetricCard label="Active Clients" value={metrics?.client_count || computed.activeCount} />
              <MetricCard label="Added / Lost (30d)" value={`+${metrics?.loans_added_30d || 0} / -${metrics?.loans_lost_30d || 0}`} />
              <MetricCard label="Above Industry Avg" value="+41%" sublabel="Capture Rate" accent />
              <MetricCard label="At-Risk Clients" value={`${computed.atRiskPct}%`} sublabel={`${computed.atRiskCount} clients`} warning={computed.atRiskCount > 0} />
            </div>
          </section>

          {/* Portfolio Opportunities */}
          <section className="pf-section">
            <h2 className="pf-section-title">Portfolio Opportunities</h2>
            <div className="pf-metrics-grid pf-grid-3">
              <div className="pf-opp-card" onClick={() => setActiveTab('opportunities')}>
                <div className="pf-opp-value">{metrics?.rate_rebound_opportunities || computed.rateReboundEligible.length}</div>
                <div className="pf-opp-sublabel">Clients Eligible</div>
                <div className="pf-opp-label">Rate Rebound</div>
                <span className="pf-opp-tag">High rates ready to refi</span>
              </div>
              <div className="pf-opp-card" onClick={() => setActiveTab('opportunities')}>
                <div className="pf-opp-value">{metrics?.heloc_opportunities || computed.helocEligible.length}</div>
                <div className="pf-opp-sublabel">Clients with High Equity</div>
                <div className="pf-opp-label">HELOC Opportunities</div>
                <span className="pf-opp-tag">Ready for equity access</span>
              </div>
              <div className="pf-opp-card" onClick={() => setActiveTab('opportunities')}>
                <div className="pf-opp-value">{metrics?.refinance_opportunities || computed.refiEligible.length}</div>
                <div className="pf-opp-sublabel">High-Priority Files</div>
                <div className="pf-opp-label">Refinance Opportunities</div>
                <span className="pf-opp-tag">Rate drop opportunities</span>
              </div>
            </div>
          </section>

          {/* Annual Revenue Performance */}
          <section className="pf-section">
            <h2 className="pf-section-title">Annual Revenue Performance</h2>
            <div className="pf-metrics-grid pf-grid-3">
              <MetricCard label="Per Client" value={formatCurrency(metrics?.avg_annual_revenue_per_client || computed.revenuePerClient)} />
              <MetricCard label="Referrals / yr" value="0.64" sublabel="Per Client" />
              <MetricCard label="Repeat Purchase Rate" value="21%" sublabel="5-Yr Rolling" />
            </div>
          </section>

          {/* Portfolio Health */}
          <section className="pf-section">
            <h2 className="pf-section-title">Portfolio Health</h2>
            <div className="pf-metrics-grid pf-grid-3">
              <MetricCard label="Portfolio Stability" value={`${retentionScore.score}/100`} />
              <MetricCard label="Month-to-Month Variance" value="±14%" />
              <MetricCard label="Pipeline Max Drawdown" value="-28%" sublabel="Last 12 Months" />
            </div>
          </section>

          {/* AI-Driven Suggestions */}
          <section className="pf-section">
            <h2 className="pf-section-title">AI-Driven Suggestions</h2>
            <div className="pf-ai-box">
              {aiSuggestions.map((s, i) => (
                <div key={i} className="pf-ai-item">
                  <span className="pf-ai-bullet" />
                  <span className="pf-ai-text"><strong>{s.bold}</strong> {s.text}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* ═══════════════ TAB 2: Client List ═══════════════ */}
      {activeTab === 'clients' && (
        <div className="pf-tab-content">
          <div className="pf-client-controls">
            <div className="pf-filter-pills">
              {[
                { key: 'all', label: 'All' },
                { key: 'primary', label: 'Primary' },
                { key: 'investment', label: 'Investment' },
                { key: 'va', label: 'VA' },
                { key: 'at_risk', label: 'At-Risk' },
              ].map(f => (
                <button
                  key={f.key}
                  className={clientFilter === f.key ? 'pf-pill active' : 'pf-pill'}
                  onClick={() => { setClientFilter(f.key); setCurrentPage(1); }}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="pf-search-wrap">
              <input
                type="text"
                className="pf-search"
                placeholder="Search clients..."
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              />
              {searchQuery && <button className="pf-search-clear" onClick={() => setSearchQuery('')}>&times;</button>}
            </div>
          </div>

          <div className="pf-table-wrap">
            <table className="pf-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort('client_name')}>Client{sortIcon('client_name')}</th>
                  <th onClick={() => handleSort('loan_type')}>Loan Type{sortIcon('loan_type')}</th>
                  <th onClick={() => handleSort('upb')}>UPB{sortIcon('upb')}</th>
                  <th onClick={() => handleSort('rate')}>Rate{sortIcon('rate')}</th>
                  <th onClick={() => handleSort('origination')}>Origination{sortIcon('origination')}</th>
                  <th onClick={() => handleSort('equity')}>Equity Est.{sortIcon('equity')}</th>
                  <th>Risk</th>
                  <th onClick={() => handleSort('last_contact_date')}>Last Contact{sortIcon('last_contact_date')}</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {paginatedClients.map(client => {
                  const risk = getRiskLevel(client);
                  return (
                    <tr key={client.id} onClick={() => navigate(`/portfolio/${client.id}`)} className="pf-row-clickable">
                      <td className="pf-td-client">
                        <div className="pf-client-name">{client.client_name || client.name || 'Unknown'}</div>
                        <div className="pf-client-email">{client.email || ''}</div>
                      </td>
                      <td>{client.loan_type || client.program || 'N/A'}</td>
                      <td>{formatCurrencyK(getClientUPB(client))}</td>
                      <td>{client.interest_rate ? `${client.interest_rate}%` : 'N/A'}</td>
                      <td>{client.original_close_date ? new Date(client.original_close_date).toLocaleDateString() : 'N/A'}</td>
                      <td>{client.equity_percentage ? `${client.equity_percentage}%` : (client.current_equity_estimate ? formatCurrencyK(client.current_equity_estimate) : 'N/A')}</td>
                      <td>
                        <div className={`pf-risk-bar pf-risk-${risk}`}>
                          <div className="pf-risk-fill" />
                        </div>
                        <span className={`pf-risk-label pf-risk-${risk}`}>{risk}</span>
                      </td>
                      <td>{client.last_contact_date ? new Date(client.last_contact_date).toLocaleDateString() : 'Never'}</td>
                      <td>
                        <span className={`pf-status-badge pf-status-${(client.status || 'active').replace(/\s/g, '-')}`}>
                          {client.status || 'Active'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {paginatedClients.length === 0 && (
              <div className="pf-empty">No clients match your filters.</div>
            )}
          </div>

          {totalPages > 1 && (
            <div className="pf-pagination">
              <button disabled={currentPage === 1} onClick={() => setCurrentPage(1)}>&laquo;</button>
              <button disabled={currentPage === 1} onClick={() => setCurrentPage(p => p - 1)}>&lsaquo; Prev</button>
              <span className="pf-page-info">Page {currentPage} of {totalPages} ({filteredClients.length} clients)</span>
              <button disabled={currentPage === totalPages} onClick={() => setCurrentPage(p => p + 1)}>Next &rsaquo;</button>
              <button disabled={currentPage === totalPages} onClick={() => setCurrentPage(totalPages)}>&raquo;</button>
            </div>
          )}
        </div>
      )}

      {/* ═══════════════ TAB 3: Attrition Risk ═══════════════ */}
      {activeTab === 'attrition' && (
        <div className="pf-tab-content">
          <div className="pf-attrition-top">
            {/* Donut Chart */}
            <div className="pf-donut-section">
              <h3 className="pf-section-title">Portfolio Retention Score</h3>
              <div className="pf-donut-wrap">
                <svg viewBox="0 0 120 120" className="pf-donut">
                  <circle cx="60" cy="60" r="50" fill="none" stroke="#ECE6D8" strokeWidth="12" />
                  <circle
                    cx="60" cy="60" r="50" fill="none"
                    stroke="#2D7A52" strokeWidth="12"
                    strokeDasharray={`${retentionScore.score * 3.14} 314`}
                    strokeLinecap="round"
                    transform="rotate(-90 60 60)"
                  />
                </svg>
                <div className="pf-donut-center">{retentionScore.score}%</div>
              </div>
            </div>

            {/* Score Factors */}
            <div className="pf-factors-section">
              <h3 className="pf-section-title">Score Factors</h3>
              <div className="pf-factors-list">
                <FactorBar label="Contact Frequency" value={retentionScore.contactFreq} color="#2D7A52" />
                <FactorBar label="Rate Competitiveness" value={retentionScore.rateCompetitiveness} color="#B8924A" />
                <FactorBar label="Service Satisfaction" value={retentionScore.satisfaction} color="#1F3D2E" />
                <FactorBar label="Equity Engagement" value={retentionScore.equityEngagement} color="#2D7A52" />
              </div>
            </div>
          </div>

          {/* Attrition Risk Breakdown */}
          <section className="pf-section">
            <h2 className="pf-section-title">Attrition Risk Breakdown</h2>
            <div className="pf-metrics-grid pf-grid-4">
              <MetricCard label="Low Risk" value={mumClients.filter(c => getRiskLevel(c) === 'low').length} accent />
              <MetricCard label="Medium Risk" value={mumClients.filter(c => getRiskLevel(c) === 'medium').length} />
              <MetricCard label="High Risk" value={mumClients.filter(c => getRiskLevel(c) === 'high').length} warning />
              <MetricCard label="Lost (30d)" value={metrics?.loans_lost_30d || 0} warning />
            </div>
          </section>

          {/* High-Risk Clients Table */}
          <section className="pf-section">
            <h2 className="pf-section-title">High-Risk Clients</h2>
            <div className="pf-table-wrap">
              <table className="pf-table pf-table-compact">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>Last Contact</th>
                    <th>Rate</th>
                    <th>Risk Factors</th>
                  </tr>
                </thead>
                <tbody>
                  {computed.atRiskClients.slice(0, 10).map(client => (
                    <tr key={client.id} onClick={() => navigate(`/portfolio/${client.id}`)} className="pf-row-clickable">
                      <td>{client.client_name || client.name}</td>
                      <td>{client.last_contact_date ? `${daysSince(client.last_contact_date)} days ago` : 'Never'}</td>
                      <td>{client.interest_rate ? `${client.interest_rate}%` : 'N/A'}</td>
                      <td>
                        {client.status === 'at_risk' && <span className="pf-risk-tag">Status: At Risk</span>}
                        {daysSince(client.last_contact_date) > 60 && <span className="pf-risk-tag">No Contact 60d+</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {computed.atRiskClients.length === 0 && <div className="pf-empty">No high-risk clients detected.</div>}
            </div>
          </section>

          {/* Aria's Retention Playbook */}
          <section className="pf-section">
            <h2 className="pf-section-title">Aria's Retention Playbook</h2>
            <div className="pf-ai-box">
              <div className="pf-ai-item"><span className="pf-ai-bullet" /><span className="pf-ai-text">Schedule quarterly check-ins for all clients with 60+ days since last contact</span></div>
              <div className="pf-ai-item"><span className="pf-ai-bullet" /><span className="pf-ai-text">Proactively share rate drop alerts for clients with rates above market</span></div>
              <div className="pf-ai-item"><span className="pf-ai-bullet" /><span className="pf-ai-text">Send home value appreciation reports to high-equity clients monthly</span></div>
              <div className="pf-ai-item"><span className="pf-ai-bullet" /><span className="pf-ai-text">Trigger birthday/anniversary touchpoints via automated campaigns</span></div>
              <div className="pf-ai-item"><span className="pf-ai-bullet" /><span className="pf-ai-text">Flag clients approaching PMI removal threshold for proactive outreach</span></div>
            </div>
          </section>
        </div>
      )}

      {/* ═══════════════ TAB 4: Revenue Analysis ═══════════════ */}
      {activeTab === 'revenue' && (
        <div className="pf-tab-content">
          {/* Revenue Summary */}
          <section className="pf-section">
            <h2 className="pf-section-title">Revenue Summary</h2>
            <div className="pf-metrics-grid pf-grid-4">
              <MetricCard label="Total Portfolio Revenue" value={formatCurrencyK(metrics?.total_annual_revenue || computed.totalRevenue)} sublabel="Annual" />
              <MetricCard label="Revenue Per Client" value={formatCurrency(metrics?.avg_annual_revenue_per_client || computed.revenuePerClient)} sublabel="Annual" />
              <MetricCard label="Avg Client Lifetime Value" value={formatCurrency((metrics?.avg_annual_revenue_per_client || computed.revenuePerClient) * 5)} sublabel="5-Year" />
              <MetricCard label="Referrals Generated" value={Math.round(mumClients.length * 0.64)} sublabel="Projected/yr" />
            </div>
          </section>

          {/* Monthly Revenue Trend */}
          <section className="pf-section">
            <h2 className="pf-section-title">Monthly Revenue Trend</h2>
            <div className="pf-chart-bar-container">
              {monthlyRevenue.map((m, i) => (
                <div key={i} className="pf-chart-bar-col">
                  <div className="pf-chart-bar" style={{ height: `${m.pct}%` }} />
                  <span className="pf-chart-bar-label">{m.label}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Revenue by Source */}
          <section className="pf-section">
            <h2 className="pf-section-title">Revenue by Source</h2>
            <div className="pf-metrics-grid pf-grid-3">
              <div className="pf-revenue-source">
                <div className="pf-revenue-source-bar" style={{ width: '60%', background: '#1F3D2E' }} />
                <div className="pf-revenue-source-info">
                  <span className="pf-revenue-source-label">Servicing</span>
                  <span className="pf-revenue-source-value">{formatCurrencyK(computed.totalRevenue * 0.6)}</span>
                </div>
              </div>
              <div className="pf-revenue-source">
                <div className="pf-revenue-source-bar" style={{ width: '25%', background: '#B8924A' }} />
                <div className="pf-revenue-source-info">
                  <span className="pf-revenue-source-label">Referral</span>
                  <span className="pf-revenue-source-value">{formatCurrencyK(computed.totalRevenue * 0.25)}</span>
                </div>
              </div>
              <div className="pf-revenue-source">
                <div className="pf-revenue-source-bar" style={{ width: '15%', background: '#2D7A52' }} />
                <div className="pf-revenue-source-info">
                  <span className="pf-revenue-source-label">Repeat Business</span>
                  <span className="pf-revenue-source-value">{formatCurrencyK(computed.totalRevenue * 0.15)}</span>
                </div>
              </div>
            </div>
          </section>

          {/* Top Revenue Clients */}
          <section className="pf-section">
            <h2 className="pf-section-title">Top Revenue Clients</h2>
            <div className="pf-table-wrap">
              <table className="pf-table pf-table-compact">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>UPB</th>
                    <th>Est. Annual Revenue</th>
                    <th>Rate</th>
                    <th>Loan Type</th>
                  </tr>
                </thead>
                <tbody>
                  {topRevenueClients.map(client => (
                    <tr key={client.id} onClick={() => navigate(`/portfolio/${client.id}`)} className="pf-row-clickable">
                      <td>{client.client_name || client.name}</td>
                      <td>{formatCurrencyK(getClientUPB(client))}</td>
                      <td className="pf-td-revenue">{formatCurrency(client.estimatedRevenue)}</td>
                      <td>{client.interest_rate ? `${client.interest_rate}%` : 'N/A'}</td>
                      <td>{client.loan_type || client.program || 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {/* ═══════════════ TAB 5: Opportunities ═══════════════ */}
      {activeTab === 'opportunities' && (
        <div className="pf-tab-content">
          {/* Opportunity Pipeline */}
          <section className="pf-section">
            <h2 className="pf-section-title">Opportunity Pipeline</h2>
            <div className="pf-metrics-grid pf-grid-3">
              <OppActionCard
                title="Rate Rebound"
                count={computed.rateReboundEligible.length}
                desc="Clients with high rates ready to refinance when market drops"
                color="#2D7A52"
              />
              <OppActionCard
                title="HELOC / Cash-Out"
                count={computed.helocEligible.length}
                desc="Clients with 20%+ equity eligible for home equity products"
                color="#B8924A"
              />
              <OppActionCard
                title="Purchase-Next"
                count={mumClients.filter(c => c.equity_percentage && c.equity_percentage > 40).length}
                desc="High equity clients likely considering investment property"
                color="#1F3D2E"
              />
              <OppActionCard
                title="Approaching Events"
                count={mumClients.filter(c => { const d = daysSince(c.original_close_date); return d && d > 300 && d < 400; }).length}
                desc="Clients nearing loan anniversary or key mortgage milestones"
                color="#B25F18"
              />
              <OppActionCard
                title="Referral Activation"
                count={mumClients.filter(c => { const d = daysSince(c.last_contact_date); return d !== null && d <= 30; }).length}
                desc="Recently engaged clients most likely to provide referrals"
                color="#2D7A52"
              />
              <OppActionCard
                title="PMI Removal"
                count={mumClients.filter(c => c.equity_percentage && c.equity_percentage >= 20 && c.equity_percentage < 25).length}
                desc="Clients crossing 20% equity threshold — eligible for PMI drop"
                color="#9B2C2C"
              />
            </div>
          </section>

          {/* Client Segments by Property Type */}
          <section className="pf-section">
            <h2 className="pf-section-title">Client Segments by Property Type</h2>
            <div className="pf-metrics-grid pf-grid-4">
              <SegmentCard label="Primary Residence" count={computed.segments.primary} total={mumClients.length} />
              <SegmentCard label="Second Home" count={computed.segments.second_home} total={mumClients.length} />
              <SegmentCard label="Investment" count={computed.segments.investment} total={mumClients.length} />
              <SegmentCard label="New Construction" count={computed.segments.new_construction} total={mumClients.length} />
            </div>
          </section>

          {/* Client Segments by Loan Type */}
          <section className="pf-section">
            <h2 className="pf-section-title">Client Segments by Loan Type</h2>
            <div className="pf-metrics-grid pf-grid-6">
              <SegmentCard label="Conventional" count={computed.loanTypeSegments.conventional} total={mumClients.length} />
              <SegmentCard label="FHA" count={computed.loanTypeSegments.fha} total={mumClients.length} />
              <SegmentCard label="VA" count={computed.loanTypeSegments.va} total={mumClients.length} />
              <SegmentCard label="USDA" count={computed.loanTypeSegments.usda} total={mumClients.length} />
              <SegmentCard label="N/O" count={computed.loanTypeSegments.other} total={mumClients.length} />
              <SegmentCard label="First Time Buyers" count={computed.loanTypeSegments.first_time} total={mumClients.length} />
            </div>
          </section>

          {/* Rate Rebound Eligible Clients */}
          <section className="pf-section">
            <h2 className="pf-section-title">Rate Rebound Eligible Clients</h2>
            <div className="pf-table-wrap">
              <table className="pf-table pf-table-compact">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>Current Rate</th>
                    <th>UPB</th>
                    <th>Origination</th>
                    <th>Potential Savings</th>
                  </tr>
                </thead>
                <tbody>
                  {computed.rateReboundEligible.slice(0, 10).map(client => {
                    const savings = client.interest_rate && client.interest_rate > 5.5
                      ? Math.round(getClientUPB(client) * (client.interest_rate - 5.5) / 100)
                      : 0;
                    return (
                      <tr key={client.id} onClick={() => navigate(`/portfolio/${client.id}`)} className="pf-row-clickable">
                        <td>{client.client_name || client.name}</td>
                        <td className="pf-td-rate-high">{client.interest_rate}%</td>
                        <td>{formatCurrencyK(getClientUPB(client))}</td>
                        <td>{client.original_close_date ? new Date(client.original_close_date).toLocaleDateString() : 'N/A'}</td>
                        <td className="pf-td-savings">{savings > 0 ? `${formatCurrency(savings)}/yr` : '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {computed.rateReboundEligible.length === 0 && <div className="pf-empty">No rate rebound candidates found.</div>}
            </div>
          </section>

          {/* HELOC/Cash-Out Top Equity */}
          <section className="pf-section">
            <h2 className="pf-section-title">HELOC/Cash-Out — Top Equity Clients</h2>
            <div className="pf-table-wrap">
              <table className="pf-table pf-table-compact">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>Equity %</th>
                    <th>Est. Equity</th>
                    <th>Property Value</th>
                    <th>Current Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {computed.helocEligible
                    .sort((a, b) => (b.equity_percentage || 0) - (a.equity_percentage || 0))
                    .slice(0, 10)
                    .map(client => (
                      <tr key={client.id} onClick={() => navigate(`/portfolio/${client.id}`)} className="pf-row-clickable">
                        <td>{client.client_name || client.name}</td>
                        <td className="pf-td-equity-high">{client.equity_percentage || 0}%</td>
                        <td>{formatCurrencyK(client.current_equity_estimate || 0)}</td>
                        <td>{formatCurrencyK(client.current_property_value || client.appraisal_value_at_closing || 0)}</td>
                        <td>{formatCurrencyK(getClientUPB(client))}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {computed.helocEligible.length === 0 && <div className="pf-empty">No HELOC candidates found.</div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

// ─── Sub-Components ──────────────────────────────────────────────────────────

function MetricCard({ label, value, sublabel, accent, warning }) {
  let cls = 'pf-metric-card';
  if (accent) cls += ' pf-metric-accent';
  if (warning) cls += ' pf-metric-warning';
  return (
    <div className={cls}>
      <div className="pf-metric-value">{value}</div>
      {sublabel && <div className="pf-metric-sublabel">{sublabel}</div>}
      <div className="pf-metric-label">{label}</div>
    </div>
  );
}

function OppActionCard({ title, count, desc, color }) {
  return (
    <div className="pf-opp-action-card" style={{ borderTopColor: color }}>
      <div className="pf-opp-action-count" style={{ color }}>{count}</div>
      <div className="pf-opp-action-title">{title}</div>
      <div className="pf-opp-action-desc">{desc}</div>
    </div>
  );
}

function SegmentCard({ label, count, total }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="pf-segment-card">
      <div className="pf-segment-value">{pct}%</div>
      <div className="pf-segment-count">{count} clients</div>
      <div className="pf-segment-label">{label}</div>
    </div>
  );
}

function FactorBar({ label, value, color }) {
  return (
    <div className="pf-factor">
      <div className="pf-factor-header">
        <span className="pf-factor-label">{label}</span>
        <span className="pf-factor-value">{value}%</span>
      </div>
      <div className="pf-factor-track">
        <div className="pf-factor-fill" style={{ width: `${value}%`, background: color }} />
      </div>
    </div>
  );
}

export default Portfolio;
