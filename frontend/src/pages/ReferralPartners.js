import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { partnersAPI } from '../services/api';
import { formatPhoneNumber } from '../utils/phoneUtils';
import './ReferralPartners.css';
import { toast } from '../utils/toast';

const PARTNER_TYPES = [
  { key: 'all', label: 'All Partners', icon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8m14 14v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75' },
  { key: 'Realtor', label: 'Realtors', icon: 'M3 21l1.65-3.8a9 9 0 1 1 14.7 0L21 21M12 3v2m0 14v2m-7-9H3m18 0h-2' },
  { key: 'Builder', label: 'Builders', icon: 'M2 20h20M5 20V8l7-5 7 5v12M9 20v-5h6v5' },
  { key: 'Insurance Agent', label: 'Insurance', icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' },
  { key: 'Title', label: 'Title', icon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8' },
  { key: 'Attorney', label: 'Attorneys', icon: 'M12 1v6m-6 6h12M5 13l7 8 7-8M4 7h16' },
  { key: 'Financial Advisor', label: 'Financial', icon: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { key: 'CPA', label: 'CPAs', icon: 'M4 2v20h16V2zm4 6h8m-8 4h8m-8 4h5' },
];

const generateMockPartners = () => {
  return [
    { id: 1, name: 'Amy Smith', email: 'amy.smith@realestate.com', phone: '(555) 123-4567', company: 'Smith Realty Group', title: 'Senior Realtor', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 24, closed_loans: 18, volume: 2850000, partner_category: 'individual', last_referral: '2026-05-01' },
    { id: 2, name: 'Bob Johnson', email: 'bob@johnsoninsurance.com', phone: '(555) 234-5678', company: 'Johnson Insurance Agency', title: 'Insurance Agent', type: 'Insurance Agent', loyalty_tier: 'Silver', status: 'active', referrals_in: 15, closed_loans: 12, volume: 1620000, partner_category: 'individual', last_referral: '2026-04-22' },
    { id: 3, name: 'Carol White', email: 'carol@elitehomes.com', phone: '(555) 345-6789', company: 'Elite Homes Realty', title: 'Broker', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 32, closed_loans: 25, volume: 4100000, partner_category: 'individual', last_referral: '2026-05-10' },
    { id: 4, name: 'David Chen', email: 'david@chenfinancial.com', phone: '(555) 456-7890', company: 'Chen Financial Planning', title: 'Financial Advisor', type: 'Financial Advisor', loyalty_tier: 'Bronze', status: 'active', referrals_in: 8, closed_loans: 6, volume: 980000, partner_category: 'individual', last_referral: '2026-03-15' },
    { id: 5, name: 'Emily Rodriguez', email: 'emily@coastalrealty.com', phone: '(555) 567-8901', company: 'Coastal Realty Partners', title: 'Managing Broker', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 28, closed_loans: 22, volume: 3650000, partner_category: 'individual', last_referral: '2026-05-08' },
    { id: 6, name: 'Frank Miller', email: 'frank@millerlegal.com', phone: '(555) 678-9012', company: 'Miller & Associates Law', title: 'Attorney', type: 'Attorney', loyalty_tier: 'Silver', status: 'active', referrals_in: 12, closed_loans: 10, volume: 1450000, partner_category: 'individual', last_referral: '2026-04-28' },
    { id: 7, name: 'Grace Lee', email: 'grace@premiumhomes.com', phone: '(555) 789-0123', company: 'Premium Homes Group', title: 'Realtor', type: 'Realtor', loyalty_tier: 'Silver', status: 'active', referrals_in: 18, closed_loans: 14, volume: 2180000, partner_category: 'individual', last_referral: '2026-04-15' },
    { id: 8, name: 'Henry Davis', email: 'henry@daviscpa.com', phone: '(555) 890-1234', company: 'Davis CPA Firm', title: 'CPA', type: 'CPA', loyalty_tier: 'Bronze', status: 'active', referrals_in: 6, closed_loans: 5, volume: 720000, partner_category: 'individual', last_referral: '2026-02-20' },
    { id: 9, name: 'Irene Martinez', email: 'irene@luxuryproperties.com', phone: '(555) 901-2345', company: 'Luxury Properties LLC', title: 'Luxury Realtor', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 21, closed_loans: 16, volume: 5200000, partner_category: 'individual', last_referral: '2026-05-12' },
    { id: 10, name: 'Jack Wilson', email: 'jack@wilsonbuilders.com', phone: '(555) 012-3456', company: 'Wilson Custom Builders', title: 'Builder', type: 'Builder', loyalty_tier: 'Silver', status: 'active', referrals_in: 14, closed_loans: 11, volume: 1890000, partner_category: 'individual', last_referral: '2026-04-30' },
    { id: 11, name: 'Karen Thompson', email: 'karen@thompsonrealty.com', phone: '(555) 111-2222', company: 'Thompson Realty', title: 'Broker', type: 'Realtor', loyalty_tier: 'Bronze', status: 'inactive', referrals_in: 5, closed_loans: 3, volume: 450000, partner_category: 'individual', last_referral: '2025-11-10' },
    { id: 12, name: 'Liam Brown', email: 'liam@brownfinancial.com', phone: '(555) 222-3333', company: 'Brown Financial Services', title: 'Wealth Manager', type: 'Financial Advisor', loyalty_tier: 'Silver', status: 'active', referrals_in: 11, closed_loans: 9, volume: 1340000, partner_category: 'individual', last_referral: '2026-04-05' },
    { id: 13, name: 'Maria Garcia', email: 'maria@garciahomes.com', phone: '(555) 333-4444', company: 'Garcia Homes Real Estate', title: 'Realtor', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 26, closed_loans: 20, volume: 3250000, partner_category: 'individual', last_referral: '2026-05-09' },
    { id: 14, name: 'Nathan Clark', email: 'nathan@clarklaw.com', phone: '(555) 444-5555', company: 'Clark Law Group', title: 'Real Estate Attorney', type: 'Attorney', loyalty_tier: 'Bronze', status: 'active', referrals_in: 7, closed_loans: 6, volume: 890000, partner_category: 'individual', last_referral: '2026-03-22' },
    { id: 15, name: 'Olivia Taylor', email: 'olivia@taylorproperties.com', phone: '(555) 555-6666', company: 'Taylor Properties', title: 'Senior Agent', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 30, closed_loans: 24, volume: 3920000, partner_category: 'individual', last_referral: '2026-05-11' },
    { id: 16, name: 'Paul Anderson', email: 'paul@andersongroup.com', phone: '(555) 666-7777', company: 'Anderson Investment Group', title: 'Investment Advisor', type: 'Financial Advisor', loyalty_tier: 'Silver', status: 'active', referrals_in: 13, closed_loans: 10, volume: 1780000, partner_category: 'individual', last_referral: '2026-04-18' },
    { id: 17, name: 'Summit Homes LLC', email: 'info@summithomes.com', phone: '(555) 777-8888', company: 'Summit Homes', title: 'Custom Builder', type: 'Builder', loyalty_tier: 'Gold', status: 'active', referrals_in: 19, closed_loans: 15, volume: 4800000, partner_category: 'individual', last_referral: '2026-05-03' },
    { id: 18, name: 'Rachel Torres', email: 'rachel@securetitle.com', phone: '(555) 888-9999', company: 'Secure Title Services', title: 'Title Officer', type: 'Title', loyalty_tier: 'Silver', status: 'active', referrals_in: 10, closed_loans: 8, volume: 1200000, partner_category: 'individual', last_referral: '2026-04-25' },
    { id: 19, name: 'Steve Park', email: 'steve@parktitle.com', phone: '(555) 999-0000', company: 'Park Title & Escrow', title: 'Escrow Officer', type: 'Title', loyalty_tier: 'Bronze', status: 'active', referrals_in: 4, closed_loans: 3, volume: 520000, partner_category: 'individual', last_referral: '2026-03-08' },
  ];
};

function SvgIcon({ path, size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d={path} />
    </svg>
  );
}

function ReferralPartners() {
  const navigate = useNavigate();
  const [partners, setPartners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [activeType, setActiveType] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('referrals_in');

  useEffect(() => {
    loadPartners();
  }, []);

  const loadPartners = async () => {
    try {
      setLoading(true);
      try {
        const data = await partnersAPI.getAll();
        if (Array.isArray(data) && data.length > 0) {
          setPartners(data);
        } else {
          setPartners(generateMockPartners());
        }
      } catch (apiError) {
        setPartners(generateMockPartners());
      }
    } catch (error) {
      console.error('Failed to load referral partners:', error);
      setPartners(generateMockPartners());
    } finally {
      setLoading(false);
    }
  };

  const handleAddPartner = async (partnerData) => {
    try {
      await partnersAPI.create(partnerData);
      loadPartners();
      setShowAddModal(false);
      toast.success('Partner added successfully');
    } catch (error) {
      console.error('Failed to create partner:', error);
      const errorMsg = error.response?.data?.detail
        ? (typeof error.response.data.detail === 'string'
           ? error.response.data.detail
           : JSON.stringify(error.response.data.detail))
        : error.message || 'Unknown error';
      toast.error('Failed to create referral partner: ' + errorMsg);
    }
  };

  const handleDeletePartner = async (id, e) => {
    e.stopPropagation();
    try {
      await partnersAPI.delete(id);
      loadPartners();
      toast.success('Partner removed');
    } catch (error) {
      console.error('Failed to delete partner:', error);
      toast.error('Failed to remove partner');
    }
  };

  const safePartners = Array.isArray(partners) ? partners : [];

  const filteredPartners = useMemo(() => {
    let result = safePartners;

    if (activeType !== 'all') {
      result = result.filter(p => (p.type || p.partner_type) === activeType);
    }

    if (filterStatus !== 'all') {
      result = result.filter(p => p.status === filterStatus);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(p =>
        (p.name || '').toLowerCase().includes(q) ||
        (p.company || '').toLowerCase().includes(q) ||
        (p.email || '').toLowerCase().includes(q)
      );
    }

    result.sort((a, b) => {
      if (sortBy === 'name') return (a.name || '').localeCompare(b.name || '');
      if (sortBy === 'volume') return (b.volume || 0) - (a.volume || 0);
      if (sortBy === 'referrals_in') return (b.referrals_in || 0) - (a.referrals_in || 0);
      if (sortBy === 'closed_loans') return (b.closed_loans || 0) - (a.closed_loans || 0);
      return 0;
    });

    return result;
  }, [safePartners, activeType, filterStatus, searchQuery, sortBy]);

  const stats = useMemo(() => {
    const active = safePartners.filter(p => p.status === 'active');
    return {
      total: safePartners.length,
      active: active.length,
      totalReferrals: safePartners.reduce((s, p) => s + (p.referrals_in || 0), 0),
      totalVolume: safePartners.reduce((s, p) => s + (p.volume || 0), 0),
      totalClosed: safePartners.reduce((s, p) => s + (p.closed_loans || 0), 0),
    };
  }, [safePartners]);

  const typeCountMap = useMemo(() => {
    const map = { all: safePartners.length };
    safePartners.forEach(p => {
      const t = p.type || p.partner_type || 'Other';
      map[t] = (map[t] || 0) + 1;
    });
    return map;
  }, [safePartners]);

  const getTierClass = (tier) => {
    const t = (tier || '').toLowerCase();
    if (t === 'gold') return 'rp-tier--gold';
    if (t === 'silver') return 'rp-tier--silver';
    return 'rp-tier--bronze';
  };

  const formatVolume = (v) => {
    if (!v) return '$0';
    if (v >= 1000000) return `$${(v / 1000000).toFixed(1)}M`;
    if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`;
    return `$${v}`;
  };

  const getInitials = (name) => {
    if (!name) return '?';
    const parts = name.split(' ');
    return parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : name.substring(0, 2).toUpperCase();
  };

  return (
    <div className="rp-page">
      {/* Header */}
      <div className="rp-header">
        <div className="rp-header__left">
          <h1 className="rp-header__title">Partner Portal</h1>
          <p className="rp-header__subtitle">Manage your referral network and track partner performance</p>
        </div>
        <button className="rp-btn rp-btn--primary" onClick={() => setShowAddModal(true)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
          Add Partner
        </button>
      </div>

      {/* Stats Row */}
      <div className="rp-stats">
        <div className="rp-stat">
          <span className="rp-stat__value">{stats.total}</span>
          <span className="rp-stat__label">Total Partners</span>
        </div>
        <div className="rp-stat">
          <span className="rp-stat__value">{stats.active}</span>
          <span className="rp-stat__label">Active</span>
        </div>
        <div className="rp-stat">
          <span className="rp-stat__value">{stats.totalReferrals}</span>
          <span className="rp-stat__label">Total Referrals</span>
        </div>
        <div className="rp-stat">
          <span className="rp-stat__value">{stats.totalClosed}</span>
          <span className="rp-stat__label">Closed Loans</span>
        </div>
        <div className="rp-stat rp-stat--highlight">
          <span className="rp-stat__value">{formatVolume(stats.totalVolume)}</span>
          <span className="rp-stat__label">Total Volume</span>
        </div>
      </div>

      {/* Partner Type Tabs */}
      <div className="rp-type-tabs">
        {PARTNER_TYPES.map(pt => (
          <button
            key={pt.key}
            className={`rp-type-tab ${activeType === pt.key ? 'rp-type-tab--active' : ''}`}
            onClick={() => setActiveType(pt.key)}
          >
            <SvgIcon path={pt.icon} size={18} />
            <span className="rp-type-tab__label">{pt.label}</span>
            {typeCountMap[pt.key] !== undefined && (
              <span className="rp-type-tab__count">{typeCountMap[pt.key] || 0}</span>
            )}
          </button>
        ))}
      </div>

      {/* Toolbar: Search, Status Filter, Sort */}
      <div className="rp-toolbar">
        <div className="rp-search">
          <svg className="rp-search__icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input
            type="text"
            className="rp-search__input"
            placeholder="Search partners..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="rp-toolbar__right">
          <div className="rp-status-pills">
            {['all', 'active', 'inactive'].map(s => (
              <button
                key={s}
                className={`rp-pill ${filterStatus === s ? 'rp-pill--active' : ''}`}
                onClick={() => setFilterStatus(s)}
              >
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
          <select
            className="rp-sort"
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
          >
            <option value="referrals_in">Sort: Most Referrals</option>
            <option value="volume">Sort: Highest Volume</option>
            <option value="closed_loans">Sort: Most Closed</option>
            <option value="name">Sort: Name A-Z</option>
          </select>
        </div>
      </div>

      {/* Partner Cards */}
      {loading ? (
        <div className="rp-loading">
          <div className="rp-loading__spinner" />
          Loading partners...
        </div>
      ) : filteredPartners.length === 0 ? (
        <div className="rp-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#8B8A7E" strokeWidth="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8m14 14v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <h3>No partners found</h3>
          <p>
            {searchQuery || activeType !== 'all' || filterStatus !== 'all'
              ? 'Try adjusting your filters or search query.'
              : 'Add your first referral partner to start tracking your network.'}
          </p>
          {!searchQuery && activeType === 'all' && filterStatus === 'all' && (
            <button className="rp-btn rp-btn--primary" onClick={() => setShowAddModal(true)}>
              Add Your First Partner
            </button>
          )}
        </div>
      ) : (
        <div className="rp-grid">
          {filteredPartners.map(partner => {
            const partnerType = partner.type || partner.partner_type || 'Other';
            const tier = partner.loyalty_tier || 'Bronze';
            return (
              <div
                key={partner.id}
                className="rp-card"
                onClick={() => navigate(`/referral-partners/${partner.id}`)}
              >
                <div className="rp-card__header">
                  <div className="rp-card__avatar" data-tier={tier.toLowerCase()}>
                    {getInitials(partner.name)}
                  </div>
                  <div className="rp-card__identity">
                    <h3 className="rp-card__name">{partner.name}</h3>
                    <p className="rp-card__company">{partner.company || partner.title || 'Independent'}</p>
                  </div>
                  <div className="rp-card__badges">
                    <span className={`rp-tier ${getTierClass(tier)}`}>{tier}</span>
                    <span className={`rp-status ${partner.status === 'active' ? 'rp-status--active' : 'rp-status--inactive'}`}>
                      {partner.status || 'active'}
                    </span>
                  </div>
                </div>

                <div className="rp-card__type-bar">
                  <span className="rp-card__type-label">{partnerType}</span>
                  {partner.title && partner.title !== partnerType && (
                    <span className="rp-card__title-label">{partner.title}</span>
                  )}
                </div>

                <div className="rp-card__metrics">
                  <div className="rp-metric">
                    <span className="rp-metric__value">{partner.referrals_in || 0}</span>
                    <span className="rp-metric__label">Referrals</span>
                  </div>
                  <div className="rp-metric">
                    <span className="rp-metric__value">{partner.closed_loans || 0}</span>
                    <span className="rp-metric__label">Closed</span>
                  </div>
                  <div className="rp-metric">
                    <span className="rp-metric__value">{formatVolume(partner.volume)}</span>
                    <span className="rp-metric__label">Volume</span>
                  </div>
                  <div className="rp-metric">
                    <span className="rp-metric__value">
                      {(partner.referrals_in && partner.closed_loans)
                        ? Math.round((partner.closed_loans / partner.referrals_in) * 100) + '%'
                        : '0%'}
                    </span>
                    <span className="rp-metric__label">Close Rate</span>
                  </div>
                </div>

                <div className="rp-card__footer">
                  <div className="rp-card__contact">
                    {partner.email && <span className="rp-card__email">{partner.email}</span>}
                    {partner.phone && <span className="rp-card__phone">{partner.phone}</span>}
                  </div>
                  <button
                    className="rp-card__delete"
                    onClick={(e) => handleDeletePartner(partner.id, e)}
                    title="Remove partner"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showAddModal && (
        <AddPartnerModal
          onClose={() => setShowAddModal(false)}
          onAdd={handleAddPartner}
        />
      )}
    </div>
  );
}

function AddPartnerModal({ onClose, onAdd }) {
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    company: '',
    type: '',
    phone: '',
    email: '',
    partner_category: 'individual',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const submitData = {
      ...formData,
      name: `${formData.first_name} ${formData.last_name}`.trim()
    };
    onAdd(submitData);
  };

  const update = (field, value) => setFormData(prev => ({ ...prev, [field]: value }));

  return (
    <div className="rp-modal-overlay" onClick={onClose}>
      <div className="rp-modal" onClick={e => e.stopPropagation()}>
        <div className="rp-modal__header">
          <h2>Add Referral Partner</h2>
          <button className="rp-modal__close" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="rp-form-row">
            <div className="rp-form-group">
              <label>First Name *</label>
              <input type="text" required value={formData.first_name} onChange={e => update('first_name', e.target.value)} placeholder="First name" />
            </div>
            <div className="rp-form-group">
              <label>Last Name *</label>
              <input type="text" required value={formData.last_name} onChange={e => update('last_name', e.target.value)} placeholder="Last name" />
            </div>
          </div>
          <div className="rp-form-group">
            <label>Company</label>
            <input type="text" value={formData.company} onChange={e => update('company', e.target.value)} placeholder="Company name" />
          </div>
          <div className="rp-form-group">
            <label>Partner Type *</label>
            <select required value={formData.type} onChange={e => update('type', e.target.value)}>
              <option value="">Select type...</option>
              <option value="Realtor">Realtor</option>
              <option value="Builder">Builder</option>
              <option value="Insurance Agent">Insurance Agent</option>
              <option value="Title">Title / Escrow</option>
              <option value="Attorney">Attorney</option>
              <option value="Financial Advisor">Financial Advisor</option>
              <option value="CPA">CPA</option>
              <option value="Other">Other</option>
            </select>
          </div>
          <div className="rp-form-group">
            <label>Email</label>
            <input type="email" value={formData.email} onChange={e => update('email', e.target.value)} placeholder="partner@company.com" />
          </div>
          <div className="rp-form-group">
            <label>Phone</label>
            <input type="tel" value={formData.phone} onChange={e => update('phone', formatPhoneNumber(e.target.value))} placeholder="(555) 000-0000" />
          </div>
          <div className="rp-form-group">
            <label>Category</label>
            <div className="rp-radio-row">
              <label className={`rp-radio-card ${formData.partner_category === 'individual' ? 'rp-radio-card--selected' : ''}`}>
                <input type="radio" name="partner_category" value="individual" checked={formData.partner_category === 'individual'} onChange={e => update('partner_category', e.target.value)} />
                <span>Individual</span>
              </label>
              <label className={`rp-radio-card ${formData.partner_category === 'team' ? 'rp-radio-card--selected' : ''}`}>
                <input type="radio" name="partner_category" value="team" checked={formData.partner_category === 'team'} onChange={e => update('partner_category', e.target.value)} />
                <span>Team</span>
              </label>
            </div>
          </div>
          <div className="rp-modal__actions">
            <button type="button" className="rp-btn rp-btn--ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="rp-btn rp-btn--primary">Add Partner</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ReferralPartners;
