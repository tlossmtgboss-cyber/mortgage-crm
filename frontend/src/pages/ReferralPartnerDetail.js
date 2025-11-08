import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { partnersAPI, leadsAPI } from '../services/api';
import './ReferralPartnerDetail.css';

function ReferralPartnerDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [partner, setPartner] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPartnerData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadPartnerData = async () => {
    try {
      setLoading(true);
      const [partnerData, allLeads] = await Promise.all([
        partnersAPI.getById(id),
        leadsAPI.getAll()
      ]);

      setPartner(partnerData);

      // Filter leads that were referred by this partner
      const partnerReferrals = allLeads.filter(lead =>
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
            <span className="value">{partner.email || 'N/A'}</span>
          </div>
          <div className="info-item">
            <span className="label">Phone</span>
            <span className="value">{partner.phone || 'N/A'}</span>
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
            <span className="count-badge">{categories.leads.length}</span>
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
            <span className="count-badge">{categories.active.length}</span>
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
            <span className="count-badge">{categories.closed.length}</span>
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
            <span className="count-badge">{categories.nurtured.length}</span>
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
            <span className="count-badge">{categories.disqualified.length}</span>
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
    </div>
  );
}

export default ReferralPartnerDetail;
