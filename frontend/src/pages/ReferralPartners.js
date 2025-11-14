import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { partnersAPI } from '../services/api';
import './ReferralPartners.css';

// Mock referral partners data
const generateMockPartners = () => {
  return [
    { id: 1, name: 'Amy Smith', email: 'amy.smith@realestate.com', phone: '(555) 123-4567', company: 'Smith Realty Group', title: 'Senior Realtor', partner_type: 'Realtor', tier: 'Gold', status: 'active', total_referrals: 24, closed_deals: 18, pipeline_value: 2850000, partner_category: 'individual' },
    { id: 2, name: 'Bob Johnson', email: 'bob@johnsoninsurance.com', phone: '(555) 234-5678', company: 'Johnson Insurance Agency', title: 'Insurance Agent', partner_type: 'Insurance Agent', tier: 'Silver', status: 'active', total_referrals: 15, closed_deals: 12, pipeline_value: 1620000, partner_category: 'individual' },
    { id: 3, name: 'Carol White', email: 'carol@elitehomes.com', phone: '(555) 345-6789', company: 'Elite Homes Realty', title: 'Broker', partner_type: 'Realtor', tier: 'Gold', status: 'active', total_referrals: 32, closed_deals: 25, pipeline_value: 4100000, partner_category: 'individual' },
    { id: 4, name: 'David Chen', email: 'david@chenfinancial.com', phone: '(555) 456-7890', company: 'Chen Financial Planning', title: 'Financial Advisor', partner_type: 'Financial Advisor', tier: 'Bronze', status: 'active', total_referrals: 8, closed_deals: 6, pipeline_value: 980000, partner_category: 'individual' },
    { id: 5, name: 'Emily Rodriguez', email: 'emily@coastalrealty.com', phone: '(555) 567-8901', company: 'Coastal Realty Partners', title: 'Managing Broker', partner_type: 'Realtor', tier: 'Gold', status: 'active', total_referrals: 28, closed_deals: 22, pipeline_value: 3650000, partner_category: 'individual' },
    { id: 6, name: 'Frank Miller', email: 'frank@millerlegal.com', phone: '(555) 678-9012', company: 'Miller & Associates Law', title: 'Attorney', partner_type: 'Attorney', tier: 'Silver', status: 'active', total_referrals: 12, closed_deals: 10, pipeline_value: 1450000, partner_category: 'individual' },
    { id: 7, name: 'Grace Lee', email: 'grace@premiumhomes.com', phone: '(555) 789-0123', company: 'Premium Homes Group', title: 'Realtor', partner_type: 'Realtor', tier: 'Silver', status: 'active', total_referrals: 18, closed_deals: 14, pipeline_value: 2180000, partner_category: 'individual' },
    { id: 8, name: 'Henry Davis', email: 'henry@daviscpa.com', phone: '(555) 890-1234', company: 'Davis CPA Firm', title: 'CPA', partner_type: 'CPA', tier: 'Bronze', status: 'active', total_referrals: 6, closed_deals: 5, pipeline_value: 720000, partner_category: 'individual' },
    { id: 9, name: 'Irene Martinez', email: 'irene@luxuryproperties.com', phone: '(555) 901-2345', company: 'Luxury Properties LLC', title: 'Luxury Realtor', partner_type: 'Realtor', tier: 'Gold', status: 'active', total_referrals: 21, closed_deals: 16, pipeline_value: 5200000, partner_category: 'individual' },
    { id: 10, name: 'Jack Wilson', email: 'jack@wilsonbuilders.com', phone: '(555) 012-3456', company: 'Wilson Custom Builders', title: 'Builder', partner_type: 'Builder', tier: 'Silver', status: 'active', total_referrals: 14, closed_deals: 11, pipeline_value: 1890000, partner_category: 'individual' },
    { id: 11, name: 'Karen Thompson', email: 'karen@thompsonrealty.com', phone: '(555) 111-2222', company: 'Thompson Realty', title: 'Broker', partner_type: 'Realtor', tier: 'Bronze', status: 'inactive', total_referrals: 5, closed_deals: 3, pipeline_value: 450000, partner_category: 'individual' },
    { id: 12, name: 'Liam Brown', email: 'liam@brownfinancial.com', phone: '(555) 222-3333', company: 'Brown Financial Services', title: 'Wealth Manager', partner_type: 'Financial Advisor', tier: 'Silver', status: 'active', total_referrals: 11, closed_deals: 9, pipeline_value: 1340000, partner_category: 'individual' },
    { id: 13, name: 'Maria Garcia', email: 'maria@garciahomes.com', phone: '(555) 333-4444', company: 'Garcia Homes Real Estate', title: 'Realtor', partner_type: 'Realtor', tier: 'Gold', status: 'active', total_referrals: 26, closed_deals: 20, pipeline_value: 3250000, partner_category: 'individual' },
    { id: 14, name: 'Nathan Clark', email: 'nathan@clarklaw.com', phone: '(555) 444-5555', company: 'Clark Law Group', title: 'Real Estate Attorney', partner_type: 'Attorney', tier: 'Bronze', status: 'active', total_referrals: 7, closed_deals: 6, pipeline_value: 890000, partner_category: 'individual' },
    { id: 15, name: 'Olivia Taylor', email: 'olivia@taylorproperties.com', phone: '(555) 555-6666', company: 'Taylor Properties', title: 'Senior Agent', partner_type: 'Realtor', tier: 'Gold', status: 'active', total_referrals: 30, closed_deals: 24, pipeline_value: 3920000, partner_category: 'individual' }
  ];
};

