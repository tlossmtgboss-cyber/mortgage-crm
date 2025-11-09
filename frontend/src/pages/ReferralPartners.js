import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { partnersAPI } from '../services/api';
import './ReferralPartners.css';

function ReferralPartners() {
  const navigate = useNavigate();
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
      // Ensure data is always an array
      setPartners(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load referral partners:', error);
      // Set empty array on error
      setPartners([]);
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

  const handleDeletePartner = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this referral partner?')) return;
    try {
      await partnersAPI.delete(id);
      loadPartners();
    } catch (error) {
      console.error('Failed to delete partner:', error);
    }
  };

  // Ensure partners is always an array before filtering
  const safePartners = Array.isArray(partners) ? partners : [];
  const filteredPartners = filterStatus === 'all'
    ? safePartners
    : safePartners.filter(p => p.status === filterStatus);

  const getTierBadgeClass = (tier) => {
    const tierMap = {
      gold: 'tier-gold',
      silver: 'tier-silver',
      bronze: 'tier-bronze',
    };
    return tierMap[tier?.toLowerCase()] || 'tier-bronze';
  };

  return (
    <div className="referral-partners-page">
      <div className="page-header">
        <div>
          <h1>Referral Partners</h1>
          <p>{safePartners.length} total partners</p>
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
          All ({safePartners.length})
        </button>
        <button
          className={filterStatus === 'active' ? 'active' : ''}
          onClick={() => setFilterStatus('active')}
        >
          Active ({safePartners.filter(p => p.status === 'active').length})
        </button>
        <button
          className={filterStatus === 'inactive' ? 'active' : ''}
          onClick={() => setFilterStatus('inactive')}
        >
          Inactive ({safePartners.filter(p => p.status === 'inactive').length})
        </button>
      </div>

      {loading ? (
        <div className="loading">Loading partners...</div>
      ) : (
        <div className="partners-list">
          <table className="partners-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Company</th>
                <th>Type</th>
                <th>Tier</th>
                <th>Contact</th>
                <th>Referrals In</th>
                <th>Closed Loans</th>
                <th>Volume</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredPartners.map((partner) => (
                <tr
                  key={partner.id}
                  className="partner-row"
                  onClick={() => navigate(`/referral-partners/${partner.id}`)}
                >
                  <td className="partner-name">{partner.name}</td>
                  <td>{partner.company || 'N/A'}</td>
                  <td>{partner.type || 'N/A'}</td>
                  <td>
                    <span className={`tier-badge ${getTierBadgeClass(partner.loyalty_tier)}`}>
                      {partner.loyalty_tier || 'Bronze'}
                    </span>
                  </td>
                  <td>
                    <div className="contact-info">
                      <div>{partner.email || 'N/A'}</div>
                      <div className="phone">{partner.phone || 'N/A'}</div>
                    </div>
                  </td>
                  <td className="stat-cell">{partner.referrals_in || 0}</td>
                  <td className="stat-cell">{partner.closed_loans || 0}</td>
                  <td className="stat-cell">
                    ${((partner.volume || 0) / 1000000).toFixed(1)}M
                  </td>
                  <td>
                    <button
                      className="btn-delete-small"
                      onClick={(e) => handleDeletePartner(partner.id, e)}
                      title="Delete"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredPartners.length === 0 && (
            <div className="empty-state">
              No referral partners found. Add your first partner to start tracking referrals.
            </div>
          )}
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
