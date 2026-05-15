/**
 * RealtorPortal - External Realtor Portal
 *
 * Token-based authentication for external realtors to:
 * - View loan status and timeline
 * - Generate pre-qualification letters
 * - Communicate with loan officers
 * - Track client pipelines
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import PortalVideoMessages from '../components/Portal/PortalVideoMessages';
import './RealtorPortal.css';

// API Configuration
const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
const REALTOR_API = `${API_BASE}/api/v1/realtor-portal`;

// =============================================================================
// API HELPER
// =============================================================================

async function realtorApi(endpoint, token, options = {}) {
  const url = new URL(`${REALTOR_API}${endpoint}`);
  url.searchParams.append('token', token);

  const response = await fetch(url.toString(), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || error.error || 'API request failed');
  }

  return response.json();
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

const RealtorPortal = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Get token from URL or localStorage
  const urlToken = searchParams.get('token');
  const [token, setToken] = useState(urlToken || localStorage.getItem('realtor_token') || '');

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loans, setLoans] = useState([]);
  const [activeTab, setActiveTab] = useState('loans');
  const [selectedLoan, setSelectedLoan] = useState(null);
  const [loanDetail, setLoanDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Store token in localStorage when received via URL
  useEffect(() => {
    if (urlToken) {
      localStorage.setItem('realtor_token', urlToken);
      setToken(urlToken);
      // Clean URL
      window.history.replaceState({}, '', '/realtor-portal');
    }
  }, [urlToken]);

  // Load profile and loans
  const loadData = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const [profileRes, loansRes] = await Promise.all([
        realtorApi('/me', token),
        realtorApi('/loans', token),
      ]);

      setProfile(profileRes.profile);
      setLoans(loansRes.loans || []);
    } catch (err) {
      console.error('Load error:', err);
      setError(err.message);
      if (err.message.includes('expired') || err.message.includes('Invalid')) {
        localStorage.removeItem('realtor_token');
        setToken('');
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Load loan detail
  const loadLoanDetail = useCallback(async (loanId) => {
    if (!token || !loanId) return;

    try {
      setLoadingDetail(true);
      const detail = await realtorApi(`/loans/${loanId}`, token);
      setLoanDetail(detail);
    } catch (err) {
      console.error('Loan detail error:', err);
    } finally {
      setLoadingDetail(false);
    }
  }, [token]);

  // Handle loan selection
  const handleLoanClick = (loan) => {
    setSelectedLoan(loan);
    loadLoanDetail(loan.loan_id);
  };

  // Back to list
  const handleBack = () => {
    setSelectedLoan(null);
    setLoanDetail(null);
  };

  // Logout
  const handleLogout = () => {
    localStorage.removeItem('realtor_token');
    setToken('');
    setProfile(null);
    setLoans([]);
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  // Get status color
  const getStatusColor = (status) => {
    const colors = {
      'LEAD': '#6b7280',
      'APPLICATION': '#3b82f6',
      'PROCESSING': '#B8924A',
      'SUBMITTED': '#f59e0b',
      'UNDERWRITING': '#f59e0b',
      'CONDITIONAL': '#2D7A52',
      'CLEAR_TO_CLOSE': '#2D7A52',
      'CTC': '#2D7A52',
      'DISCLOSED': '#3b82f6',
      'FUNDED': '#2D7A52',
      'DENIED': '#ef4444',
      'WITHDRAWN': '#6b7280',
    };
    return colors[status?.toUpperCase()] || '#6b7280';
  };

  // ==========================================================================
  // RENDER: No Token
  // ==========================================================================

  if (!token) {
    return (
      <div className="realtor-portal">
        <div className="portal-login">
          <div className="login-card">
            <div className="login-logo">
              <h1>Perennia AI</h1>
              <p>Realtor Portal</p>
            </div>
            <div className="login-message">
              <p>Please use the link provided by your loan officer to access the portal.</p>
              <p className="login-help">If you need access, contact your loan officer partner.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ==========================================================================
  // RENDER: Loading
  // ==========================================================================

  if (loading) {
    return (
      <div className="realtor-portal">
        <div className="portal-loading">
          <div className="spinner"></div>
          <p>Loading portal...</p>
        </div>
      </div>
    );
  }

  // ==========================================================================
  // RENDER: Error
  // ==========================================================================

  if (error) {
    return (
      <div className="realtor-portal">
        <div className="portal-error">
          <h2>Access Error</h2>
          <p>{error}</p>
          <button onClick={() => { setError(null); loadData(); }}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // ==========================================================================
  // RENDER: Loan Detail
  // ==========================================================================

  if (selectedLoan) {
    return (
      <div className="realtor-portal">
        <header className="portal-header">
          <div className="header-left">
            <button className="back-button" onClick={handleBack}>
              ← Back to Loans
            </button>
          </div>
          <div className="header-right">
            <span className="user-name">{profile?.first_name} {profile?.last_name}</span>
          </div>
        </header>

        <main className="portal-main">
          <div className="loan-detail-view">
            <div className="detail-header">
              <h2>{selectedLoan.borrower_name}</h2>
              <span
                className="status-badge"
                style={{ backgroundColor: getStatusColor(selectedLoan.status) }}
              >
                {selectedLoan.status}
              </span>
            </div>

            <div className="detail-cards">
              <div className="detail-card">
                <h3>Loan Information</h3>
                <div className="detail-row">
                  <span>Loan Amount</span>
                  <strong>{formatCurrency(selectedLoan.loan_amount)}</strong>
                </div>
                <div className="detail-row">
                  <span>Your Role</span>
                  <strong>{selectedLoan.role?.replace('_', ' ')}</strong>
                </div>
                <div className="detail-row">
                  <span>Access Granted</span>
                  <strong>{new Date(selectedLoan.granted_at).toLocaleDateString()}</strong>
                </div>
              </div>

              {loadingDetail ? (
                <div className="detail-card loading">
                  <div className="spinner small"></div>
                  <p>Loading details...</p>
                </div>
              ) : loanDetail ? (
                <>
                  {loanDetail.timeline && loanDetail.timeline.length > 0 && (
                    <div className="detail-card">
                      <h3>Timeline</h3>
                      <div className="timeline">
                        {loanDetail.timeline.slice(0, 5).map((event, i) => (
                          <div key={i} className="timeline-item">
                            <div className="timeline-dot"></div>
                            <div className="timeline-content">
                              <strong>{event.event_type || event.title}</strong>
                              <span>{new Date(event.created_at || event.date).toLocaleDateString()}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {loanDetail.permissions && (
                    <div className="detail-card">
                      <h3>Available Actions</h3>
                      <div className="permissions-list">
                        {loanDetail.permissions.can_generate_prequal && (
                          <button className="action-button">Generate Pre-Qual Letter</button>
                        )}
                        {loanDetail.permissions.can_generate_preapproval && (
                          <button className="action-button">Generate Pre-Approval Letter</button>
                        )}
                        {loanDetail.permissions.can_send_messages && (
                          <button className="action-button secondary">Message LO</button>
                        )}
                        {loanDetail.permissions.can_view_documents && (
                          <button className="action-button secondary">View Documents</button>
                        )}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </main>
      </div>
    );
  }

  // ==========================================================================
  // RENDER: Main Dashboard
  // ==========================================================================

  return (
    <div className="realtor-portal">
      <header className="portal-header">
        <div className="header-left">
          <h1>Perennia AI</h1>
          <span className="header-subtitle">Realtor Portal</span>
        </div>
        <div className="header-right">
          <span className="user-name">{profile?.first_name} {profile?.last_name}</span>
          <span className="user-brokerage">{profile?.brokerage_name}</span>
          <button className="logout-button" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      <nav className="portal-nav">
        <button
          className={`nav-tab ${activeTab === 'loans' ? 'active' : ''}`}
          onClick={() => setActiveTab('loans')}
        >
          My Clients ({loans.length})
        </button>
        <button
          className={`nav-tab ${activeTab === 'videos' ? 'active' : ''}`}
          onClick={() => setActiveTab('videos')}
        >
          Messages
        </button>
        <button
          className={`nav-tab ${activeTab === 'profile' ? 'active' : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          Profile
        </button>
      </nav>

      <main className="portal-main">
        {activeTab === 'loans' && (
          <div className="loans-section">
            {loans.length === 0 ? (
              <div className="empty-state">
                <h3>No Active Loans</h3>
                <p>You don't have any loan associations yet.</p>
              </div>
            ) : (
              <div className="loans-grid">
                {loans.map((loan) => (
                  <div
                    key={loan.loan_id}
                    className="loan-card"
                    onClick={() => handleLoanClick(loan)}
                  >
                    <div className="loan-header">
                      <h3>{loan.borrower_name}</h3>
                      <span
                        className="status-badge"
                        style={{ backgroundColor: getStatusColor(loan.status) }}
                      >
                        {loan.status}
                      </span>
                    </div>
                    <div className="loan-body">
                      <div className="loan-stat">
                        <span className="stat-label">Loan Amount</span>
                        <span className="stat-value">{formatCurrency(loan.loan_amount)}</span>
                      </div>
                      <div className="loan-stat">
                        <span className="stat-label">Role</span>
                        <span className="stat-value">{loan.role?.replace('_', ' ')}</span>
                      </div>
                    </div>
                    <div className="loan-footer">
                      <span>Access granted {new Date(loan.granted_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'videos' && profile && (
          <div className="videos-section">
            <PortalVideoMessages
              portalType="realtor"
              identifier={profile.id}
              token={token}
              title="Messages from Your Loan Officers"
            />
            {/* Fallback if no videos */}
            <div className="video-empty-state" style={{ textAlign: 'center', padding: '40px 20px', color: '#64748b' }}>
              <p>Video messages from your loan officer partners will appear here.</p>
            </div>
          </div>
        )}

        {activeTab === 'profile' && profile && (
          <div className="profile-section">
            <div className="profile-card">
              <h2>Profile Information</h2>
              <div className="profile-grid">
                <div className="profile-item">
                  <label>Name</label>
                  <span>{profile.first_name} {profile.last_name}</span>
                </div>
                <div className="profile-item">
                  <label>Email</label>
                  <span>{profile.email}</span>
                </div>
                <div className="profile-item">
                  <label>Phone</label>
                  <span>{profile.phone || 'Not provided'}</span>
                </div>
                <div className="profile-item">
                  <label>Brokerage</label>
                  <span>{profile.brokerage_name || 'Not provided'}</span>
                </div>
                <div className="profile-item">
                  <label>License</label>
                  <span>{profile.license_number} ({profile.license_state})</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      <footer className="portal-footer">
        <p>&copy; 2025 Perennia AI. All rights reserved.</p>
      </footer>
    </div>
  );
};

export default RealtorPortal;
