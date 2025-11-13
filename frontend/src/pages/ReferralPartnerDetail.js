import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { partnersAPI, leadsAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import './ReferralPartnerDetail.css';

function ReferralPartnerDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [partner, setPartner] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [searchCategory, setSearchCategory] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [allLeads, setAllLeads] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');

  // ROI Calculator states
  const [monthlyMarketingSpend, setMonthlyMarketingSpend] = useState(() => {
    const saved = localStorage.getItem(`partner_${id}_marketing_spend`);
    return saved ? parseFloat(saved) : 500;
  });
  const [avgCommission, setAvgCommission] = useState(() => {
    const saved = localStorage.getItem(`partner_${id}_avg_commission`);
    return saved ? parseFloat(saved) : 4000;
  });

  useEffect(() => {
    loadPartnerData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadPartnerData = async () => {
    try {
      setLoading(true);
      const [partnerData, allLeadsData] = await Promise.all([
        partnersAPI.getById(id),
        leadsAPI.getAll()
      ]);

      setPartner(partnerData);
      setAllLeads(allLeadsData);

      // Filter leads that were referred by this partner
      const partnerReferrals = allLeadsData.filter(lead =>
        lead.referral_partner_id === parseInt(id) ||
        lead.source?.toLowerCase().includes(partnerData.name?.toLowerCase())
      );

      setReferrals(partnerReferrals);
    } catch (error) {
      console.error('Failed to load partner data:', error);
      alert('Failed to load referral partner details');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenSearch = (category) => {
    setSearchCategory(category);
    setSearchQuery('');
    setSearchResults([]);
    setShowSearchModal(true);
  };

  const handleSearchChange = (e) => {
    const query = e.target.value;
    setSearchQuery(query);

    if (query.trim() === '') {
      setSearchResults([]);
      return;
    }

    // Filter leads that:
    // 1. Are not already assigned to this partner
    // 2. Match the search query
    const filtered = allLeads.filter(lead => {
      const isNotAssigned = lead.referral_partner_id !== parseInt(id);
      const matchesQuery = lead.name?.toLowerCase().includes(query.toLowerCase());
      return isNotAssigned && matchesQuery;
    });

    setSearchResults(filtered);
  };

  const handleAssignLead = async (lead) => {
    const categoryNames = {
      leads: 'Leads',
      active: 'Active Clients',
      closed: 'Closed Clients',
      nurtured: 'Nurtured Clients',
      disqualified: 'Do Not Qualify'
    };

    // Map category to appropriate stage
    const categoryToStageMap = {
      leads: 'New',
      active: 'Application',
      closed: 'Completed',
      nurtured: 'Prospect',
      disqualified: 'Does Not Qualify'
    };

    const confirmed = window.confirm(
      `Add ${lead.name} to ${partner.name}'s ${categoryNames[searchCategory]}?`
    );

    if (!confirmed) return;

    try {
      // Update the lead with the referral partner ID AND stage
      await leadsAPI.update(lead.id, {
        referral_partner_id: parseInt(id),
        stage: categoryToStageMap[searchCategory]
      });

      // Close modal and refresh data
      setShowSearchModal(false);
      setSearchQuery('');
      setSearchResults([]);

      // Reload partner data to show the newly assigned lead
      await loadPartnerData();

      alert(`${lead.name} has been added to ${partner.name}'s ${categoryNames[searchCategory]}!`);
    } catch (error) {
      console.error('Failed to assign lead:', error);
      alert('Failed to assign lead to partner. Please try again.');
    }
  };

  const categorizeReferrals = () => {
    const categories = {
      leads: referrals.filter(r => ['New', 'Attempted Contact', 'Prospect'].includes(r.stage)),
      active: referrals.filter(r => ['Application', 'Pre-Qualified', 'Pre-Approved'].includes(r.stage)),
      closed: referrals.filter(r => r.stage === 'Completed'),
      nurtured: referrals.filter(r => r.stage === 'Prospect'),
      disqualified: referrals.filter(r => ['Withdrawn', 'Does Not Qualify'].includes(r.stage))
    };
    return categories;
  };

  // ROI Calculator Functions
  const handleMarketingSpendChange = (value) => {
    setMonthlyMarketingSpend(value);
    localStorage.setItem(`partner_${id}_marketing_spend`, value);
  };

  const handleCommissionChange = (value) => {
    setAvgCommission(value);
    localStorage.setItem(`partner_${id}_avg_commission`, value);
  };

  const calculateROIMetrics = () => {
    const categories = categorizeReferrals();
    const closedLoans = categories.closed.length;
    const totalLeads = referrals.length;
    const annualMarketingSpend = monthlyMarketingSpend * 12;

    // Calculate conversion rate
    const conversionRate = totalLeads > 0 ? (closedLoans / totalLeads) * 100 : 0;

    // Calculate revenue
    const totalRevenue = closedLoans * avgCommission;

    // Calculate ROI
    const roi = annualMarketingSpend > 0 ? ((totalRevenue - annualMarketingSpend) / annualMarketingSpend) * 100 : 0;

    // Cost per closed loan
    const costPerLoan = closedLoans > 0 ? annualMarketingSpend / closedLoans : 0;

    // Annual profit
    const annualProfit = totalRevenue - annualMarketingSpend;

    return {
      closedLoans,
      totalLeads,
      conversionRate: conversionRate.toFixed(1),
      costPerLoan: Math.round(costPerLoan),
      annualROI: Math.round(roi),
      annualProfit: Math.round(annualProfit),
      totalRevenue: Math.round(totalRevenue),
      annualSpend: Math.round(annualMarketingSpend)
    };
  };

  const getROIStatus = (roi) => {
    if (roi >= 300) return { label: 'Excellent', color: '#10b981' };
    if (roi >= 150) return { label: 'Strong', color: '#3b82f6' };
    if (roi >= 50) return { label: 'Good', color: '#f59e0b' };
    return { label: 'Needs Improvement', color: '#ef4444' };
  };

  const getTierBadgeClass = (tier) => {
    const tierMap = {
      gold: 'tier-gold',
      silver: 'tier-silver',
      bronze: 'tier-bronze',
    };
    return tierMap[tier?.toLowerCase()] || 'tier-bronze';
  };

  const handleLeadClick = (leadId) => {
    navigate(`/leads/${leadId}`);
  };

  if (loading) {
    return (
      <div className="partner-detail-container">
        <div className="loading">Loading partner details...</div>
      </div>
    );
  }

  if (!partner) {
    return (
      <div className="partner-detail-container">
        <div className="error">Partner not found</div>
      </div>
    );
  }

  const categories = categorizeReferrals();

  return (
    <div className="partner-detail-container">
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/referral-partners')}>
          ← Back to Partners
        </button>
        <div className="partner-title-section">
          <h1>{partner.name}</h1>
          <span className={`tier-badge ${getTierBadgeClass(partner.loyalty_tier)}`}>
            {partner.loyalty_tier || 'Bronze'}
          </span>
        </div>
      </div>

      {/* Partner Info */}
      <div className="partner-info-card">
        <div className="info-grid">
          <div className="info-item">
            <span className="label">Company</span>
            <span className="value">{partner.company || 'N/A'}</span>
          </div>
          <div className="info-item">
            <span className="label">Type</span>
            <span className="value">{partner.type || 'N/A'}</span>
          </div>
          <div className="info-item">
            <span className="label">Email</span>
            <span className="value"><ClickableEmail email={partner.email} /></span>
          </div>
          <div className="info-item">
            <span className="label">Phone</span>
            <span className="value"><ClickablePhone phone={partner.phone} /></span>
          </div>
        </div>

        <div className="stats-row">
          <div className="stat-box">
            <div className="stat-value">{referrals.length}</div>
            <div className="stat-label">Total Referrals</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{categories.active.length}</div>
            <div className="stat-label">Active Clients</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{categories.closed.length}</div>
            <div className="stat-label">Closed Loans</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">
              {referrals.length > 0
                ? ((categories.closed.length / referrals.length) * 100).toFixed(1)
                : '0.0'}%
            </div>
            <div className="stat-label">Conversion Rate</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">
              ${((partner.volume || 0) / 1000000).toFixed(1)}M
            </div>
            <div className="stat-label">Total Volume</div>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="partner-tabs">
        <button
          className={`partner-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`partner-tab ${activeTab === 'roi' ? 'active' : ''}`}
          onClick={() => setActiveTab('roi')}
        >
          💰 ROI Calculator
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <>
          {/* Referrals by Status */}
          <div className="referrals-section">
        <h2>Referrals by Status</h2>

        {/* Leads */}
        <div className="status-category">
          <div className="category-header">
            <h3>Leads ({categories.leads.length})</h3>
            <div className="category-header-actions">
              <span className="count-badge">{categories.leads.length}</span>
              <button
                className="btn-add-to-category"
                onClick={() => handleOpenSearch('leads')}
                title="Add lead to this category"
              >
                +
              </button>
            </div>
          </div>
          {categories.leads.length > 0 ? (
            <div className="referrals-list">
              {categories.leads.map((lead) => (
                <div
                  key={lead.id}
                  className="referral-item"
                  onClick={() => handleLeadClick(lead.id)}
                >
                  <div className="referral-name">{lead.name}</div>
                  <div className="referral-details">
                    <span>{lead.email || 'No email'}</span>
                    <span className="separator">•</span>
                    <span className={`status-badge status-${lead.stage.toLowerCase().replace(/\s+/g, '-')}`}>
                      {lead.stage}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-category">No leads in this category</div>
          )}
        </div>

        {/* Active Clients */}
        <div className="status-category">
          <div className="category-header">
            <h3>Active Clients ({categories.active.length})</h3>
            <div className="category-header-actions">
              <span className="count-badge">{categories.active.length}</span>
              <button
                className="btn-add-to-category"
                onClick={() => handleOpenSearch('active')}
                title="Add lead to this category"
              >
                +
              </button>
            </div>
          </div>
          {categories.active.length > 0 ? (
            <div className="referrals-list">
              {categories.active.map((lead) => (
                <div
                  key={lead.id}
                  className="referral-item"
                  onClick={() => handleLeadClick(lead.id)}
                >
                  <div className="referral-name">{lead.name}</div>
                  <div className="referral-details">
                    <span>{lead.email || 'No email'}</span>
                    <span className="separator">•</span>
                    <span className={`status-badge status-${lead.stage.toLowerCase().replace(/\s+/g, '-')}`}>
                      {lead.stage}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-category">No active clients in this category</div>
          )}
        </div>

        {/* Closed Clients */}
        <div className="status-category">
          <div className="category-header">
            <h3>Closed Clients ({categories.closed.length})</h3>
            <div className="category-header-actions">
              <span className="count-badge">{categories.closed.length}</span>
              <button
                className="btn-add-to-category"
                onClick={() => handleOpenSearch('closed')}
                title="Add lead to this category"
              >
                +
              </button>
            </div>
          </div>
          {categories.closed.length > 0 ? (
            <div className="referrals-list">
              {categories.closed.map((lead) => (
                <div
                  key={lead.id}
                  className="referral-item"
                  onClick={() => handleLeadClick(lead.id)}
                >
                  <div className="referral-name">{lead.name}</div>
                  <div className="referral-details">
                    <span>{lead.email || 'No email'}</span>
                    <span className="separator">•</span>
                    <span className={`status-badge status-${lead.stage.toLowerCase().replace(/\s+/g, '-')}`}>
                      {lead.stage}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-category">No closed clients in this category</div>
          )}
        </div>

        {/* Nurtured Clients */}
        <div className="status-category">
          <div className="category-header">
            <h3>Nurtured Clients ({categories.nurtured.length})</h3>
            <div className="category-header-actions">
              <span className="count-badge">{categories.nurtured.length}</span>
              <button
                className="btn-add-to-category"
                onClick={() => handleOpenSearch('nurtured')}
                title="Add lead to this category"
              >
                +
              </button>
            </div>
          </div>
          {categories.nurtured.length > 0 ? (
            <div className="referrals-list">
              {categories.nurtured.map((lead) => (
                <div
                  key={lead.id}
                  className="referral-item"
                  onClick={() => handleLeadClick(lead.id)}
                >
                  <div className="referral-name">{lead.name}</div>
                  <div className="referral-details">
                    <span>{lead.email || 'No email'}</span>
                    <span className="separator">•</span>
                    <span className={`status-badge status-${lead.stage.toLowerCase().replace(/\s+/g, '-')}`}>
                      {lead.stage}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-category">No nurtured clients in this category</div>
          )}
        </div>

        {/* Do Not Qualify */}
        <div className="status-category">
          <div className="category-header">
            <h3>Do Not Qualify ({categories.disqualified.length})</h3>
            <div className="category-header-actions">
              <span className="count-badge">{categories.disqualified.length}</span>
              <button
                className="btn-add-to-category"
                onClick={() => handleOpenSearch('disqualified')}
                title="Add lead to this category"
              >
                +
              </button>
            </div>
          </div>
          {categories.disqualified.length > 0 ? (
            <div className="referrals-list">
              {categories.disqualified.map((lead) => (
                <div
                  key={lead.id}
                  className="referral-item"
                  onClick={() => handleLeadClick(lead.id)}
                >
                  <div className="referral-name">{lead.name}</div>
                  <div className="referral-details">
                    <span>{lead.email || 'No email'}</span>
                    <span className="separator">•</span>
                    <span className={`status-badge status-${lead.stage.toLowerCase().replace(/\s+/g, '-')}`}>
                      {lead.stage}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-category">No disqualified clients in this category</div>
          )}
        </div>
      </div>
        </>
      )}

      {/* ROI Calculator Tab */}
      {activeTab === 'roi' && (
        <div className="roi-calculator-section">
          <div className="roi-header">
            <h2>Partnership Profitability Calculator</h2>
            <p>Track your marketing investment and measure ROI from this referral partnership</p>
          </div>

          <div className="roi-calculator-grid">
            {/* Configuration Panel */}
            <div className="roi-config-panel">
              <h3>Configuration</h3>

              {/* Monthly Marketing Spend */}
              <div className="roi-input-group">
                <label className="roi-label">
                  Monthly Marketing Contribution
                  <span className="info-tooltip" title="Amount you contribute monthly to partner's marketing">ⓘ</span>
                </label>
                <div className="input-with-slider">
                  <input
                    type="number"
                    className="roi-input"
                    value={monthlyMarketingSpend}
                    onChange={(e) => handleMarketingSpendChange(parseFloat(e.target.value) || 0)}
                    min="0"
                    step="100"
                  />
                  <input
                    type="range"
                    className="roi-slider"
                    value={monthlyMarketingSpend}
                    onChange={(e) => handleMarketingSpendChange(parseFloat(e.target.value))}
                    min="0"
                    max="10000"
                    step="100"
                  />
                  <div className="slider-labels">
                    <span>$0</span>
                    <span>$10,000</span>
                  </div>
                </div>
              </div>

              {/* Average Commission */}
              <div className="roi-input-group">
                <label className="roi-label">
                  Average Commission Per Loan
                  <span className="info-tooltip" title="Your average commission per closed loan">ⓘ</span>
                </label>
                <div className="input-with-slider">
                  <input
                    type="number"
                    className="roi-input"
                    value={avgCommission}
                    onChange={(e) => handleCommissionChange(parseFloat(e.target.value) || 0)}
                    min="0"
                    step="100"
                  />
                  <input
                    type="range"
                    className="roi-slider"
                    value={avgCommission}
                    onChange={(e) => handleCommissionChange(parseFloat(e.target.value))}
                    min="1000"
                    max="15000"
                    step="100"
                  />
                  <div className="slider-labels">
                    <span>$1,000</span>
                    <span>$15,000</span>
                  </div>
                </div>
              </div>

              {/* Live Data Indicator */}
              <div className="live-data-indicator">
                <span className="live-dot"></span>
                <span className="live-text">Using live data from closed clients</span>
              </div>
            </div>

            {/* Results Panel */}
            <div className="roi-results-panel">
              <h3>Performance Results</h3>

              {(() => {
                const metrics = calculateROIMetrics();
                const roiStatus = getROIStatus(metrics.annualROI);

                return (
                  <>
                    {/* Cost Per Funded Loan */}
                    <div className="roi-metric-large">
                      <div className="metric-label">COST PER FUNDED LOAN</div>
                      <div className="metric-value-big" style={{ color: '#10b981' }}>
                        ${metrics.costPerLoan.toLocaleString()}
                      </div>
                      <div className="metric-status" style={{ color: roiStatus.color }}>
                        {roiStatus.label}
                      </div>
                    </div>

                    {/* Key Metrics Grid */}
                    <div className="roi-metrics-grid">
                      <div className="roi-metric-box">
                        <div className="metric-label-small">Annual Leads</div>
                        <div className="metric-value-medium">{metrics.totalLeads}</div>
                        <div className="metric-sublabel">Generated</div>
                      </div>
                      <div className="roi-metric-box">
                        <div className="metric-label-small">Annual Loans</div>
                        <div className="metric-value-medium">{metrics.closedLoans}</div>
                        <div className="metric-sublabel">Closed</div>
                      </div>
                      <div className="roi-metric-box">
                        <div className="metric-label-small">Conversion Rate</div>
                        <div className="metric-value-medium">{metrics.conversionRate}%</div>
                        <div className="metric-sublabel">Lead to Close</div>
                      </div>
                    </div>

                    {/* ROI and Profit */}
                    <div className="roi-bottom-metrics">
                      <div className="roi-metric-box-large">
                        <div className="metric-label-small">Annual ROI</div>
                        <div className="metric-value-huge" style={{ color: '#10b981' }}>
                          +{metrics.annualROI}%
                        </div>
                        <div className="metric-sublabel" style={{ color: roiStatus.color }}>
                          {roiStatus.label} returns
                        </div>
                      </div>
                      <div className="roi-metric-box-large">
                        <div className="metric-label-small">Annual Profit</div>
                        <div className="metric-value-huge" style={{ color: '#10b981' }}>
                          +${metrics.annualProfit.toLocaleString()}
                        </div>
                        <div className="metric-sublabel">Annual profit</div>
                      </div>
                    </div>

                    {/* Additional Info */}
                    <div className="roi-info-boxes">
                      <div className="roi-info-item">
                        <span className="info-label">Annual Marketing Spend:</span>
                        <span className="info-value">${metrics.annualSpend.toLocaleString()}</span>
                      </div>
                      <div className="roi-info-item">
                        <span className="info-label">Total Revenue Generated:</span>
                        <span className="info-value">${metrics.totalRevenue.toLocaleString()}</span>
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Search Modal */}
      {showSearchModal && (
        <div className="search-modal-overlay" onClick={() => setShowSearchModal(false)}>
          <div className="search-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="search-modal-header">
              <h3>Add Lead to {partner.name}</h3>
              <button
                className="btn-close-modal"
                onClick={() => setShowSearchModal(false)}
              >
                ×
              </button>
            </div>
            <div className="search-modal-body">
              <input
                type="text"
                className="search-input"
                placeholder="Search for a lead by name..."
                value={searchQuery}
                onChange={handleSearchChange}
                autoFocus
              />
              <div className="search-results">
                {searchQuery.trim() === '' ? (
                  <div className="search-hint">Start typing to search for leads...</div>
                ) : searchResults.length > 0 ? (
                  searchResults.map((lead) => (
                    <div
                      key={lead.id}
                      className="search-result-item"
                      onClick={() => handleAssignLead(lead)}
                    >
                      <div className="result-name">{lead.name}</div>
                      <div className="result-details">
                        <span>{lead.email || 'No email'}</span>
                        <span className="separator">•</span>
                        <span className={`status-badge status-${lead.stage?.toLowerCase().replace(/\s+/g, '-')}`}>
                          {lead.stage}
                        </span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="no-results">No leads found matching "{searchQuery}"</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ReferralPartnerDetail;
