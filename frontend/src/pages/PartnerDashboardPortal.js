/**
 * Partner Dashboard Portal
 *
 * Full-featured portal view for referral partners showing their leads,
 * active clients, and closed clients with deep dive capabilities.
 * Accessed via "View Portal" button from ReferralPartnerDetail.
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { partnersAPI } from '../services/api';
import './PartnerDashboardPortal.css';

// Status badge component
const StatusBadge = ({ status }) => {
  const statusConfig = {
    'New': { color: 'blue', label: 'New Lead' },
    'Attempted Contact': { color: 'yellow', label: 'Attempted Contact' },
    'Prospect': { color: 'purple', label: 'Prospect' },
    'Application': { color: 'orange', label: 'Application' },
    'Pre-Qualified': { color: 'cyan', label: 'Pre-Qualified' },
    'Pre-Approved': { color: 'green', label: 'Pre-Approved' },
    'Completed': { color: 'emerald', label: 'Completed' },
    'Withdrawn': { color: 'gray', label: 'Withdrawn' },
    'Does Not Qualify': { color: 'red', label: 'Does Not Qualify' },
  };

  const config = statusConfig[status] || { color: 'gray', label: status };

  return (
    <span className={`portal-status-badge status-${config.color}`}>
      {config.label}
    </span>
  );
};

// Tier badge component
const TierBadge = ({ tier }) => {
  const tierClass = tier?.toLowerCase() || 'bronze';
  return (
    <span className={`portal-tier-badge tier-${tierClass}`}>
      {tier || 'Bronze'}
    </span>
  );
};

// Stats card component
const StatsCard = ({ icon, value, label, color }) => (
  <div className={`portal-stats-card ${color || ''}`}>
    <div className="stats-icon">{icon}</div>
    <div className="stats-content">
      <div className="stats-value">{value}</div>
      <div className="stats-label">{label}</div>
    </div>
  </div>
);

// Lead card component with expandable details
const LeadCard = ({ lead, onExpand, isExpanded, onViewDetails }) => {
  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatCurrency = (amount) => {
    if (!amount) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount);
  };

  return (
    <div className={`portal-lead-card ${isExpanded ? 'expanded' : ''}`}>
      <div className="lead-card-header" onClick={onExpand}>
        <div className="lead-main-info">
          <div className="lead-avatar">
            {lead.name?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div className="lead-name-section">
            <h3 className="lead-name">{lead.name || 'Unknown'}</h3>
            <p className="lead-contact">{lead.email || 'No email'}</p>
          </div>
        </div>
        <div className="lead-status-section">
          <StatusBadge status={lead.stage} />
          <span className="lead-date">Added {formatDate(lead.created_at)}</span>
        </div>
        <button className="expand-btn">
          {isExpanded ? '▲' : '▼'}
        </button>
      </div>

      {isExpanded && (
        <div className="lead-card-details">
          <div className="details-grid">
            <div className="detail-item">
              <span className="detail-label">Phone</span>
              <span className="detail-value">{lead.phone || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Email</span>
              <span className="detail-value">{lead.email || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Loan Purpose</span>
              <span className="detail-value">{lead.loan_purpose || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Loan Amount</span>
              <span className="detail-value">{formatCurrency(lead.loan_amount)}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Property Type</span>
              <span className="detail-value">{lead.property_type || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Credit Score</span>
              <span className="detail-value">{lead.credit_score || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Source</span>
              <span className="detail-value">{lead.source || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Last Updated</span>
              <span className="detail-value">{formatDate(lead.updated_at)}</span>
            </div>
          </div>

          {/* Timeline/Progress */}
          <div className="lead-timeline">
            <h4>Status Timeline</h4>
            <div className="timeline-steps">
              {['New', 'Prospect', 'Application', 'Pre-Approved', 'Completed'].map((step, index) => {
                const currentIndex = ['New', 'Prospect', 'Application', 'Pre-Approved', 'Completed'].indexOf(lead.stage);
                const isComplete = index <= currentIndex;
                const isCurrent = index === currentIndex;

                return (
                  <div key={step} className={`timeline-step ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''}`}>
                    <div className="step-indicator">
                      {isComplete ? '✓' : index + 1}
                    </div>
                    <span className="step-label">{step}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {lead.notes && (
            <div className="lead-notes">
              <h4>Notes</h4>
              <p>{lead.notes}</p>
            </div>
          )}

          {/* View Full Details Button */}
          <div className="lead-actions">
            <button
              className="view-details-btn"
              onClick={(e) => {
                e.stopPropagation();
                onViewDetails && onViewDetails(lead);
              }}
            >
              View Full Details →
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// Category section component
const CategorySection = ({ title, leads, emptyMessage, defaultExpanded = false, onViewDetails }) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [expandedLeadId, setExpandedLeadId] = useState(null);

  return (
    <div className="portal-category-section">
      <div className="category-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="category-title">
          <h2>{title}</h2>
          <span className="category-count">{leads.length}</span>
        </div>
        <button className="category-toggle">
          {isExpanded ? '−' : '+'}
        </button>
      </div>

      {isExpanded && (
        <div className="category-content">
          {leads.length === 0 ? (
            <div className="empty-category">
              <p>{emptyMessage}</p>
            </div>
          ) : (
            <div className="leads-list">
              {leads.map(lead => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  isExpanded={expandedLeadId === lead.id}
                  onExpand={() => setExpandedLeadId(expandedLeadId === lead.id ? null : lead.id)}
                  onViewDetails={onViewDetails}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function PartnerDashboardPortal() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [partner, setPartner] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPartnerData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadPartnerData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch partner info and referrals (including application-selected realtors)
      const [partnerData, referralsData] = await Promise.all([
        partnersAPI.getById(id),
        partnersAPI.getReferrals(id)
      ]);

      if (!partnerData) {
        throw new Error('Partner not found');
      }

      setPartner(partnerData);

      // Use the referrals from the new endpoint which includes:
      // 1. Direct referrals (referral_partner_id)
      // 2. Source matches (lead source contains partner name)
      // 3. Application-selected realtors (borrower chose this partner as realtor)
      setReferrals(referralsData.referrals || []);
    } catch (err) {
      console.error('Failed to load partner data:', err);
      setError(err.message || 'Failed to load partner portal');
    } finally {
      setLoading(false);
    }
  };

  const categorizeReferrals = () => {
    return {
      leads: referrals.filter(r => ['New', 'Attempted Contact', 'Prospect'].includes(r.stage)),
      active: referrals.filter(r => ['Application', 'Pre-Qualified', 'Pre-Approved'].includes(r.stage)),
      closed: referrals.filter(r => r.stage === 'Completed'),
    };
  };

  if (loading) {
    return (
      <div className="partner-dashboard-portal loading">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Loading partner portal...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="partner-dashboard-portal error">
        <div className="error-card">
          <span className="error-icon">⚠️</span>
          <h1>Error Loading Portal</h1>
          <p>{error}</p>
          <button onClick={() => navigate('/referral-partners')}>
            Back to Partners
          </button>
        </div>
      </div>
    );
  }

  const categories = categorizeReferrals();
  const conversionRate = referrals.length > 0
    ? ((categories.closed.length / referrals.length) * 100).toFixed(1)
    : 0;

  // Handle navigation to client detail page
  const handleViewDetails = (lead) => {
    // Use lead.loan_id if available, otherwise use lead.id
    const clientId = lead.loan_id || lead.id;
    navigate(`/partner-portal/${id}/client/${clientId}`);
  };

  return (
    <div className="partner-dashboard-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="header-content">
          <div className="header-top">
            <button className="back-btn" onClick={() => navigate(`/referral-partners/${id}`)}>
              ← Back to Admin View
            </button>
            <div className="portal-badge">
              <span className="badge-icon">👁️</span>
              <span>Partner Portal View</span>
            </div>
          </div>

          <div className="partner-info">
            <div className="partner-avatar">
              {partner.name?.charAt(0)?.toUpperCase() || 'P'}
            </div>
            <div className="partner-details">
              <div className="partner-name-row">
                <h1>{partner.name}</h1>
                <TierBadge tier={partner.loyalty_tier} />
              </div>
              <p className="partner-company">{partner.company || 'Independent Partner'}</p>
              <p className="partner-type">{partner.type || 'Referral Partner'}</p>
            </div>
          </div>

          {/* Stats Row */}
          <div className="portal-stats-row">
            <StatsCard
              icon="📊"
              value={referrals.length}
              label="Total Referrals"
              color="blue"
            />
            <StatsCard
              icon="🔥"
              value={categories.leads.length}
              label="Active Leads"
              color="orange"
            />
            <StatsCard
              icon="📝"
              value={categories.active.length}
              label="In Progress"
              color="yellow"
            />
            <StatsCard
              icon="✅"
              value={categories.closed.length}
              label="Closed Loans"
              color="green"
            />
            <StatsCard
              icon="📈"
              value={`${conversionRate}%`}
              label="Conversion Rate"
              color="purple"
            />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="portal-main">
        <div className="portal-content">
          {/* Leads Section */}
          <CategorySection
            title="Leads"
            leads={categories.leads}
            emptyMessage="No active leads at this time. New referrals will appear here."
            defaultExpanded={true}
            onViewDetails={handleViewDetails}
          />

          {/* Active Clients Section */}
          <CategorySection
            title="Active Clients"
            leads={categories.active}
            emptyMessage="No clients currently in the loan process."
            defaultExpanded={true}
            onViewDetails={handleViewDetails}
          />

          {/* Closed Clients Section */}
          <CategorySection
            title="Closed Clients"
            leads={categories.closed}
            emptyMessage="Completed loans will appear here."
            defaultExpanded={false}
            onViewDetails={handleViewDetails}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="portal-footer">
        <p>Partner Portal - {partner.name}</p>
        <p className="powered-by">Powered by Perennia AI</p>
      </footer>
    </div>
  );
}
