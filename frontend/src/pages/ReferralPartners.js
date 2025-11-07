import { useState, useEffect } from 'react';
import { partnersAPI } from '../services/api';
import './ReferralPartners.css';

function ReferralPartners() {
  const [partners, setPartners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');

  useEffect(() => {
    loadPartners();
  }, []);

  const loadPartners = async () => {
    try {
      setLoading(true);
      const data = await partnersAPI.getAll();
      setPartners(data);
    } catch (error) {
      console.error('Failed to load referral partners:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddPartner = async (partnerData) => {
    try {
      await partnersAPI.create(partnerData);
      loadPartners();
      setShowAddModal(false);
    } catch (error) {
      console.error('Failed to create partner:', error);
      alert('Failed to create referral partner. Please try again.');
    }
  };

  const handleDeletePartner = async (id) => {
    if (!window.confirm('Delete this referral partner?')) return;
    try {
      await partnersAPI.delete(id);
      loadPartners();
    } catch (error) {
      console.error('Failed to delete partner:', error);
    }
  };

  const filteredPartners = filterStatus === 'all'
    ? partners
    : partners.filter(p => p.status === filterStatus);

  const getTierBadgeClass = (tier) => {
    const tierMap = {
      gold: 'tier-gold',
      silver: 'tier-silver',
      bronze: 'tier-bronze',
    };
    return tierMap[tier] || 'tier-bronze';
  };

  return (
    <div className="referral-partners-page">
      <div className="page-header">
        <div>
          <h1>Referral Partners</h1>
          <p>{partners.length} total partners</p>
        </div>
        <button className="btn-add" onClick={() => setShowAddModal(true)}>
          + Add Partner
        </button>
      </div>

      <div className="filter-bar">
        <button
          className={filterStatus === 'all' ? 'active' : ''}
          onClick={() => setFilterStatus('all')}
        >
          All ({partners.length})
        </button>
        <button
          className={filterStatus === 'active' ? 'active' : ''}
          onClick={() => setFilterStatus('active')}
        >
          Active ({partners.filter(p => p.status === 'active').length})
        </button>
        <button
          className={filterStatus === 'inactive' ? 'active' : ''}
          onClick={() => setFilterStatus('inactive')}
        >
          Inactive ({partners.filter(p => p.status === 'inactive').length})
        </button>
      </div>

      {loading ? (
        <div className="loading">Loading partners...</div>
      ) : (
        <div className="partners-grid">
          {filteredPartners.map((partner) => (
            <div key={partner.id} className="partner-card">
              <div className="partner-header">
                <div>
                  <h3>{partner.name}</h3>
                  <p className="company">{partner.company || 'No company'}</p>
                </div>
                <span className={`tier-badge ${getTierBadgeClass(partner.loyalty_tier)}`}>
                  {partner.loyalty_tier}
                </span>
              </div>

              <div className="partner-details">
                <div className="detail-item">
                  <label>Type</label>
                  <p>{partner.type || 'N/A'}</p>
                </div>
                <div className="detail-item">
                  <label>Email</label>
                  <p>{partner.email || 'N/A'}</p>
                </div>
                <div className="detail-item">
                  <label>Phone</label>
                  <p>{partner.phone || 'N/A'}</p>
                </div>
              </div>

              <div className="partner-stats">
                <div className="stat">
                  <span className="stat-value">{partner.referrals_in}</span>
                  <span className="stat-label">Referrals In</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{partner.closed_loans}</span>
                  <span className="stat-label">Closed Loans</span>
                </div>
                <div className="stat">
                  <span className="stat-value">${(partner.volume / 1000000).toFixed(1)}M</span>
                  <span className="stat-label">Volume</span>
                </div>
              </div>

              <div className="partner-actions">
                <button className="btn-view">View Details</button>
                <button
                  className="btn-delete"
                  onClick={() => handleDeletePartner(partner.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
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
    name: '',
    company: '',
    type: '',
    phone: '',
    email: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onAdd(formData);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Add Referral Partner</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Name *</label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Company</label>
            <input
              type="text"
              value={formData.company}
              onChange={(e) => setFormData({ ...formData, company: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Type</label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
            >
              <option value="">Select type...</option>
              <option value="Real Estate Agent">Real Estate Agent</option>
              <option value="Builder">Builder</option>
              <option value="Financial Advisor">Financial Advisor</option>
              <option value="CPA">CPA</option>
              <option value="Attorney">Attorney</option>
              <option value="Other">Other</option>
            </select>
          </div>
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Add Partner</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ReferralPartners;
