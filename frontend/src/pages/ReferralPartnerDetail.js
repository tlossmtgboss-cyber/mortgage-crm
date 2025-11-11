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

    const confirmed = window.confirm(
      `Add ${lead.name} to ${partner.name}'s ${categoryNames[searchCategory]}?`
    );

    if (!confirmed) return;

    try {
      // Update the lead with the referral partner ID
      await leadsAPI.update(lead.id, {
        referral_partner_id: parseInt(id)
      });

      // Close modal and refresh data
      setShowSearchModal(false);
      setSearchQuery('');
      setSearchResults([]);

      // Reload partner data to show the newly assigned lead
      await loadPartnerData();

      alert(`${lead.name} has been added to ${partner.name}'s referrals!`);
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
            <div className="stat-value">{categories.closed.length}</div>
            <div className="stat-label">Closed Loans</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{categories.active.length}</div>
            <div className="stat-label">Active Clients</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">
              ${((partner.volume || 0) / 1000000).toFixed(1)}M
            </div>
            <div className="stat-label">Total Volume</div>
          </div>
        </div>
      </div>

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
