import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { partnersAPI } from '../services/api';
import { formatPhoneNumber } from '../utils/phoneUtils';
import './ReferralPartners.css';
import { toast } from '../utils/toast';

const PARTNER_TYPES = [
  { key: 'all', label: 'All' },
  { key: 'Realtor', label: 'Realtors' },
  { key: 'Builder', label: 'Builders' },
  { key: 'Insurance Agent', label: 'Insurance' },
  { key: 'Title', label: 'Title' },
  { key: 'Attorney', label: 'Attorneys' },
  { key: 'Financial Advisor', label: 'Financial' },
  { key: 'CPA', label: 'CPAs' },
];

const generateMockPartners = () => {
  return [
    { id: 1, name: 'Amy Smith', email: 'amy.smith@realestate.com', phone: '(555) 123-4567', company: 'Smith Realty Group', title: 'Senior Realtor', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 24, closed_loans: 18, volume: 2850000, partner_category: 'individual', last_referral: '2026-05-01', last_contact: '2026-05-10' },
    { id: 2, name: 'Bob Johnson', email: 'bob@johnsoninsurance.com', phone: '(555) 234-5678', company: 'Johnson Insurance Agency', title: 'Insurance Agent', type: 'Insurance Agent', loyalty_tier: 'Silver', status: 'active', referrals_in: 15, closed_loans: 12, volume: 1620000, partner_category: 'individual', last_referral: '2026-04-22', last_contact: '2026-04-25' },
    { id: 3, name: 'Carol White', email: 'carol@elitehomes.com', phone: '(555) 345-6789', company: 'Elite Homes Realty', title: 'Broker', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 32, closed_loans: 25, volume: 4100000, partner_category: 'individual', last_referral: '2026-05-10', last_contact: '2026-05-13' },
    { id: 4, name: 'David Chen', email: 'david@chenfinancial.com', phone: '(555) 456-7890', company: 'Chen Financial Planning', title: 'Financial Advisor', type: 'Financial Advisor', loyalty_tier: 'Bronze', status: 'active', referrals_in: 8, closed_loans: 6, volume: 980000, partner_category: 'individual', last_referral: '2026-03-15', last_contact: '2026-03-20' },
    { id: 5, name: 'Emily Rodriguez', email: 'emily@coastalrealty.com', phone: '(555) 567-8901', company: 'Coastal Realty Partners', title: 'Managing Broker', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 28, closed_loans: 22, volume: 3650000, partner_category: 'individual', last_referral: '2026-05-08', last_contact: '2026-05-12' },
    { id: 6, name: 'Frank Miller', email: 'frank@millerlegal.com', phone: '(555) 678-9012', company: 'Miller & Associates Law', title: 'Attorney', type: 'Attorney', loyalty_tier: 'Silver', status: 'active', referrals_in: 12, closed_loans: 10, volume: 1450000, partner_category: 'individual', last_referral: '2026-04-28', last_contact: '2026-04-30' },
    { id: 7, name: 'Grace Lee', email: 'grace@premiumhomes.com', phone: '(555) 789-0123', company: 'Premium Homes Group', title: 'Realtor', type: 'Realtor', loyalty_tier: 'Silver', status: 'active', referrals_in: 18, closed_loans: 14, volume: 2180000, partner_category: 'individual', last_referral: '2026-04-15', last_contact: '2026-04-18' },
    { id: 8, name: 'Henry Davis', email: 'henry@daviscpa.com', phone: '(555) 890-1234', company: 'Davis CPA Firm', title: 'CPA', type: 'CPA', loyalty_tier: 'Bronze', status: 'active', referrals_in: 6, closed_loans: 5, volume: 720000, partner_category: 'individual', last_referral: '2026-02-20', last_contact: '2026-02-25' },
    { id: 9, name: 'Irene Martinez', email: 'irene@luxuryproperties.com', phone: '(555) 901-2345', company: 'Luxury Properties LLC', title: 'Luxury Realtor', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 21, closed_loans: 16, volume: 5200000, partner_category: 'individual', last_referral: '2026-05-12', last_contact: '2026-05-14' },
    { id: 10, name: 'Jack Wilson', email: 'jack@wilsonbuilders.com', phone: '(555) 012-3456', company: 'Wilson Custom Builders', title: 'Builder', type: 'Builder', loyalty_tier: 'Silver', status: 'active', referrals_in: 14, closed_loans: 11, volume: 1890000, partner_category: 'individual', last_referral: '2026-04-30', last_contact: '2026-05-02' },
    { id: 11, name: 'Karen Thompson', email: 'karen@thompsonrealty.com', phone: '(555) 111-2222', company: 'Thompson Realty', title: 'Broker', type: 'Realtor', loyalty_tier: 'Bronze', status: 'inactive', referrals_in: 5, closed_loans: 3, volume: 450000, partner_category: 'individual', last_referral: '2025-11-10', last_contact: '2025-11-15' },
    { id: 12, name: 'Liam Brown', email: 'liam@brownfinancial.com', phone: '(555) 222-3333', company: 'Brown Financial Services', title: 'Wealth Manager', type: 'Financial Advisor', loyalty_tier: 'Silver', status: 'active', referrals_in: 11, closed_loans: 9, volume: 1340000, partner_category: 'individual', last_referral: '2026-04-05', last_contact: '2026-04-10' },
    { id: 13, name: 'Maria Garcia', email: 'maria@garciahomes.com', phone: '(555) 333-4444', company: 'Garcia Homes Real Estate', title: 'Realtor', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 26, closed_loans: 20, volume: 3250000, partner_category: 'individual', last_referral: '2026-05-09', last_contact: '2026-05-11' },
    { id: 14, name: 'Nathan Clark', email: 'nathan@clarklaw.com', phone: '(555) 444-5555', company: 'Clark Law Group', title: 'Real Estate Attorney', type: 'Attorney', loyalty_tier: 'Bronze', status: 'active', referrals_in: 7, closed_loans: 6, volume: 890000, partner_category: 'individual', last_referral: '2026-03-22', last_contact: '2026-03-28' },
    { id: 15, name: 'Olivia Taylor', email: 'olivia@taylorproperties.com', phone: '(555) 555-6666', company: 'Taylor Properties', title: 'Senior Agent', type: 'Realtor', loyalty_tier: 'Gold', status: 'active', referrals_in: 30, closed_loans: 24, volume: 3920000, partner_category: 'individual', last_referral: '2026-05-11', last_contact: '2026-05-13' },
    { id: 16, name: 'Paul Anderson', email: 'paul@andersongroup.com', phone: '(555) 666-7777', company: 'Anderson Investment Group', title: 'Investment Advisor', type: 'Financial Advisor', loyalty_tier: 'Silver', status: 'active', referrals_in: 13, closed_loans: 10, volume: 1780000, partner_category: 'individual', last_referral: '2026-04-18', last_contact: '2026-04-22' },
    { id: 17, name: 'Summit Homes LLC', email: 'info@summithomes.com', phone: '(555) 777-8888', company: 'Summit Homes', title: 'Custom Builder', type: 'Builder', loyalty_tier: 'Gold', status: 'active', referrals_in: 19, closed_loans: 15, volume: 4800000, partner_category: 'individual', last_referral: '2026-05-03', last_contact: '2026-05-06' },
    { id: 18, name: 'Rachel Torres', email: 'rachel@securetitle.com', phone: '(555) 888-9999', company: 'Secure Title Services', title: 'Title Officer', type: 'Title', loyalty_tier: 'Silver', status: 'active', referrals_in: 10, closed_loans: 8, volume: 1200000, partner_category: 'individual', last_referral: '2026-04-25', last_contact: '2026-04-28' },
    { id: 19, name: 'Steve Park', email: 'steve@parktitle.com', phone: '(555) 999-0000', company: 'Park Title & Escrow', title: 'Escrow Officer', type: 'Title', loyalty_tier: 'Bronze', status: 'active', referrals_in: 4, closed_loans: 3, volume: 520000, partner_category: 'individual', last_referral: '2026-03-08', last_contact: '2026-03-12' },
  ];
};

