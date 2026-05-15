/**
 * Partner Dashboard Portal - Redesigned
 *
 * Full-featured portal for referral partners with:
 * - Dashboard overview with stats
 * - Loan programs education
 * - Marketing support requests
 * - AI Assistant for pre-approval letters
 * - Client tracking (leads, active, closed)
 */

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { partnersAPI, activitiesAPI } from '../services/api';
import './PartnerDashboardPortal.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

// Activity type configuration
const ACTIVITY_TYPE_CONFIG = {
  note: { label: 'Note', color: '#B8924A' },
  call: { label: 'Call', color: '#2D7A52' },
  email: { label: 'Email', color: '#3b82f6' },
  sms: { label: 'SMS', color: '#B8924A' },
  meeting: { label: 'Meeting', color: '#f59e0b' },
  stage_change: { label: 'Status Update', color: '#1F3D2E' },
  new_lead: { label: 'New Lead', color: '#2D7A52' },
  progress: { label: 'In Progress', color: '#3b82f6' },
  closed: { label: 'Closed', color: '#22c55e' },
};

// Format relative time
const formatRelativeTime = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Tab configuration
const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'programs', label: 'Programs' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'assistant', label: 'AI Assistant' },
  { id: 'clients', label: 'Clients', hasSubmenu: true },
  { id: 'micropage', label: 'My Micropage' },
];

// Client submenu categories
const CLIENT_CATEGORIES = [
  { id: 'all', label: 'All Clients' },
  { id: 'leads', label: 'Leads' },
  { id: 'active', label: 'Active Loans' },
  { id: 'closed', label: 'Closed Clients' },
  { id: 'nurtured', label: 'Nurtured Clients' },
  { id: 'credit_challenged', label: 'Credit Challenged' },
  { id: 'another_lender', label: 'Went with Another Lender' },
  { id: 'not_interested', label: 'Not Interested' },
];

// Loan program data
const LOAN_PROGRAMS = [
  {
    id: 'conventional',
    name: 'Conventional',
    color: '#3b82f6',
    minCredit: 620,
    minDown: '3%',
    maxDTI: '45%',
    highlights: ['Most common loan type', 'PMI removed at 20% equity', 'Fixed & ARM options'],
    bestFor: 'Buyers with good credit and stable income',
  },
  {
    id: 'fha',
    name: 'FHA',
    color: '#2D7A52',
    minCredit: 580,
    minDown: '3.5%',
    maxDTI: '50%',
    highlights: ['Lower credit requirements', 'Gift funds allowed', 'Assumable loans'],
    bestFor: 'First-time buyers or those rebuilding credit',
  },
  {
    id: 'va',
    name: 'VA',
    color: '#B8924A',
    minCredit: 580,
    minDown: '0%',
    maxDTI: '41%',
    highlights: ['No down payment', 'No PMI', 'Competitive rates'],
    bestFor: 'Veterans, active military, and eligible spouses',
  },
  {
    id: 'usda',
    name: 'USDA',
    color: '#f59e0b',
    minCredit: 640,
    minDown: '0%',
    maxDTI: '41%',
    highlights: ['No down payment', 'Rural areas', 'Income limits apply'],
    bestFor: 'Buyers in eligible rural areas',
  },
  {
    id: 'jumbo',
    name: 'Jumbo',
    color: '#ec4899',
    minCredit: 700,
    minDown: '10%',
    maxDTI: '43%',
    highlights: ['Higher loan amounts', 'Luxury properties', 'Custom terms'],
    bestFor: 'High-value property purchases',
  },
  {
    id: 'nonqm',
    name: 'Non-QM',
    color: '#64748b',
    minCredit: 620,
    minDown: '10%',
    maxDTI: '50%',
    highlights: ['Bank statements', 'Asset depletion', 'DSCR for investors'],
    bestFor: 'Self-employed or non-traditional income',
  },
];

// Marketing materials
const MARKETING_CATEGORIES = [
  {
    id: 'flyers',
    name: 'Co-Branded Flyers',
    items: ['Rate Sheet', 'Open House Flyer', 'Just Listed/Sold', 'Buyer Guide'],
  },
  {
    id: 'digital',
    name: 'Digital Assets',
    items: ['Social Media Graphics', 'Email Templates', 'Website Banner', 'Video Content'],
  },
  {
    id: 'print',
    name: 'Print Materials',
    items: ['Business Cards', 'Brochures', 'Postcards', 'Door Hangers'],
  },
  {
    id: 'events',
    name: 'Event Support',
    items: ['Open House Setup', 'Lunch & Learn', 'Client Appreciation', 'Seminar Materials'],
  },
];

