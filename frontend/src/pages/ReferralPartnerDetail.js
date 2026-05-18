import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { partnersAPI, leadsAPI, builderApplicationsAPI } from '../services/api';
import { ClickableEmail, ClickablePhone } from '../components/ClickableContact';
import SMSAccordionPanel from '../components/sms/SMSAccordionPanel';
import './ReferralPartnerDetail.css';
import { toast } from '../utils/toast';


// Partner type options
const PARTNER_TYPES = [
  'Realtor',
  'Real Estate Agent',
  'Broker',
  'Insurance Agent',
  'Financial Advisor',
  'CPA',
  'Attorney',
  'Builder',
  'Title Company',
  'Other',
];

// Tier options
const TIER_OPTIONS = ['Bronze', 'Silver', 'Gold', 'Platinum'];

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

  // Edit modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);

  // Builder application state
  const [builderApps, setBuilderApps] = useState([]);
  const [selectedApp, setSelectedApp] = useState(null);
  const [loadingApp, setLoadingApp] = useState(false);
  const [rejectAppId, setRejectAppId] = useState(null);
  const [rejectNotes, setRejectNotes] = useState('');

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
      let partnerData = null;
      let allLeadsData = [];

      // Fetch partner and leads independently so one failure doesn't block the other
      try {
        partnerData = await partnersAPI.getById(id);
      } catch (partnerError) {
        console.error('Partner API error:', partnerError);
        const is404 = partnerError?.response?.status === 404;
        if (is404) {
          toast.error('Referral partner not found. This partner may have been deleted or the ID is incorrect.');
        } else {
          toast.error('Failed to load referral partner details');
        }
        navigate('/referral-partners');
        return;
      }

      try {
        allLeadsData = await leadsAPI.getAll();
      } catch (leadsError) {
        console.error('Leads API error (non-blocking):', leadsError);
        allLeadsData = [];
      }

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
      toast.error('Failed to load referral partner details');
      navigate('/referral-partners');
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

      toast.success(`${lead.name} has been added to ${partner.name}'s ${categoryNames[searchCategory]}!`);
    } catch (error) {
      console.error('Failed to assign lead:', error);
      toast.error('Failed to assign lead to partner. Please try again.');
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
    if (roi >= 300) return { label: 'Excellent', color: '#2D7A52' };
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
    // Navigate to partner portal client view
    navigate(`/partner-portal/${id}/client/${leadId}`);
  };

  // Edit partner functions
  const handleOpenEdit = () => {
    // Split name into first and last name
    const nameParts = (partner.name || '').trim().split(' ');
    const firstName = nameParts[0] || '';
    const lastName = nameParts.slice(1).join(' ') || '';

    setEditForm({
      first_name: firstName,
      last_name: lastName,
      company: partner.company || '',
      email: partner.email || '',
      phone: partner.phone || '',
      type: partner.type || '',
      title: partner.title || '',
      loyalty_tier: partner.loyalty_tier || 'Bronze',
      address: partner.address || '',
      city: partner.city || '',
      state: partner.state || '',
      zip: partner.zip || '',
      notes: partner.notes || '',
    });
    setShowEditModal(true);
  };

  const handleEditFormChange = (field, value) => {
    setEditForm(prev => ({ ...prev, [field]: value }));
  };

  const handleSavePartner = async () => {
    try {
      setSaving(true);
      // Combine first_name and last_name into name for the backend
      const dataToSave = {
        ...editForm,
        name: `${editForm.first_name} ${editForm.last_name}`.trim(),
      };
      delete dataToSave.first_name;
      delete dataToSave.last_name;

      await partnersAPI.update(id, dataToSave);
      setPartner(prev => ({ ...prev, ...dataToSave }));
      setShowEditModal(false);
      toast.success('Partner profile updated successfully!');
    } catch (error) {
      console.error('Failed to save partner:', error);
      toast.error('Failed to save partner. Please try again.');
    } finally {
      setSaving(false);
    }
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
  const isBuilder = partner?.type === 'Builder' || partner?.category === 'builder';

  return (
    <div className="partner-detail-container">
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/referral-partners')}>
          ← Back to Partners
        </button>
        <div className="partner-title-section">
          <button
            className="btn-view-portal"
            onClick={() => navigate(`/partner-portal/${id}`)}
            title="View as partner"
          >
            👁 View Portal
          </button>
          {isBuilder && (
            <button
              className="btn-builder-docs-portal"
              onClick={() => navigate(`/partner-portal/${id}?tab=clients`)}
              title="Open builder docs portal"
            >
              📄 Builder Docs Portal
            </button>
          )}
          <h1>{partner.name}</h1>
          <span className={`tier-badge ${getTierBadgeClass(partner.loyalty_tier)}`}>
            {partner.loyalty_tier || 'Bronze'}
          </span>
        </div>
      </div>

      {/* Partner Info */}
      <div className="partner-info-card">
        <div className="info-card-header">
          <h3>Partner Information</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            {isBuilder && (
              <button
                className="btn-builder-portal"
                onClick={() => {
                  const portalUrl = `${window.location.origin}/builder-portal?partner_id=${id}`;
                  navigator.clipboard.writeText(portalUrl).then(() => toast.success('Builder docs portal link copied to clipboard'));
                }}
                title="Copy builder docs portal link"
              >
                📋 Copy Docs Portal Link
              </button>
            )}
            <button className="btn-edit-partner" onClick={handleOpenEdit}>
              Edit Profile
            </button>
          </div>
        </div>
        <div className="info-grid">
          <div className="info-item">
            <span className="label">Company</span>
            <span className="value">{partner.company || partner.business_name || 'N/A'}</span>
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
          {partner.title && (
            <div className="info-item">
              <span className="label">Title</span>
              <span className="value">{partner.title}</span>
            </div>
          )}
          {partner.contact_name && partner.contact_name !== partner.name && (
            <div className="info-item">
              <span className="label">Contact</span>
              <span className="value">{partner.contact_name}</span>
            </div>
          )}
          {(partner.street_address || partner.city) && (
            <div className="info-item" style={{ gridColumn: 'span 2' }}>
              <span className="label">Address</span>
              <span className="value">
                {[partner.street_address, partner.city, partner.state, partner.zip_code].filter(Boolean).join(', ')}
              </span>
            </div>
          )}
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
        {isBuilder && (
          <button
            className={`partner-tab ${activeTab === 'builderapp' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('builderapp');
              if (builderApps.length === 0 && !loadingApp) {
                setLoadingApp(true);
                builderApplicationsAPI.list({ partner_id: partner.id }).then(apps => {
                  setBuilderApps(apps || []);
                }).catch(() => toast.error('Failed to load builder applications')).finally(() => setLoadingApp(false));
              }
            }}
          >
            Builder Application
          </button>
        )}
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
                      <div className="metric-value-big" style={{ color: '#2D7A52' }}>
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
                        <div className="metric-value-huge" style={{ color: '#2D7A52' }}>
                          +{metrics.annualROI}%
                        </div>
                        <div className="metric-sublabel" style={{ color: roiStatus.color }}>
                          {roiStatus.label} returns
                        </div>
                      </div>
                      <div className="roi-metric-box-large">
                        <div className="metric-label-small">Annual Profit</div>
                        <div className="metric-value-huge" style={{ color: '#2D7A52' }}>
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

      {/* Builder Application Tab */}
      {activeTab === 'builderapp' && (
        <div className="referrals-section">
          <h2>Builder Applications</h2>
          {loadingApp && <p style={{ color: 'var(--text-muted)', padding: '16px 0' }}>Loading applications...</p>}
          {!loadingApp && builderApps.length === 0 && (
            <p style={{ color: 'var(--text-muted)', padding: '16px 0' }}>No builder applications found for this partner.</p>
          )}
          {builderApps.map(app => (
            <div key={app.id} style={{
              border: '1px solid var(--border)', borderRadius: 8, padding: 16, marginBottom: 12,
              background: 'var(--bg-card)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <strong>{app.company_name}</strong>
                <span style={{
                  fontSize: 11, fontWeight: 600, padding: '2px 10px', borderRadius: 12,
                  background: app.status === 'APPROVED' ? '#d4edda' : app.status === 'REJECTED' ? '#f8d7da' : app.status === 'SUBMITTED' ? '#fff3cd' : '#e2e3e5',
                  color: app.status === 'APPROVED' ? '#155724' : app.status === 'REJECTED' ? '#721c24' : app.status === 'SUBMITTED' ? '#856404' : '#383d41',
                }}>{app.status}</span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                {app.contact_name} &middot; {app.contact_email} &middot; {app.doc_count} docs
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                Submitted: {app.submitted_at ? new Date(app.submitted_at).toLocaleDateString() : 'Draft'}
              </div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <button
                  className="btn-sm"
                  style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-card)', cursor: 'pointer' }}
                  onClick={async () => {
                    try {
                      setLoadingApp(true);
                      const detail = await builderApplicationsAPI.getById(app.id);
                      setSelectedApp(detail);
                    } catch { toast.error('Failed to load application'); }
                    finally { setLoadingApp(false); }
                  }}
                >View Details</button>
                {(app.status === 'SUBMITTED' || app.status === 'UNDER_REVIEW') && (
                  <>
                    <button
                      style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, border: 'none', background: '#27ae60', color: '#fff', cursor: 'pointer' }}
                      onClick={async () => {
                        try {
                          await builderApplicationsAPI.review(app.id, { action: 'approve' });
                          toast.success('Application approved');
                          setBuilderApps(prev => prev.map(a => a.id === app.id ? { ...a, status: 'APPROVED' } : a));
                        } catch { toast.error('Failed to approve'); }
                      }}
                    >Approve</button>
                    <button
                      style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, border: 'none', background: '#e74c3c', color: '#fff', cursor: 'pointer' }}
                      onClick={() => setRejectAppId(app.id)}
                    >Reject</button>
                  </>
                )}
              </div>
            </div>
          ))}

          {rejectAppId && (
            <div style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 1001,
              display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
            }} onClick={() => { setRejectAppId(null); setRejectNotes(''); }}>
              <div style={{
                background: '#fff', borderRadius: 12, maxWidth: 420, width: '100%', padding: 24,
              }} onClick={e => e.stopPropagation()}>
                <h4 style={{ margin: '0 0 12px' }}>Reject Application</h4>
                <textarea
                  placeholder="Rejection reason (optional)"
                  value={rejectNotes}
                  onChange={e => setRejectNotes(e.target.value)}
                  style={{ width: '100%', minHeight: 80, padding: 10, borderRadius: 6, border: '1px solid #ddd', fontSize: 13, resize: 'vertical' }}
                />
                <div style={{ display: 'flex', gap: 8, marginTop: 12, justifyContent: 'flex-end' }}>
                  <button
                    style={{ fontSize: 13, padding: '8px 16px', borderRadius: 6, border: '1px solid #ddd', background: '#fff', cursor: 'pointer' }}
                    onClick={() => { setRejectAppId(null); setRejectNotes(''); }}
                  >Cancel</button>
                  <button
                    style={{ fontSize: 13, padding: '8px 16px', borderRadius: 6, border: 'none', background: '#e74c3c', color: '#fff', cursor: 'pointer' }}
                    onClick={async () => {
                      try {
                        await builderApplicationsAPI.review(rejectAppId, { action: 'reject', notes: rejectNotes || undefined });
                        toast.success('Application rejected');
                        setBuilderApps(prev => prev.map(a => a.id === rejectAppId ? { ...a, status: 'REJECTED' } : a));
                      } catch { toast.error('Failed to reject'); }
                      setRejectAppId(null);
                      setRejectNotes('');
                    }}
                  >Reject Application</button>
                </div>
              </div>
            </div>
          )}

          {/* Application Detail Modal */}
          {selectedApp && (
            <div style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 1000,
              display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
            }} onClick={() => setSelectedApp(null)}>
              <div style={{
                background: '#fff', borderRadius: 12, maxWidth: 720, width: '100%',
                maxHeight: '80vh', overflow: 'auto', padding: 32,
              }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                  <h3 style={{ margin: 0 }}>{selectedApp.company_name}</h3>
                  <button onClick={() => setSelectedApp(null)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}>&times;</button>
                </div>
                <div style={{ fontSize: 13, marginBottom: 16, color: '#666' }}>
                  {selectedApp.contact_first} {selectedApp.contact_last} &middot; {selectedApp.contact_email}
                  {selectedApp.contact_phone && <> &middot; {selectedApp.contact_phone}</>}
                  {selectedApp.ein && <> &middot; EIN: {selectedApp.ein}</>}
                </div>

                {/* Signature */}
                {selectedApp.signature_data && selectedApp.signature_data.name && (
                  <div style={{ background: '#f8f9fa', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
                    <strong>E-Signature:</strong> {selectedApp.signature_data.name} &mdash; {selectedApp.signature_data.date ? new Date(selectedApp.signature_data.date).toLocaleString() : ''}
                    {selectedApp.signature_data.contentHash && <div style={{ fontSize: 11, color: '#999', marginTop: 4, fontFamily: 'monospace' }}>Hash: {selectedApp.signature_data.contentHash.substring(0, 16)}...</div>}
                  </div>
                )}

                {/* Application Data */}
                {selectedApp.application_data && Object.keys(selectedApp.application_data).length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <h4 style={{ marginBottom: 8 }}>Application Data</h4>
                    <div style={{ background: '#f8f9fa', padding: 12, borderRadius: 8, fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
                      {Object.entries(selectedApp.application_data).filter(([k]) => !k.startsWith('_')).map(([key, val]) => {
                        if (val && typeof val === 'object' && !Array.isArray(val)) {
                          return (
                            <div key={key} style={{ marginBottom: 8 }}>
                              <div style={{ fontWeight: 600, color: '#333', marginBottom: 4, textTransform: 'capitalize' }}>{key.replace(/([A-Z])/g, ' $1').trim()}</div>
                              {Object.entries(val).map(([k2, v2]) => (
                                <div key={k2} style={{ marginLeft: 12, marginBottom: 2 }}>
                                  <span style={{ fontWeight: 500, color: '#555' }}>{k2}:</span>{' '}
                                  <span style={{ color: '#666' }}>{typeof v2 === 'object' ? JSON.stringify(v2) : String(v2 ?? '')}</span>
                                </div>
                              ))}
                            </div>
                          );
                        }
                        if (Array.isArray(val)) {
                          return (
                            <div key={key} style={{ marginBottom: 8 }}>
                              <div style={{ fontWeight: 600, color: '#333', marginBottom: 4, textTransform: 'capitalize' }}>{key.replace(/([A-Z])/g, ' $1').trim()} ({val.length})</div>
                              {val.map((item, idx) => (
                                <div key={idx} style={{ marginLeft: 12, marginBottom: 4, paddingBottom: 4, borderBottom: idx < val.length - 1 ? '1px solid #e9ecef' : 'none' }}>
                                  {typeof item === 'object' && item ? Object.entries(item).map(([k3, v3]) => (
                                    <div key={k3} style={{ marginBottom: 1 }}>
                                      <span style={{ fontWeight: 500, color: '#555' }}>{k3}:</span>{' '}
                                      <span style={{ color: '#666' }}>{String(v3 ?? '')}</span>
                                    </div>
                                  )) : <span style={{ color: '#666' }}>{String(item ?? '')}</span>}
                                </div>
                              ))}
                            </div>
                          );
                        }
                        return (
                          <div key={key} style={{ marginBottom: 4 }}>
                            <span style={{ fontWeight: 500, color: '#333' }}>{key}:</span>{' '}
                            <span style={{ color: '#666' }}>{String(val ?? '')}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Documents */}
                {selectedApp.documents && selectedApp.documents.length > 0 && (
                  <div>
                    <h4 style={{ marginBottom: 8 }}>Documents ({selectedApp.documents.length})</h4>
                    {selectedApp.documents.map(doc => (
                      <div key={doc.id} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '8px 12px', border: '1px solid #eee', borderRadius: 6, marginBottom: 4, fontSize: 13,
                      }}>
                        <div>
                          <strong>{doc.doc_type}</strong>
                          <span style={{ color: '#999', marginLeft: 8 }}>{doc.file_name}</span>
                          <span style={{ color: '#bbb', marginLeft: 8 }}>{(doc.file_size / 1024).toFixed(0)} KB</span>
                        </div>
                        <button
                          style={{ fontSize: 12, padding: '3px 10px', borderRadius: 4, border: '1px solid #ddd', background: '#fff', cursor: 'pointer' }}
                          onClick={async () => {
                            try {
                              const result = await builderApplicationsAPI.getDownloadUrl(selectedApp.id, doc.id);
                              window.open(result.download_url, '_blank');
                            } catch { toast.error('Failed to get download link'); }
                          }}
                        >Download</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
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

      {/* Edit Partner Modal */}
      {showEditModal && (
        <div className="edit-modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="edit-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="edit-modal-header">
              <h2>Edit Partner Profile</h2>
              <button
                className="btn-close-modal"
                onClick={() => setShowEditModal(false)}
              >
                ×
              </button>
            </div>
            <div className="edit-modal-body">
              <div className="edit-form-grid">
                {/* Basic Information */}
                <div className="form-section">
                  <h4>Basic Information</h4>
                  <div className="form-row">
                    <div className="form-group">
                      <label>First Name *</label>
                      <input
                        type="text"
                        value={editForm.first_name}
                        onChange={(e) => handleEditFormChange('first_name', e.target.value)}
                        placeholder="First name"
                      />
                    </div>
                    <div className="form-group">
                      <label>Last Name *</label>
                      <input
                        type="text"
                        value={editForm.last_name}
                        onChange={(e) => handleEditFormChange('last_name', e.target.value)}
                        placeholder="Last name"
                      />
                    </div>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Company</label>
                      <input
                        type="text"
                        value={editForm.company}
                        onChange={(e) => handleEditFormChange('company', e.target.value)}
                        placeholder="Company name"
                      />
                    </div>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Title</label>
                      <input
                        type="text"
                        value={editForm.title}
                        onChange={(e) => handleEditFormChange('title', e.target.value)}
                        placeholder="Job title"
                      />
                    </div>
                    <div className="form-group">
                      <label>Partner Type</label>
                      <select
                        value={editForm.type}
                        onChange={(e) => handleEditFormChange('type', e.target.value)}
                      >
                        <option value="">Select type...</option>
                        {PARTNER_TYPES.map((type) => (
                          <option key={type} value={type}>{type}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>

                {/* Contact Information */}
                <div className="form-section">
                  <h4>Contact Information</h4>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Email</label>
                      <input
                        type="email"
                        value={editForm.email}
                        onChange={(e) => handleEditFormChange('email', e.target.value)}
                        placeholder="email@example.com"
                      />
                    </div>
                    <div className="form-group">
                      <label>Phone</label>
                      <input
                        type="tel"
                        value={editForm.phone}
                        onChange={(e) => handleEditFormChange('phone', e.target.value)}
                        placeholder="(555) 123-4567"
                      />
                    </div>
                  </div>
                </div>

                {/* Address */}
                <div className="form-section">
                  <h4>Address</h4>
                  <div className="form-row">
                    <div className="form-group full-width">
                      <label>Street Address</label>
                      <input
                        type="text"
                        value={editForm.address}
                        onChange={(e) => handleEditFormChange('address', e.target.value)}
                        placeholder="123 Main Street"
                      />
                    </div>
                  </div>
                  <div className="form-row three-col">
                    <div className="form-group">
                      <label>City</label>
                      <input
                        type="text"
                        value={editForm.city}
                        onChange={(e) => handleEditFormChange('city', e.target.value)}
                        placeholder="City"
                      />
                    </div>
                    <div className="form-group">
                      <label>State</label>
                      <input
                        type="text"
                        value={editForm.state}
                        onChange={(e) => handleEditFormChange('state', e.target.value)}
                        placeholder="State"
                        maxLength={2}
                      />
                    </div>
                    <div className="form-group">
                      <label>ZIP Code</label>
                      <input
                        type="text"
                        value={editForm.zip}
                        onChange={(e) => handleEditFormChange('zip', e.target.value)}
                        placeholder="12345"
                        maxLength={10}
                      />
                    </div>
                  </div>
                </div>

                {/* Partnership Details */}
                <div className="form-section">
                  <h4>Partnership Details</h4>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Loyalty Tier</label>
                      <select
                        value={editForm.loyalty_tier}
                        onChange={(e) => handleEditFormChange('loyalty_tier', e.target.value)}
                      >
                        {TIER_OPTIONS.map((tier) => (
                          <option key={tier} value={tier}>{tier}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="form-row">
                    <div className="form-group full-width">
                      <label>Notes</label>
                      <textarea
                        value={editForm.notes}
                        onChange={(e) => handleEditFormChange('notes', e.target.value)}
                        placeholder="Any additional notes about this partner..."
                        rows={3}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="edit-modal-footer">
              <button
                className="btn-cancel"
                onClick={() => setShowEditModal(false)}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                className="btn-save"
                onClick={handleSavePartner}
                disabled={saving || !editForm.first_name || !editForm.last_name}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
      {partner && partner.phone && (
        <SMSAccordionPanel
          contactId={partner.id}
          contactName={partner.name || partner.company}
          phone={partner.phone}
          pageType="partner"
        />
      )}
    </div>
  );
}

export default ReferralPartnerDetail;