function ReferralPartners() {
  const navigate = useNavigate();
  const [partners, setPartners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [partnerCategory, setPartnerCategory] = useState('individual'); // 'individual' or 'team'

  useEffect(() => {
    loadPartners();
  }, []);

  const loadPartners = async () => {
    try {
      setLoading(true);
      try {
        const data = await partnersAPI.getAll();
        console.log('Loaded partners data:', data);
        console.log('Is array?', Array.isArray(data));
        console.log('Type:', typeof data);

        // Ensure data is always an array
        if (Array.isArray(data)) {
          setPartners(data);
        } else {
          console.error('API returned non-array data:', data);
          setPartners([]);
        }
      } catch (apiError) {
        console.log('API failed, using mock data:', apiError);
        // Fallback to mock data
        setPartners(generateMockPartners());
      }
    } catch (error) {
      console.error('Failed to load referral partners:', error);
      console.error('Error details:', error.response?.data);
      // Set empty array on error
      setPartners([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddPartner = async (partnerData) => {
    try {
      console.log('Creating referral partner with data:', partnerData);
      await partnersAPI.create(partnerData);
      loadPartners();
      setShowAddModal(false);
    } catch (error) {
      console.error('Failed to create partner:', error);
      console.error('Error response:', error.response?.data);
      const errorMsg = error.response?.data?.detail
        ? (typeof error.response.data.detail === 'string'
           ? error.response.data.detail
           : JSON.stringify(error.response.data.detail))
        : error.message || 'Unknown error';
      alert('Failed to create referral partner: ' + errorMsg);
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

  // Filter by category first (individual vs team)
  const categoryFiltered = safePartners.filter(p => {
    const category = p.partner_category || 'individual'; // Default to individual if not set
    return category === partnerCategory;
  });

  // Then filter by status
  const filteredPartners = filterStatus === 'all'
    ? categoryFiltered
    : categoryFiltered.filter(p => p.status === filterStatus);

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

      {/* Category Toggle */}
      <div className="category-toggle">
        <button
          className={`category-toggle-btn ${partnerCategory === 'individual' ? 'active' : ''}`}
          onClick={() => setPartnerCategory('individual')}
        >
          👤 Individual Partners
          <span className="category-count">
            ({safePartners.filter(p => (p.partner_category || 'individual') === 'individual').length})
          </span>
        </button>
        <button
          className={`category-toggle-btn ${partnerCategory === 'team' ? 'active' : ''}`}
          onClick={() => setPartnerCategory('team')}
        >
          👥 Team Partners
          <span className="category-count">
            ({safePartners.filter(p => p.partner_category === 'team').length})
          </span>
        </button>
      </div>

      <div className="filter-bar">
        <button
          className={filterStatus === 'all' ? 'active' : ''}
          onClick={() => setFilterStatus('all')}
        >
          All ({categoryFiltered.length})
        </button>
        <button
          className={filterStatus === 'active' ? 'active' : ''}
          onClick={() => setFilterStatus('active')}
        >
          Active ({categoryFiltered.filter(p => p.status === 'active').length})
        </button>
        <button
          className={filterStatus === 'inactive' ? 'active' : ''}
          onClick={() => setFilterStatus('inactive')}
        >
          Inactive ({categoryFiltered.filter(p => p.status === 'inactive').length})
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
          defaultCategory={partnerCategory}
        />
      )}
    </div>
  );
}

function AddPartnerModal({ onClose, onAdd, defaultCategory }) {
  const [formData, setFormData] = useState({
    name: '',
    company: '',
    type: '',
    phone: '',
    email: '',
    partner_category: defaultCategory || 'individual',
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
            <label>Partner Category</label>
            <div className="radio-group">
              <label className="radio-label">
                <input
                  type="radio"
                  name="partner_category"
                  value="individual"
                  checked={formData.partner_category === 'individual'}
                  onChange={(e) => setFormData({ ...formData, partner_category: e.target.value })}
                />
                <span>👤 Individual Partner</span>
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="partner_category"
                  value="team"
                  checked={formData.partner_category === 'team'}
                  onChange={(e) => setFormData({ ...formData, partner_category: e.target.value })}
                />
                <span>👥 Team Partner</span>
              </label>
            </div>
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