export default function PartnerDashboardPortal() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [clientsExpanded, setClientsExpanded] = useState(false);
  const [activeClientCategory, setActiveClientCategory] = useState('all');
  const [partner, setPartner] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPartnerData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Load activities when referrals are available
  useEffect(() => {
    if (referrals.length > 0) {
      loadActivitiesForReferrals();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referrals]);

  const loadActivitiesForReferrals = async () => {
    try {
      const jwtToken = getToken();
      if (!jwtToken) return; // Only fetch if CRM user is logged in

      // Get activities for all referrals (limit to recent ones)
      const allActivities = [];

      // Fetch activities and stage history for each referral (batch up to 5 for performance)
      const referralIds = referrals.slice(0, 10).map(r => r.id);

      for (const leadId of referralIds) {
        try {
          // Fetch activities
          const leadActivities = await activitiesAPI.getAll({ lead_id: leadId, limit: 5 });
          if (leadActivities?.length > 0) {
            const referral = referrals.find(r => r.id === leadId);
            leadActivities.forEach(activity => {
              allActivities.push({
                ...activity,
                lead_name: referral?.name || 'Unknown',
                lead_id: leadId,
              });
            });
          }

          // Fetch stage history
          const response = await fetch(
            `${process.env.REACT_APP_API_URL || ''}/api/v1/leads/${leadId}/stage-history`,
            {
              headers: {
                'Authorization': `Bearer ${jwtToken}`,
                'Content-Type': 'application/json'
              }
            }
          );
          if (response.ok) {
            const data = await response.json();
            const referral = referrals.find(r => r.id === leadId);
            (data.stage_history || []).forEach(history => {
              allActivities.push({
                id: `stage-${history.id}`,
                type: 'stage_change',
                content: `Status changed from "${history.from_stage || 'New'}" to "${history.to_stage}"`,
                created_at: history.changed_at,
                lead_name: referral?.name || 'Unknown',
                lead_id: leadId,
              });
            });
          }
        } catch (err) {
          console.error(`Error loading activities for lead ${leadId}:`, err);
        }
      }

      // Sort all activities by date (newest first)
      allActivities.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setActivities(allActivities.slice(0, 20)); // Keep top 20
    } catch (err) {
      console.error('Error loading activities:', err);
    }
  };

  const loadPartnerData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [partnerData, referralsData] = await Promise.all([
        partnersAPI.getById(id),
        partnersAPI.getReferrals(id),
      ]);

      if (!partnerData) {
        throw new Error('Partner not found');
      }

      setPartner(partnerData);
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
      all: referrals,
      leads: referrals.filter((r) =>
        ['New', 'Attempted Contact', 'Prospect'].includes(r.stage)
      ),
      active: referrals.filter((r) =>
        ['Application', 'Pre-Qualified', 'Pre-Approved', 'Processing', 'Under Contract'].includes(r.stage)
      ),
      closed: referrals.filter((r) => r.stage === 'Completed' || r.stage === 'Funded'),
      nurtured: referrals.filter((r) => r.stage === 'Nurturing' || r.stage === 'Long Term'),
      credit_challenged: referrals.filter((r) => r.stage === 'Credit Challenged' || r.stage === 'Credit Repair'),
      another_lender: referrals.filter((r) => r.stage === 'Went with Another Lender' || r.stage === 'Lost'),
      not_interested: referrals.filter((r) => r.stage === 'Not Interested' || r.stage === 'Withdrawn'),
    };
  };

  if (loading) {
    return (
      <div className="partner-portal-v2 loading-state">
        <div className="loading-content">
          <div className="loading-spinner" />
          <p>Loading your partner portal...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="partner-portal-v2 error-state">
        <div className="error-content">
          <h1>Unable to Load Portal</h1>
          <p>{error}</p>
          <button onClick={() => navigate('/referral-partners')}>Back to Partners</button>
        </div>
      </div>
    );
  }

  const categories = categorizeReferrals();
  const stats = {
    totalReferrals: referrals.length,
    activeLeads: categories.leads.length,
    inProgress: categories.active.length,
    closedLoans: categories.closed.length,
    conversionRate:
      referrals.length > 0
        ? ((categories.closed.length / referrals.length) * 100).toFixed(1)
        : 0,
    totalVolume: categories.closed.reduce((sum, r) => sum + (r.loan_amount || 0), 0),
  };

  return (
    <div className="partner-portal-v2">
      {/* Sidebar */}
      <aside className="portal-sidebar">
        <div className="sidebar-header">
          <div className="partner-avatar-lg">
            {partner.name?.charAt(0)?.toUpperCase() || 'P'}
          </div>
          <div className="partner-info-sidebar">
            <h2>{partner.name}</h2>
            <p>{partner.company || 'Independent Partner'}</p>
            <TierBadge tier={partner.loyalty_tier} />
          </div>
        </div>

        <nav className="sidebar-nav">
          {TABS.map((tab) => (
            <div key={tab.id} className="nav-item-wrapper">
              <button
                className={`nav-item ${activeTab === tab.id ? 'active' : ''} ${tab.hasSubmenu && clientsExpanded ? 'expanded' : ''}`}
                onClick={() => {
                  if (tab.hasSubmenu) {
                    setClientsExpanded(!clientsExpanded);
                    setActiveTab(tab.id);
                  } else {
                    setActiveTab(tab.id);
                    setClientsExpanded(false);
                  }
                }}
              >
                <span className="nav-label">{tab.label}</span>
                {tab.id === 'clients' && referrals.length > 0 && (
                  <span className="nav-badge">{referrals.length}</span>
                )}
                {tab.hasSubmenu && (
                  <span className={`nav-arrow ${clientsExpanded ? 'expanded' : ''}`}>
                    ›
                  </span>
                )}
              </button>

              {/* Client Submenu */}
              {tab.hasSubmenu && clientsExpanded && (
                <div className="nav-submenu">
                  {CLIENT_CATEGORIES.map((cat) => (
                    <button
                      key={cat.id}
                      className={`submenu-item ${activeClientCategory === cat.id ? 'active' : ''}`}
                      onClick={() => {
                        setActiveClientCategory(cat.id);
                        setActiveTab('clients');
                      }}
                    >
                      <span className="submenu-label">{cat.label}</span>
                      <span className="submenu-count">{categories[cat.id]?.length || 0}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="back-to-admin" onClick={() => navigate(`/referral-partners/${id}`)}>
            ← Admin View
          </button>
          <div className="lo-contact-mini">
            <span className="lo-label">Your Loan Officer</span>
            <span className="lo-name">{partner.assigned_lo_name || 'Contact Us'}</span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="portal-main-content">
        {activeTab === 'dashboard' && (
          <DashboardTab
            partner={partner}
            stats={stats}
            categories={categories}
            activities={activities}
            partnerId={id}
            navigate={navigate}
            onTabChange={setActiveTab}
          />
        )}
        {activeTab === 'programs' && <ProgramsTab />}
        {activeTab === 'marketing' && <MarketingTab partner={partner} />}
        {activeTab === 'assistant' && <AIAssistantTab partner={partner} />}
        {activeTab === 'clients' && (
          <ClientsTab
            categories={categories}
            partnerId={id}
            navigate={navigate}
            activeCategory={activeClientCategory}
            setActiveCategory={setActiveClientCategory}
          />
        )}
        {activeTab === 'micropage' && (
          <MicropageTab partner={partner} partnerId={id} />
        )}
      </main>
    </div>
  );
}

// ============================================================================
// DASHBOARD TAB
// ============================================================================
function DashboardTab({ partner, stats, categories, activities = [], partnerId, navigate, onTabChange }) {
  const [showReferralModal, setShowReferralModal] = useState(false);

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const handleQuickAction = (action) => {
    switch (action) {
      case 'referral':
        setShowReferralModal(true);
        break;
      case 'preapproval':
        onTabChange('assistant');
        break;
      case 'marketing':
        onTabChange('marketing');
        break;
      case 'contact':
        // Open email to LO
        if (partner.assigned_lo_email) {
          window.location.href = `mailto:${encodeURIComponent(partner.assigned_lo_email)}?subject=${encodeURIComponent('Partner Portal Message from ' + (partner.name || ''))}`;
        } else {
          toast.error('Loan officer contact information not available. Please contact support.');
        }
        break;
      default:
        break;
    }
  };

  const handleViewClient = (clientId) => {
    navigate(`/partner-portal/${partnerId}/client/${clientId}`);
  };

  return (
    <div className="tab-content dashboard-tab">
      <div className="tab-header">
        <h1>Welcome back, {partner.name?.split(' ')[0]}!</h1>
        <p>Here's an overview of your partnership performance</p>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-details">
            <span className="stat-value">{stats.totalReferrals}</span>
            <span className="stat-label">Total Referrals</span>
          </div>
        </div>
        <div className="stat-card warning">
          <div className="stat-details">
            <span className="stat-value">{stats.activeLeads}</span>
            <span className="stat-label">Active Leads</span>
          </div>
        </div>
        <div className="stat-card info">
          <div className="stat-details">
            <span className="stat-value">{stats.inProgress}</span>
            <span className="stat-label">In Progress</span>
          </div>
        </div>
        <div className="stat-card success">
          <div className="stat-details">
            <span className="stat-value">{stats.closedLoans}</span>
            <span className="stat-label">Closed Loans</span>
          </div>
        </div>
        <div className="stat-card purple">
          <div className="stat-details">
            <span className="stat-value">{stats.conversionRate}%</span>
            <span className="stat-label">Conversion Rate</span>
          </div>
        </div>
        <div className="stat-card gold">
          <div className="stat-details">
            <span className="stat-value">{formatCurrency(stats.totalVolume)}</span>
            <span className="stat-label">Closed Volume</span>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <section className="dashboard-section">
        <h2>Quick Actions</h2>
        <div className="quick-actions-grid">
          <QuickActionCard
            title="Submit a Referral"
            description="Send us a new client referral"
            color="#3b82f6"
            onClick={() => handleQuickAction('referral')}
          />
          <QuickActionCard
            title="Request Pre-Approval"
            description="Generate a pre-approval letter"
            color="#2D7A52"
            onClick={() => handleQuickAction('preapproval')}
          />
          <QuickActionCard
            title="Order Marketing"
            description="Request co-branded materials"
            color="#f59e0b"
            onClick={() => handleQuickAction('marketing')}
          />
          <QuickActionCard
            title="Contact LO"
            description="Message your loan officer"
            color="#B8924A"
            onClick={() => handleQuickAction('contact')}
          />
        </div>
      </section>

      {/* Recent Activity */}
      <section className="dashboard-section">
        <h2>Recent Activity</h2>
        <div className="activity-list">
          {/* Show real activities if available, otherwise fall back to lead-based activities */}
          {activities.length > 0 ? (
            activities.slice(0, 8).map((activity, idx) => (
              <EnhancedActivityItem
                key={activity.id || idx}
                activity={activity}
                onClickClient={() => handleViewClient(activity.lead_id)}
              />
            ))
          ) : (
            <>
              {categories.leads.slice(0, 3).map((lead) => (
                <ActivityItem
                  key={lead.id}
                  lead={lead}
                  type="new_lead"
                  onClick={() => handleViewClient(lead.id)}
                />
              ))}
              {categories.active.slice(0, 2).map((client) => (
                <ActivityItem
                  key={client.id}
                  lead={client}
                  type="progress"
                  onClick={() => handleViewClient(client.id)}
                />
              ))}
            </>
          )}
          {activities.length === 0 && categories.leads.length === 0 && categories.active.length === 0 && (
            <div className="empty-activity">
              <p>No recent activity. Submit a referral to get started!</p>
            </div>
          )}
        </div>
      </section>

      {/* Submit Referral Modal */}
      {showReferralModal && (
        <SubmitReferralModal
          partner={partner}
          partnerId={partnerId}
          onClose={() => setShowReferralModal(false)}
        />
      )}
    </div>
  );
}

function QuickActionCard({ title, description, color, onClick }) {
  return (
    <button className="quick-action-card" style={{ '--accent-color': color }} onClick={onClick}>
      <h3>{title}</h3>
      <p>{description}</p>
    </button>
  );
}

// Enhanced activity item that shows real CRM activities
function EnhancedActivityItem({ activity, onClickClient }) {
  const config = ACTIVITY_TYPE_CONFIG[activity.type?.toLowerCase()] || { label: activity.type || 'Update', color: '#6b7280' };

  return (
    <div className="activity-item enhanced">
      <div
        className="activity-dot"
        style={{ backgroundColor: config.color }}
      />
      <div className="activity-details">
        <div className="activity-header-row">
          <span
            className="activity-type-badge"
            style={{ backgroundColor: `${config.color}15`, color: config.color }}
          >
            {config.label}
          </span>
          <span className="activity-time">{formatRelativeTime(activity.created_at)}</span>
        </div>
        <span className="activity-name clickable" onClick={onClickClient}>
          {activity.lead_name}
        </span>
        <span className="activity-content">{activity.content}</span>
      </div>
    </div>
  );
}

function ActivityItem({ lead, type, onClick }) {
  const typeConfig = {
    new_lead: { label: 'New Lead' },
    progress: { label: 'In Progress' },
    closed: { label: 'Closed' },
  };
  const config = typeConfig[type] || typeConfig.new_lead;

  return (
    <div className="activity-item">
      <div className="activity-type-badge">{config.label}</div>
      <div className="activity-details">
        <span className="activity-name clickable" onClick={onClick}>{lead.name}</span>
        <span className="activity-status">{lead.stage}</span>
      </div>
      <span className="activity-time">
        {formatRelativeTime(lead.updated_at || lead.created_at)}
      </span>
    </div>
  );
}

// ============================================================================
// PROGRAMS TAB
// ============================================================================
function ProgramsTab() {
  const [selectedProgram, setSelectedProgram] = useState(null);

  return (
    <div className="tab-content programs-tab">
      <div className="tab-header">
        <h1>Loan Programs</h1>
        <p>Learn about our available mortgage programs to better serve your clients</p>
      </div>

      <div className="programs-grid">
        {LOAN_PROGRAMS.map((program) => (
          <div
            key={program.id}
            className={`program-card ${selectedProgram === program.id ? 'selected' : ''}`}
            style={{ '--program-color': program.color }}
            onClick={() => setSelectedProgram(selectedProgram === program.id ? null : program.id)}
          >
            <div className="program-header">
              <h3>{program.name}</h3>
            </div>

            <div className="program-quick-stats">
              <div className="quick-stat">
                <span className="qs-label">Min Credit</span>
                <span className="qs-value">{program.minCredit}</span>
              </div>
              <div className="quick-stat">
                <span className="qs-label">Min Down</span>
                <span className="qs-value">{program.minDown}</span>
              </div>
              <div className="quick-stat">
                <span className="qs-label">Max DTI</span>
                <span className="qs-value">{program.maxDTI}</span>
              </div>
            </div>

            {selectedProgram === program.id && (
              <div className="program-details">
                <div className="detail-section">
                  <h4>Key Benefits</h4>
                  <ul>
                    {program.highlights.map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                </div>
                <div className="detail-section">
                  <h4>Best For</h4>
                  <p>{program.bestFor}</p>
                </div>
                <button className="learn-more-btn">Download Full Guidelines</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Comparison Table */}
      <section className="comparison-section">
        <h2>Quick Comparison</h2>
        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Program</th>
                <th>Min Credit</th>
                <th>Min Down</th>
                <th>Max DTI</th>
                <th>PMI</th>
              </tr>
            </thead>
            <tbody>
              {LOAN_PROGRAMS.map((p) => (
                <tr key={p.id}>
                  <td>
                    <span className="program-name-cell">
                      {p.name}
                    </span>
                  </td>
                  <td>{p.minCredit}</td>
                  <td>{p.minDown}</td>
                  <td>{p.maxDTI}</td>
                  <td>{p.id === 'va' ? 'No' : p.id === 'conventional' ? 'Until 20%' : 'MIP/GF'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ============================================================================
// MARKETING TAB
// ============================================================================
function MarketingTab({ partner }) {
  const [selectedItems, setSelectedItems] = useState([]);
  const [requestNotes, setRequestNotes] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const toggleItem = (categoryId, item) => {
    const key = `${categoryId}-${item}`;
    setSelectedItems((prev) =>
      prev.includes(key) ? prev.filter((i) => i !== key) : [...prev, key]
    );
  };

  const handleSubmit = () => {
    // In production, this would send to backend
    console.log('Marketing request:', { selectedItems, requestNotes, partner: partner.name });
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setSelectedItems([]);
      setRequestNotes('');
    }, 3000);
  };

  return (
    <div className="tab-content marketing-tab">
      <div className="tab-header">
        <h1>Marketing Support</h1>
        <p>Request co-branded marketing materials to promote our partnership</p>
      </div>

      {submitted ? (
        <div className="submission-success">
          <h2>Request Submitted!</h2>
          <p>Our marketing team will prepare your materials within 2-3 business days.</p>
        </div>
      ) : (
        <>
          <div className="marketing-categories">
            {MARKETING_CATEGORIES.map((category) => (
              <div key={category.id} className="marketing-category">
                <div className="category-header">
                  <h3>{category.name}</h3>
                </div>
                <div className="category-items">
                  {category.items.map((item) => {
                    const key = `${category.id}-${item}`;
                    const isSelected = selectedItems.includes(key);
                    return (
                      <button
                        key={item}
                        className={`material-item ${isSelected ? 'selected' : ''}`}
                        onClick={() => toggleItem(category.id, item)}
                      >
                        <span className="item-check">{isSelected ? '✓' : ''}</span>
                        <span className="item-name">{item}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="request-form">
            <h3>Additional Details</h3>
            <textarea
              placeholder="Any specific requirements, colors, messaging, or deadlines?"
              value={requestNotes}
              onChange={(e) => setRequestNotes(e.target.value)}
              rows={4}
            />
            <div className="form-actions">
              <span className="selected-count">
                {selectedItems.length} item{selectedItems.length !== 1 ? 's' : ''} selected
              </span>
              <button
                className="submit-request-btn"
                disabled={selectedItems.length === 0}
                onClick={handleSubmit}
              >
                Submit Request
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// AI ASSISTANT TAB
// ============================================================================
function AIAssistantTab({ partner }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hi ${partner.name?.split(' ')[0] || 'there'}! I'm your AI Assistant. I can help you:\n\n• Generate pre-approval letters\n• Answer loan program questions\n• Create client communications\n• Explain guidelines\n\nHow can I help you today?`,
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [preApprovalData, setPreApprovalData] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setIsTyping(true);

    // Simulate AI response
    setTimeout(() => {
      let response = '';
      const lowerInput = userMessage.toLowerCase();

      if (lowerInput.includes('pre-approval') || lowerInput.includes('preapproval')) {
        response = `I'd be happy to help generate a pre-approval letter! Please provide:\n\n1. Buyer's full name\n2. Pre-approved loan amount\n3. Loan program (Conventional, FHA, VA, etc.)\n4. Property address (if known)\n\nOnce you provide these details, I'll create the letter for you.`;
        setPreApprovalData({ step: 'collecting' });
      } else if (lowerInput.includes('fha')) {
        response = `**FHA Loan Overview:**\n\n• Min Credit Score: 580 (3.5% down) or 500 (10% down)\n• Max DTI: 50%\n• Upfront MIP: 1.75%\n• Monthly MIP: 0.55% annually\n• Great for first-time buyers and credit rebuilding\n\nWould you like more details on FHA guidelines?`;
      } else if (lowerInput.includes('conventional')) {
        response = `**Conventional Loan Overview:**\n\n• Min Credit Score: 620\n• Min Down: 3% (first-time buyers) or 5%\n• PMI required below 20% equity\n• Max DTI: 45-50%\n• Most flexible loan type\n\nWould you like information on specific conventional products?`;
      } else if (preApprovalData?.step === 'collecting') {
        response = `Great! Based on your information, I've generated the pre-approval letter.\n\n**Pre-Approval Letter Ready**\n\nClick the button below to:\n• Download PDF\n• Email to client\n• Email to agent`;
        setPreApprovalData({ step: 'ready', data: userMessage });
      } else {
        response = `I can help with that! For pre-approval letters, loan program questions, or client communications, just let me know what you need.\n\nSome things I can do:\n• "Generate pre-approval letter"\n• "Explain FHA requirements"\n• "What's the max DTI for VA loans?"`;
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: response }]);
      setIsTyping(false);
    }, 1500);
  };

  return (
    <div className="tab-content assistant-tab">
      <div className="chat-container">
        <div className="chat-header">
          <div className="chat-title">
            <h2>AI Assistant</h2>
            <span className="online-status">Online</span>
          </div>
        </div>

        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-content">
                {msg.content.split('\n').map((line, j) => (
                  <p key={j}>{line}</p>
                ))}
                {msg.role === 'assistant' && preApprovalData?.step === 'ready' && i === messages.length - 1 && (
                  <div className="letter-actions">
                    <button className="letter-btn download">
                      Download PDF
                    </button>
                    <button className="letter-btn email">
                      Email to Client
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
          {isTyping && (
            <div className="message assistant typing">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="quick-prompts">
            <button onClick={() => setInput('Generate a pre-approval letter')}>
              Pre-Approval Letter
            </button>
            <button onClick={() => setInput('Explain FHA loan requirements')}>
              FHA Requirements
            </button>
            <button onClick={() => setInput('What programs allow gift funds?')}>
              Gift Funds
            </button>
          </div>
          <div className="chat-input-wrapper">
            <input
              type="text"
              placeholder="Ask me anything about loans, pre-approvals, or guidelines..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            />
            <button className="send-btn" onClick={handleSend} disabled={!input.trim()}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// CLIENTS TAB
// ============================================================================
function ClientsTab({ categories, partnerId, navigate, activeCategory, setActiveCategory }) {
  const [searchTerm, setSearchTerm] = useState('');

  // Get the category label for display
  const getCategoryLabel = (catId) => {
    const cat = CLIENT_CATEGORIES.find(c => c.id === catId);
    return cat?.label || 'All Clients';
  };

  // Get clients based on the active category
  const categoryClients = categories[activeCategory] || [];

  const filteredClients = categoryClients.filter((client) => {
    const matchesSearch =
      !searchTerm ||
      client.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      client.email?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSearch;
  });

  const handleViewDetails = (client) => {
    const clientId = client.loan_id || client.id;
    navigate(`/partner-portal/${partnerId}/client/${clientId}`);
  };

  return (
    <div className="tab-content clients-tab">
      <div className="tab-header">
        <h1>{getCategoryLabel(activeCategory)}</h1>
        <p>
          {activeCategory === 'all'
            ? 'Track all your referrals from lead to close'
            : `${filteredClients.length} client${filteredClients.length !== 1 ? 's' : ''} in this category`}
        </p>
      </div>

      {/* Search Bar */}
      <div className="clients-toolbar">
        <div className="search-box full-width">
          <input
            type="text"
            placeholder="Search clients by name or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Clients List */}
      <div className="clients-list">
        {filteredClients.length === 0 ? (
          <div className="empty-clients">
            <h3>No clients found</h3>
            <p>
              {searchTerm
                ? `No clients match "${searchTerm}"`
                : activeCategory === 'all'
                  ? 'Submit a referral to get started!'
                  : `No clients in ${getCategoryLabel(activeCategory).toLowerCase()} at this time.`}
            </p>
          </div>
        ) : (
          filteredClients.map((client) => (
            <ClientCard
              key={client.id}
              client={client}
              onViewDetails={() => handleViewDetails(client)}
              categoryId={activeCategory}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ClientCard({ client, onViewDetails, categoryId }) {
  const formatCurrency = (amount) => {
    if (!amount) return 'TBD';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const categoryColors = {
    all: '#64748b',
    leads: '#f59e0b',
    active: '#3b82f6',
    closed: '#2D7A52',
    nurtured: '#B8924A',
    credit_challenged: '#ef4444',
    another_lender: '#6b7280',
    not_interested: '#9ca3af',
  };

  return (
    <div
      className="client-card"
      style={{ '--category-color': categoryColors[categoryId] || '#64748b' }}
    >
      <div className="client-avatar">{client.name?.charAt(0)?.toUpperCase() || '?'}</div>
      <div className="client-info">
        <h3>{client.name || 'Unknown'}</h3>
        <p>{client.email || 'No email'}</p>
      </div>
      <div className="client-details">
        <div className="detail">
          <span className="label">Loan Amount</span>
          <span className="value">{formatCurrency(client.loan_amount)}</span>
        </div>
        <div className="detail">
          <span className="label">Status</span>
          <span className="value">{client.stage}</span>
        </div>
        <div className="detail">
          <span className="label">Updated</span>
          <span className="value">{formatDate(client.updated_at)}</span>
        </div>
      </div>
      <button className="view-btn" onClick={onViewDetails}>
        View →
      </button>
    </div>
  );
}

// ============================================================================
// SHARED COMPONENTS
// ============================================================================
function TierBadge({ tier }) {
  const tierClass = tier?.toLowerCase() || 'bronze';
  return (
    <span className={`tier-badge-v2 tier-${tierClass}`}>
      {tier || 'Bronze'}
    </span>
  );
}

// ============================================================================
// SUBMIT REFERRAL MODAL
// ============================================================================
function SubmitReferralModal({ partner, partnerId, onClose }) {
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    loanPurpose: 'purchase',
    propertyAddress: '',
    estimatedAmount: '',
    notes: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const response = await partnersAPI.submitReferral(partnerId, {
        name: `${formData.firstName} ${formData.lastName}`.trim(),
        email: formData.email,
        phone: formData.phone,
        loan_purpose: formData.loanPurpose,
        property_address: formData.propertyAddress,
        loan_amount: formData.estimatedAmount ? parseFloat(formData.estimatedAmount) : null,
        notes: formData.notes,
        source: 'Partner Portal',
      });

      if (response) {
        setSubmitted(true);
        setTimeout(() => {
          onClose();
          window.location.reload(); // Refresh to show new referral
        }, 2000);
      }
    } catch (err) {
      console.error('Error submitting referral:', err);
      setError(err.message || 'Failed to submit referral. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content referral-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-success">
            <div className="success-icon">✓</div>
            <h2>Referral Submitted!</h2>
            <p>Thank you for your referral. We'll reach out to your client within 24 hours.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content referral-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Submit a Referral</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          {error && <div className="form-error">{error}</div>}

          <div className="form-row">
            <div className="form-group">
              <label>First Name *</label>
              <input
                type="text"
                name="firstName"
                value={formData.firstName}
                onChange={handleChange}
                required
                placeholder="John"
              />
            </div>
            <div className="form-group">
              <label>Last Name *</label>
              <input
                type="text"
                name="lastName"
                value={formData.lastName}
                onChange={handleChange}
                required
                placeholder="Smith"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Email *</label>
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
                placeholder="john@email.com"
              />
            </div>
            <div className="form-group">
              <label>Phone *</label>
              <input
                type="tel"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                required
                placeholder="(555) 123-4567"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Loan Purpose</label>
              <select name="loanPurpose" value={formData.loanPurpose} onChange={handleChange}>
                <option value="purchase">Purchase</option>
                <option value="refinance">Refinance</option>
                <option value="cash_out">Cash-Out Refinance</option>
              </select>
            </div>
            <div className="form-group">
              <label>Estimated Loan Amount</label>
              <input
                type="number"
                name="estimatedAmount"
                value={formData.estimatedAmount}
                onChange={handleChange}
                placeholder="450000"
              />
            </div>
          </div>

          <div className="form-group">
            <label>Property Address (if known)</label>
            <input
              type="text"
              name="propertyAddress"
              value={formData.propertyAddress}
              onChange={handleChange}
              placeholder="123 Main St, City, State ZIP"
            />
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              name="notes"
              value={formData.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Any additional information about the client..."
            />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? 'Submitting...' : 'Submit Referral'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================================
// MICROPAGE TAB
// ============================================================================
function MicropageTab({ partner, partnerId }) {
  const [settings, setSettings] = useState({
    isEnabled: partner.micropage_enabled || false,
    slug: partner.micropage_slug || partner.name?.toLowerCase().replace(/\s+/g, '-') || '',
    headline: partner.micropage_headline || `Work with ${partner.name}`,
    bio: partner.micropage_bio || '',
    showPhoto: partner.micropage_show_photo !== false,
    showTestimonials: partner.micropage_show_testimonials !== false,
    primaryColor: partner.micropage_primary_color || '#1F3D2E',
    phoneNumber: partner.phone || '',
    email: partner.email || '',
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [deployed, setDeployed] = useState(partner.micropage_enabled || false);

  const micropageUrl = `https://perenniaai.com/partner/${settings.slug}`;

  const handleChange = (field, value) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save settings via API
      await partnersAPI.updateMicropage(partnerId, settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error('Error saving micropage settings:', err);
      toast.error('Failed to save settings. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeploy = async () => {
    setDeploying(true);
    try {
      // Deploy/Enable micropage
      await partnersAPI.updateMicropage(partnerId, { ...settings, isEnabled: true });
      setSettings((prev) => ({ ...prev, isEnabled: true }));
      setDeployed(true);
    } catch (err) {
      console.error('Error deploying micropage:', err);
      toast.error('Failed to deploy micropage. Please try again.');
    } finally {
      setDeploying(false);
    }
  };

  const handleDisable = async () => {
    if (!window.confirm('Are you sure you want to disable your micropage?')) return;

    try {
      await partnersAPI.updateMicropage(partnerId, { ...settings, isEnabled: false });
      setSettings((prev) => ({ ...prev, isEnabled: false }));
      setDeployed(false);
    } catch (err) {
      console.error('Error disabling micropage:', err);
      toast.error('Failed to disable micropage. Please try again.');
    }
  };

  return (
    <div className="tab-content micropage-tab">
      <div className="tab-header">
        <h1>My Micropage</h1>
        <p>Set up and manage your personal referral landing page</p>
      </div>

      {/* Status Banner */}
      <div className={`micropage-status-banner ${settings.isEnabled ? 'live' : 'draft'}`}>
        <div className="status-info">
          <span className={`status-dot ${settings.isEnabled ? 'live' : 'draft'}`} />
          <span className="status-text">
            {settings.isEnabled ? 'Your micropage is live!' : 'Your micropage is not yet published'}
          </span>
        </div>
        {settings.isEnabled && (
          <a href={micropageUrl} target="_blank" rel="noopener noreferrer" className="view-page-link">
            View Page →
          </a>
        )}
      </div>

      {/* URL Preview */}
      <div className="micropage-url-section">
        <label>Your Micropage URL</label>
        <div className="url-preview">
          <span className="url-base">perenniaai.com/partner/</span>
          <input
            type="text"
            value={settings.slug}
            onChange={(e) => handleChange('slug', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
            placeholder="your-name"
          />
        </div>
        <p className="url-hint">Use lowercase letters, numbers, and hyphens only</p>
      </div>

      {/* Settings Form */}
      <div className="micropage-settings-grid">
        <div className="settings-section">
          <h3>Page Content</h3>

          <div className="form-group">
            <label>Headline</label>
            <input
              type="text"
              value={settings.headline}
              onChange={(e) => handleChange('headline', e.target.value)}
              placeholder="Your catchy headline..."
            />
          </div>

          <div className="form-group">
            <label>Bio / About</label>
            <textarea
              value={settings.bio}
              onChange={(e) => handleChange('bio', e.target.value)}
              rows={4}
              placeholder="Tell visitors about yourself and why they should work with you..."
            />
          </div>

          <div className="form-group">
            <label>Contact Phone</label>
            <input
              type="tel"
              value={settings.phoneNumber}
              onChange={(e) => handleChange('phoneNumber', e.target.value)}
              placeholder="(555) 123-4567"
            />
          </div>

          <div className="form-group">
            <label>Contact Email</label>
            <input
              type="email"
              value={settings.email}
              onChange={(e) => handleChange('email', e.target.value)}
              placeholder="you@email.com"
            />
          </div>
        </div>

        <div className="settings-section">
          <h3>Display Options</h3>

          <div className="toggle-group">
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={settings.showPhoto}
                onChange={(e) => handleChange('showPhoto', e.target.checked)}
              />
              <span className="toggle-text">Show Profile Photo</span>
            </label>
          </div>

          <div className="toggle-group">
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={settings.showTestimonials}
                onChange={(e) => handleChange('showTestimonials', e.target.checked)}
              />
              <span className="toggle-text">Show Client Testimonials</span>
            </label>
          </div>

          <div className="form-group">
            <label>Primary Color</label>
            <div className="color-picker-row">
              <input
                type="color"
                value={settings.primaryColor}
                onChange={(e) => handleChange('primaryColor', e.target.value)}
              />
              <span className="color-value">{settings.primaryColor}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Preview Section */}
      <div className="micropage-preview-section">
        <h3>Preview</h3>
        <div className="preview-card" style={{ '--preview-color': settings.primaryColor }}>
          <div className="preview-header">
            {settings.showPhoto && (
              <div className="preview-avatar">{partner.name?.charAt(0)?.toUpperCase() || 'P'}</div>
            )}
            <h4>{settings.headline || `Work with ${partner.name}`}</h4>
            <p className="preview-name">{partner.name}</p>
          </div>
          <p className="preview-bio">
            {settings.bio || 'Your bio will appear here...'}
          </p>
          <div className="preview-cta" style={{ backgroundColor: settings.primaryColor }}>
            Get Started
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="micropage-actions">
        <button className="btn-secondary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : saved ? '✓ Saved!' : 'Save Changes'}
        </button>

        {settings.isEnabled ? (
          <button className="btn-danger" onClick={handleDisable}>
            Disable Micropage
          </button>
        ) : (
          <button className="btn-primary" onClick={handleDeploy} disabled={deploying}>
            {deploying ? 'Deploying...' : 'Deploy Micropage'}
          </button>
        )}
      </div>

      {/* Share Section */}
      {settings.isEnabled && (
        <div className="micropage-share-section">
          <h3>Share Your Page</h3>
          <p>Copy this link and share it with potential clients:</p>
          <div className="share-url-box">
            <input type="text" readOnly value={micropageUrl} />
            <button
              className="copy-btn"
              onClick={() => {
                navigator.clipboard.writeText(micropageUrl);
                toast.success('Link copied to clipboard!');
              }}
            >
              Copy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