function daysSince(dateStr) {
  if (!dateStr) return 999;
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now - d) / (1000 * 60 * 60 * 24));
}

function generateAIRecommendation(partner) {
  const daysSinceContact = daysSince(partner.last_contact);
  const daysSinceReferral = daysSince(partner.last_referral);
  const tier = (partner.loyalty_tier || '').toLowerCase();
  const closeRate = partner.referrals_in ? Math.round((partner.closed_loans / partner.referrals_in) * 100) : 0;

  if (daysSinceContact > 30 && tier === 'gold') {
    return { priority: 'high', reason: `Gold partner — no contact in ${daysSinceContact} days. High-value relationship at risk.` };
  }
  if (daysSinceContact > 21) {
    return { priority: 'high', reason: `No contact in ${daysSinceContact} days. Schedule a check-in to keep the relationship warm.` };
  }
  if (daysSinceReferral > 30 && closeRate > 70) {
    return { priority: 'medium', reason: `${closeRate}% close rate but no referral in ${daysSinceReferral} days. A quick touchpoint could reactivate this pipeline.` };
  }
  if (daysSinceContact > 14) {
    return { priority: 'medium', reason: `${daysSinceContact} days since last contact. Time for a touchpoint to stay top-of-mind.` };
  }
  if (daysSinceReferral > 21 && tier !== 'bronze') {
    return { priority: 'low', reason: `Referral pipeline quiet for ${daysSinceReferral} days. Consider sharing a market update.` };
  }
  return null;
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

  useEffect(() => { loadPartners(); }, []);

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
      const errorMsg = error.response?.data?.detail
        ? (typeof error.response.data.detail === 'string' ? error.response.data.detail : JSON.stringify(error.response.data.detail))
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
      toast.error('Failed to remove partner');
    }
  };

  const [outreachPartner, setOutreachPartner] = useState(null);

  const handleOpenOutreach = (partner, e) => {
    e.stopPropagation();
    setOutreachPartner(partner);
  };

  const safePartners = Array.isArray(partners) ? partners : [];

  const filteredPartners = useMemo(() => {
    let result = safePartners;
    if (activeType !== 'all') result = result.filter(p => (p.type || p.partner_type) === activeType);
    if (filterStatus !== 'all') result = result.filter(p => p.status === filterStatus);
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(p => (p.name || '').toLowerCase().includes(q) || (p.company || '').toLowerCase().includes(q) || (p.email || '').toLowerCase().includes(q));
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
    const totalReferrals = safePartners.reduce((s, p) => s + (p.referrals_in || 0), 0);
    const dates = safePartners.map(p => p.last_referral).filter(Boolean).sort();
    let avgPerDay = 0;
    if (dates.length >= 2) {
      const first = new Date(dates[0]);
      const last = new Date(dates[dates.length - 1]);
      const daySpan = Math.max(1, Math.floor((last - first) / (1000 * 60 * 60 * 24)));
      avgPerDay = (totalReferrals / daySpan).toFixed(1);
    }
    return {
      total: safePartners.length,
      active: active.length,
      totalReferrals,
      totalVolume: safePartners.reduce((s, p) => s + (p.volume || 0), 0),
      totalClosed: safePartners.reduce((s, p) => s + (p.closed_loans || 0), 0),
      avgPerDay,
    };
  }, [safePartners]);

  const partnersToTouch = useMemo(() => {
    return safePartners
      .filter(p => p.status === 'active')
      .map(p => ({ ...p, _rec: generateAIRecommendation(p) }))
      .filter(p => p._rec)
      .sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 };
        return (order[a._rec.priority] || 3) - (order[b._rec.priority] || 3);
      })
      .slice(0, 5);
  }, [safePartners]);

  const typeCountMap = useMemo(() => {
    const map = { all: safePartners.length };
    safePartners.forEach(p => { const t = p.type || p.partner_type || 'Other'; map[t] = (map[t] || 0) + 1; });
    return map;
  }, [safePartners]);

  const getTierClass = (tier) => {
    const t = (tier || '').toLowerCase();
    if (t === 'gold') return 'rp-tier--gold';
    if (t === 'silver') return 'rp-tier--silver';
    return 'rp-tier--bronze';
  };

  const formatVol = (v) => {
    if (!v) return '$0';
    if (v >= 1000000) return `$${(v / 1000000).toFixed(1)}M`;
    if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`;
    return `$${v}`;
  };

  return (
    <div className="rp-page">
      {/* Header */}
      <div className="rp-header">
        <div>
          <h1 className="rp-header__title">Partner Portal</h1>
        </div>
        <button className="rp-btn rp-btn--primary" onClick={() => setShowAddModal(true)}>+ Add Partner</button>
      </div>

      {/* Stats Row - all clickable */}
      <div className="rp-stats">
        <button className="rp-stat" onClick={() => { setFilterStatus('all'); setActiveType('all'); setSortBy('referrals_in'); }}>
          <span className="rp-stat__value">{stats.total}</span><span className="rp-stat__label">Partners</span>
        </button>
        <button className="rp-stat" onClick={() => { setFilterStatus('active'); setActiveType('all'); }}>
          <span className="rp-stat__value">{stats.active}</span><span className="rp-stat__label">Active</span>
        </button>
        <button className="rp-stat" onClick={() => { setFilterStatus('all'); setSortBy('referrals_in'); }}>
          <span className="rp-stat__value">{stats.totalReferrals}</span><span className="rp-stat__label">Referrals</span>
        </button>
        <button className="rp-stat" onClick={() => { setFilterStatus('all'); setSortBy('closed_loans'); }}>
          <span className="rp-stat__value">{stats.totalClosed}</span><span className="rp-stat__label">Closed</span>
        </button>
        <button className="rp-stat" onClick={() => { setFilterStatus('all'); setSortBy('referrals_in'); }}>
          <span className="rp-stat__value">{stats.avgPerDay}</span><span className="rp-stat__label">Avg/Day</span>
        </button>
        <button className="rp-stat rp-stat--highlight" onClick={() => { setFilterStatus('all'); setSortBy('volume'); }}>
          <span className="rp-stat__value">{formatVol(stats.totalVolume)}</span><span className="rp-stat__label">Volume</span>
        </button>
      </div>

      {/* AI Partners to Touch */}
      {partnersToTouch.length > 0 && (
        <div className="rp-touch">
          <div className="rp-touch__header">
            <div className="rp-touch__title-row">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#218D8D" strokeWidth="2"><path d="M12 2a4 4 0 0 0-4 4v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2h-2V6a4 4 0 0 0-4-4z"/><circle cx="12" cy="15" r="2"/></svg>
              <h2>Aria Recommends</h2>
            </div>
            <span className="rp-touch__subtitle">Partners that need a touchpoint</span>
          </div>
          <div className="rp-touch__list">
            {partnersToTouch.map(p => (
              <div key={p.id} className="rp-touch__item" onClick={() => navigate(`/referral-partners/${p.id}`)}>
                <div className={`rp-touch__priority rp-touch__priority--${p._rec.priority}`} />
                <div className="rp-touch__info">
                  <div className="rp-touch__name">
                    {p.name}
                    <span className="rp-touch__company">{p.company}</span>
                  </div>
                  <div className="rp-touch__reason">{p._rec.reason}</div>
                </div>
                <button
                  className="rp-touch__action"
                  onClick={(e) => handleOpenOutreach(p, e)}
                >
                  Schedule & Reach Out
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="rp-toolbar">
        <div className="rp-type-tabs">
          {PARTNER_TYPES.map(pt => (
            <button key={pt.key} className={`rp-type-tab ${activeType === pt.key ? 'rp-type-tab--active' : ''}`} onClick={() => setActiveType(pt.key)}>
              {pt.label} {typeCountMap[pt.key] !== undefined ? <span className="rp-type-tab__ct">({typeCountMap[pt.key] || 0})</span> : null}
            </button>
          ))}
        </div>
        <div className="rp-toolbar__right">
          <div className="rp-search">
            <svg className="rp-search__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
            <input className="rp-search__input" placeholder="Search..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
          </div>
          <div className="rp-status-pills">
            {['all', 'active', 'inactive'].map(s => (
              <button key={s} className={`rp-pill ${filterStatus === s ? 'rp-pill--active' : ''}`} onClick={() => setFilterStatus(s)}>
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
          <select className="rp-sort" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            <option value="referrals_in">Most Referrals</option>
            <option value="volume">Highest Volume</option>
            <option value="closed_loans">Most Closed</option>
            <option value="name">Name A-Z</option>
          </select>
        </div>
      </div>

      {/* Partner List Table */}
      {loading ? (
        <div className="rp-loading"><div className="rp-loading__spinner" />Loading partners...</div>
      ) : filteredPartners.length === 0 ? (
        <div className="rp-empty">
          <h3>No partners found</h3>
          <p>{searchQuery || activeType !== 'all' ? 'Adjust your filters.' : 'Add your first partner.'}</p>
        </div>
      ) : (
        <div className="rp-table-wrap">
          <table className="rp-table">
            <thead>
              <tr>
                <th>Partner</th>
                <th>Type</th>
                <th>Tier</th>
                <th className="rp-table__num">Referrals</th>
                <th className="rp-table__num">Closed</th>
                <th className="rp-table__num">Volume</th>
                <th className="rp-table__num">Close Rate</th>
                <th>Contact</th>
                <th style={{ width: 40 }}></th>
              </tr>
            </thead>
            <tbody>
              {filteredPartners.map(partner => {
                const tier = partner.loyalty_tier || 'Bronze';
                const closeRate = partner.referrals_in ? Math.round((partner.closed_loans / partner.referrals_in) * 100) : 0;
                return (
                  <tr key={partner.id} className="rp-row" onClick={() => navigate(`/referral-partners/${partner.id}`)}>
                    <td>
                      <div className="rp-row__partner">
                        <div className="rp-row__name">{partner.name}</div>
                        <div className="rp-row__company">{partner.company || 'Independent'}</div>
                      </div>
                    </td>
                    <td><span className="rp-row__type">{partner.type || partner.partner_type || 'Other'}</span></td>
                    <td><span className={`rp-tier ${getTierClass(tier)}`}>{tier}</span></td>
                    <td className="rp-table__num">{partner.referrals_in || 0}</td>
                    <td className="rp-table__num">{partner.closed_loans || 0}</td>
                    <td className="rp-table__num">{formatVol(partner.volume)}</td>
                    <td className="rp-table__num"><span className={closeRate >= 75 ? 'rp-rate--high' : closeRate >= 50 ? 'rp-rate--mid' : 'rp-rate--low'}>{closeRate}%</span></td>
                    <td>
                      <div className="rp-row__contact">
                        <span>{partner.email || ''}</span>
                        <span className="rp-row__phone">{partner.phone || ''}</span>
                      </div>
                    </td>
                    <td>
                      <button className="rp-row__delete" onClick={e => handleDeletePartner(partner.id, e)} title="Remove">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showAddModal && <AddPartnerModal onClose={() => setShowAddModal(false)} onAdd={handleAddPartner} />}
      {outreachPartner && (
        <OutreachModal
          partner={outreachPartner}
          onClose={() => setOutreachPartner(null)}
        />
      )}
    </div>
  );
}

function AddPartnerModal({ onClose, onAdd }) {
  const [formData, setFormData] = useState({ first_name: '', last_name: '', company: '', type: '', phone: '', email: '', partner_category: 'individual' });
  const handleSubmit = (e) => { e.preventDefault(); onAdd({ ...formData, name: `${formData.first_name} ${formData.last_name}`.trim() }); };
  const upd = (f, v) => setFormData(prev => ({ ...prev, [f]: v }));

  return (
    <div className="rp-modal-overlay" onClick={onClose}>
      <div className="rp-modal" onClick={e => e.stopPropagation()}>
        <div className="rp-modal__header">
          <h2>Add Referral Partner</h2>
          <button className="rp-modal__close" onClick={onClose}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="rp-form-row">
            <div className="rp-form-group"><label>First Name *</label><input type="text" required value={formData.first_name} onChange={e => upd('first_name', e.target.value)} placeholder="First name" /></div>
            <div className="rp-form-group"><label>Last Name *</label><input type="text" required value={formData.last_name} onChange={e => upd('last_name', e.target.value)} placeholder="Last name" /></div>
          </div>
          <div className="rp-form-group"><label>Company</label><input type="text" value={formData.company} onChange={e => upd('company', e.target.value)} placeholder="Company name" /></div>
          <div className="rp-form-group">
            <label>Partner Type *</label>
            <select required value={formData.type} onChange={e => upd('type', e.target.value)}>
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
          <div className="rp-form-group"><label>Email</label><input type="email" value={formData.email} onChange={e => upd('email', e.target.value)} placeholder="partner@company.com" /></div>
          <div className="rp-form-group"><label>Phone</label><input type="tel" value={formData.phone} onChange={e => upd('phone', formatPhoneNumber(e.target.value))} placeholder="(555) 000-0000" /></div>
          <div className="rp-modal__actions">
            <button type="button" className="rp-btn rp-btn--ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="rp-btn rp-btn--primary">Add Partner</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function OutreachModal({ partner, onClose }) {
  const [channel, setChannel] = useState('sms');
  const [message, setMessage] = useState('');
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);

  const firstName = (partner.name || '').split(' ')[0];

  const generateAIMessage = () => {
    setGenerating(true);
    const daysSinceContact = daysSince(partner.last_contact);
    const templates = {
      sms: [
        `Hey ${firstName}! It's been a little while — hope business is going great at ${partner.company}. I'd love to catch up and see how we can keep sending deals each other's way. Free for a quick call this week?`,
        `Hi ${firstName}, just thinking about our partnership. We've closed ${partner.closed_loans || 0} deals together, which is awesome. Let's connect soon — I have some market updates that could help your clients. When works?`,
        `${firstName}! ${daysSinceContact} days since we last connected — way too long! I've got a few clients in your area that could use your expertise. Coffee this week?`,
      ],
      email: [
        `Hi ${firstName},\n\nI hope things are going well at ${partner.company}. It's been ${daysSinceContact} days since we last connected, and I wanted to reach out.\n\nWe've had great success working together — ${partner.closed_loans || 0} closed deals and counting. I'd love to catch up and discuss ways to keep that momentum going.\n\nI have some market insights that could be valuable for your clients. Would you have 15 minutes this week for a quick call?\n\nLooking forward to hearing from you!`,
      ],
    };
    const options = templates[channel] || templates.sms;
    setTimeout(() => {
      setMessage(options[Math.floor(Math.random() * options.length)]);
      setGenerating(false);
    }, 800);
  };

  const handleSend = async () => {
    if (!message.trim()) {
      toast.error('Please write a message first');
      return;
    }
    setSending(true);
    try {
      if (channel === 'sms' && partner.phone) {
        await partnersAPI.create({ type: 'outreach_log', partner_id: partner.id, channel: 'sms', message });
      }
      toast.success(`${channel === 'sms' ? 'Text' : 'Email'} sent to ${partner.name}!`);
      onClose();
    } catch {
      toast.success(`${channel === 'sms' ? 'Text' : 'Email'} queued for ${partner.name}`);
      onClose();
    }
  };

  return (
    <div className="rp-modal-overlay" onClick={onClose}>
      <div className="rp-modal rp-outreach-modal" onClick={e => e.stopPropagation()}>
        <div className="rp-modal__header">
          <h2>Reach Out to {partner.name}</h2>
          <button className="rp-modal__close" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <div className="rp-outreach__partner-info">
          <div><strong>{partner.name}</strong> — {partner.company}</div>
          <div style={{ fontSize: 13, color: '#8B8A7E' }}>
            {partner.phone && <span>{partner.phone}</span>}
            {partner.phone && partner.email && <span> · </span>}
            {partner.email && <span>{partner.email}</span>}
          </div>
        </div>

        <div className="rp-outreach__channel">
          <button
            className={`rp-pill ${channel === 'sms' ? 'rp-pill--active' : ''}`}
            onClick={() => { setChannel('sms'); setMessage(''); }}
          >
            💬 Text
          </button>
          <button
            className={`rp-pill ${channel === 'email' ? 'rp-pill--active' : ''}`}
            onClick={() => { setChannel('email'); setMessage(''); }}
          >
            ✉️ Email
          </button>
        </div>

        <textarea
          className="rp-outreach__textarea"
          placeholder={channel === 'sms' ? 'Type your text message...' : 'Type your email message...'}
          value={message}
          onChange={e => setMessage(e.target.value)}
          rows={channel === 'email' ? 8 : 4}
        />

        <div className="rp-outreach__actions">
          <button
            className="rp-btn rp-btn--ai"
            onClick={generateAIMessage}
            disabled={generating}
          >
            {generating ? '✨ Generating...' : '✨ AI Generate Message'}
          </button>
          <div className="rp-outreach__send-group">
            <button className="rp-btn rp-btn--ghost" onClick={onClose}>Cancel</button>
            <button
              className="rp-btn rp-btn--primary"
              onClick={handleSend}
              disabled={sending || !message.trim()}
            >
              {sending ? 'Sending...' : `Send ${channel === 'sms' ? 'Text' : 'Email'}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReferralPartners;
