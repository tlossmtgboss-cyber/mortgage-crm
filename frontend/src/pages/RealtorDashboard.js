import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import './RealtorDashboard.css';
import { toast } from '../utils/toast';

/**
 * RealtorDashboard - Realtor Partner Dashboard
 *
 * Features:
 * - Referral tracking
 * - Lead submission
 * - Commission tracking
 * - Communication with LO partners
 */

const RealtorDashboard = () => {
  const navigate = useNavigate();

  // Dashboard state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [profile, setProfile] = useState(null);
  const [stats, setStats] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [loPartners, setLoPartners] = useState([]);

  // Modal state
  const [showReferralModal, setShowReferralModal] = useState(false);
  const [referralForm, setReferralForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    property_address: '',
    loan_type: 'purchase',
    estimated_amount: '',
    notes: '',
    lo_id: ''
  });
  const [submitting, setSubmitting] = useState(false);

  // Active tab
  const [activeTab, setActiveTab] = useState('overview');

  // Load dashboard data
  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch multiple endpoints in parallel
      const [profileRes, statsRes, referralsRes, partnersRes] = await Promise.allSettled([
        api.get('/api/v1/users/me'),
        api.get('/api/v1/realtor/stats'),
        api.get('/api/v1/realtor/referrals'),
        api.get('/api/v1/realtor/lo-partners'),
      ]);

      if (profileRes.status === 'fulfilled') {
        setProfile(profileRes.value.data);
      }

      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data);
      } else {
        // Set default stats
        setStats({
          total_referrals: 0,
          pending_referrals: 0,
          funded_referrals: 0,
          total_commission: 0,
          mtd_commission: 0,
          conversion_rate: 0
        });
      }

      if (referralsRes.status === 'fulfilled') {
        setReferrals(referralsRes.value.data.referrals || referralsRes.value.data || []);
      }

      if (partnersRes.status === 'fulfilled') {
        setLoPartners(partnersRes.value.data.partners || partnersRes.value.data || []);
      }

    } catch (err) {
      console.error('Dashboard load error:', err);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  // Handle referral form input
  const handleReferralInput = (e) => {
    const { name, value } = e.target;
    setReferralForm(prev => ({ ...prev, [name]: value }));
  };

  // Submit referral
  const submitReferral = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      await api.post('/api/v1/realtor/referrals', {
        ...referralForm,
        estimated_amount: parseFloat(referralForm.estimated_amount) || 0,
      });

      setShowReferralModal(false);
      setReferralForm({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        property_address: '',
        loan_type: 'purchase',
        estimated_amount: '',
        notes: '',
        lo_id: ''
      });
      loadDashboard(); // Refresh data
    } catch (err) {
      console.error('Referral submission error:', err);
      toast.error('Failed to submit referral. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount || 0);
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Get status badge class
  const getStatusClass = (status) => {
    const statusMap = {
      'new': 'new',
      'contacted': 'contacted',
      'in_progress': 'progress',
      'under_review': 'review',
      'approved': 'approved',
      'funded': 'funded',
      'lost': 'lost',
    };
    return statusMap[status?.toLowerCase()] || 'default';
  };

  if (loading) {
    return (
      <div className="realtor-dashboard-loading">
        <div className="loading-spinner"></div>
        <p>Loading your dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="realtor-dashboard-error">
        <div className="error-icon">!</div>
        <h2>Unable to load dashboard</h2>
        <p>{error}</p>
        <button onClick={loadDashboard}>Try Again</button>
      </div>
    );
  }

  return (
    <div className="realtor-dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <h1>Realtor Dashboard</h1>
          <p className="welcome-text">
            Welcome back, {profile?.first_name || profile?.name || 'Partner'}
          </p>
        </div>
        <div className="header-right">
          <button
            className="btn-new-referral"
            onClick={() => setShowReferralModal(true)}
          >
            + New Referral
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="dashboard-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab ${activeTab === 'referrals' ? 'active' : ''}`}
          onClick={() => setActiveTab('referrals')}
        >
          My Referrals
        </button>
        <button
          className={`tab ${activeTab === 'partners' ? 'active' : ''}`}
          onClick={() => setActiveTab('partners')}
        >
          LO Partners
        </button>
        <button
          className={`tab ${activeTab === 'commission' ? 'active' : ''}`}
          onClick={() => setActiveTab('commission')}
        >
          Commission
        </button>
      </nav>

      <main className="dashboard-content">
        {activeTab === 'overview' && (
          <>
            {/* Stats Cards */}
            <section className="stats-section">
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-icon referrals">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.total_referrals || 0}</span>
                    <span className="stat-label">Total Referrals</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon pending">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <polyline points="12 6 12 12 16 14"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.pending_referrals || 0}</span>
                    <span className="stat-label">In Progress</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon funded">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                      <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{stats?.funded_referrals || 0}</span>
                    <span className="stat-label">Funded</span>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-icon commission">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                    </svg>
                  </div>
                  <div className="stat-content">
                    <span className="stat-value">{formatCurrency(stats?.total_commission)}</span>
                    <span className="stat-label">Total Commission</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Recent Referrals */}
            <section className="recent-section">
              <div className="section-header">
                <h2>Recent Referrals</h2>
                <button onClick={() => setActiveTab('referrals')} className="btn-link">
                  View All
                </button>
              </div>

              {referrals.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                      <line x1="19" y1="8" x2="19" y2="14"/>
                      <line x1="22" y1="11" x2="16" y2="11"/>
                    </svg>
                  </div>
                  <p>No referrals yet</p>
                  <button
                    onClick={() => setShowReferralModal(true)}
                    className="btn-primary"
                  >
                    Submit Your First Referral
                  </button>
                </div>
              ) : (
                <div className="referrals-list">
                  {referrals.slice(0, 5).map(referral => (
                    <div key={referral.id} className="referral-card">
                      <div className="referral-main">
                        <span className="referral-name">
                          {referral.first_name} {referral.last_name}
                        </span>
                        <span className="referral-details">
                          {referral.property_address || referral.loan_type || '-'}
                        </span>
                      </div>
                      <div className="referral-meta">
                        <span className={`status-badge ${getStatusClass(referral.status)}`}>
                          {referral.status || 'New'}
                        </span>
                        <span className="referral-date">{formatDate(referral.created_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Quick Actions */}
            <section className="quick-actions-section">
              <h2>Quick Actions</h2>
              <div className="quick-actions-grid">
                <button onClick={() => setShowReferralModal(true)}>
                  <span className="action-icon">+</span>
                  <span>New Referral</span>
                </button>
                <button onClick={() => setActiveTab('partners')}>
                  <span className="action-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                    </svg>
                  </span>
                  <span>View LO Partners</span>
                </button>
                <button onClick={() => setActiveTab('commission')}>
                  <span className="action-icon">$</span>
                  <span>Commission Report</span>
                </button>
                <button onClick={() => navigate('/calendar')}>
                  <span className="action-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                      <line x1="16" y1="2" x2="16" y2="6"/>
                      <line x1="8" y1="2" x2="8" y2="6"/>
                      <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                  </span>
                  <span>Schedule Meeting</span>
                </button>
              </div>
            </section>
          </>
        )}

        {activeTab === 'referrals' && (
          <section className="referrals-section">
            <div className="section-header">
              <h2>All Referrals</h2>
              <button
                className="btn-primary"
                onClick={() => setShowReferralModal(true)}
              >
                + New Referral
              </button>
            </div>

            {referrals.length === 0 ? (
              <div className="empty-state large">
                <div className="empty-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <line x1="19" y1="8" x2="19" y2="14"/>
                    <line x1="22" y1="11" x2="16" y2="11"/>
                  </svg>
                </div>
                <h3>No referrals yet</h3>
                <p>Start submitting referrals to track your clients and earn commissions.</p>
                <button
                  onClick={() => setShowReferralModal(true)}
                  className="btn-primary"
                >
                  Submit Your First Referral
                </button>
              </div>
            ) : (
              <table className="referrals-table">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>Property</th>
                    <th>Loan Type</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {referrals.map(referral => (
                    <tr key={referral.id}>
                      <td>
                        <div className="client-cell">
                          <span className="client-name">
                            {referral.first_name} {referral.last_name}
                          </span>
                          <span className="client-email">{referral.email}</span>
                        </div>
                      </td>
                      <td>{referral.property_address || '-'}</td>
                      <td className="capitalize">{referral.loan_type || '-'}</td>
                      <td>{formatCurrency(referral.estimated_amount)}</td>
                      <td>
                        <span className={`status-badge ${getStatusClass(referral.status)}`}>
                          {referral.status || 'New'}
                        </span>
                      </td>
                      <td>{formatDate(referral.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}

        {activeTab === 'partners' && (
          <section className="partners-section">
            <div className="section-header">
              <h2>LO Partners</h2>
            </div>

            {loPartners.length === 0 ? (
              <div className="empty-state large">
                <div className="empty-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                </div>
                <h3>No partners assigned yet</h3>
                <p>Contact your administrator to get connected with loan officers.</p>
              </div>
            ) : (
              <div className="partners-grid">
                {loPartners.map(partner => (
                  <div key={partner.id} className="partner-card">
                    <div className="partner-avatar">
                      {partner.avatar_url ? (
                        <img src={partner.avatar_url} alt={partner.name} />
                      ) : (
                        <span>{(partner.name || partner.first_name || 'L').charAt(0)}</span>
                      )}
                    </div>
                    <div className="partner-info">
                      <h3>{partner.name || `${partner.first_name} ${partner.last_name}`}</h3>
                      <p className="partner-company">{partner.company || 'Mortgage Lending'}</p>
                      {partner.nmls_id && <p className="partner-nmls">NMLS# {partner.nmls_id}</p>}
                    </div>
                    <div className="partner-contact">
                      {partner.phone && (
                        <a href={`tel:${partner.phone}`} className="contact-btn">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                          </svg>
                          Call
                        </a>
                      )}
                      {partner.email && (
                        <a href={`mailto:${partner.email}`} className="contact-btn">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                            <polyline points="22,6 12,13 2,6"/>
                          </svg>
                          Email
                        </a>
                      )}
                    </div>
                    <button
                      className="btn-refer"
                      onClick={() => {
                        setReferralForm(prev => ({ ...prev, lo_id: partner.id }));
                        setShowReferralModal(true);
                      }}
                    >
                      Send Referral
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {activeTab === 'commission' && (
          <section className="commission-section">
            <div className="section-header">
              <h2>Commission Summary</h2>
            </div>

            <div className="commission-cards">
              <div className="commission-card total">
                <h3>Total Earned</h3>
                <span className="amount">{formatCurrency(stats?.total_commission)}</span>
              </div>
              <div className="commission-card mtd">
                <h3>This Month</h3>
                <span className="amount">{formatCurrency(stats?.mtd_commission)}</span>
              </div>
              <div className="commission-card pending">
                <h3>Pending</h3>
                <span className="amount">{formatCurrency(stats?.pending_commission)}</span>
              </div>
            </div>

            <div className="commission-note">
              <p>Commission is paid after loan funding. Contact your administrator for payment details.</p>
            </div>
          </section>
        )}
      </main>

      {/* Referral Modal */}
      {showReferralModal && (
        <div className="modal-overlay" onClick={() => setShowReferralModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Submit New Referral</h2>
              <button
                className="modal-close"
                onClick={() => setShowReferralModal(false)}
              >
                &times;
              </button>
            </div>

            <form onSubmit={submitReferral}>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="first_name">First Name *</label>
                  <input
                    type="text"
                    id="first_name"
                    name="first_name"
                    value={referralForm.first_name}
                    onChange={handleReferralInput}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="last_name">Last Name *</label>
                  <input
                    type="text"
                    id="last_name"
                    name="last_name"
                    value={referralForm.last_name}
                    onChange={handleReferralInput}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="email">Email *</label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={referralForm.email}
                    onChange={handleReferralInput}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="phone">Phone *</label>
                  <input
                    type="tel"
                    id="phone"
                    name="phone"
                    value={referralForm.phone}
                    onChange={handleReferralInput}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="property_address">Property Address</label>
                <input
                  type="text"
                  id="property_address"
                  name="property_address"
                  value={referralForm.property_address}
                  onChange={handleReferralInput}
                  placeholder="Enter property address (if known)"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="loan_type">Loan Type</label>
                  <select
                    id="loan_type"
                    name="loan_type"
                    value={referralForm.loan_type}
                    onChange={handleReferralInput}
                  >
                    <option value="purchase">Purchase</option>
                    <option value="refinance">Refinance</option>
                    <option value="cash_out">Cash-Out Refinance</option>
                    <option value="preapproval">Pre-Approval</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="estimated_amount">Estimated Loan Amount</label>
                  <input
                    type="number"
                    id="estimated_amount"
                    name="estimated_amount"
                    value={referralForm.estimated_amount}
                    onChange={handleReferralInput}
                    placeholder="Enter amount"
                  />
                </div>
              </div>

              {loPartners.length > 0 && (
                <div className="form-group">
                  <label htmlFor="lo_id">Assign to LO</label>
                  <select
                    id="lo_id"
                    name="lo_id"
                    value={referralForm.lo_id}
                    onChange={handleReferralInput}
                  >
                    <option value="">Select LO Partner</option>
                    {loPartners.map(lo => (
                      <option key={lo.id} value={lo.id}>
                        {lo.name || `${lo.first_name} ${lo.last_name}`}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="notes">Additional Notes</label>
                <textarea
                  id="notes"
                  name="notes"
                  value={referralForm.notes}
                  onChange={handleReferralInput}
                  placeholder="Any additional information about the client..."
                  rows="3"
                />
              </div>

              <div className="form-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowReferralModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submitting}
                >
                  {submitting ? 'Submitting...' : 'Submit Referral'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default RealtorDashboard;
