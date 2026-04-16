import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import './AdminCustomDomains.css';
import { getToken } from '../utils/tokenStore';

const AdminCustomDomains = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require admin access
  const canAccessDomains = isAdmin || hasAnyPermission(['admin.manage', 'domains.manage', 'system.admin']) || userRole === 'admin';

  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showInstructionsModal, setShowInstructionsModal] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState(null);
  const [verificationInstructions, setVerificationInstructions] = useState(null);
  const [domainStatus, setDomainStatus] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  const [actionResult, setActionResult] = useState({});

  // Form state for adding domain
  const [newDomain, setNewDomain] = useState('');
  const [newDomainNotes, setNewDomainNotes] = useState('');

  const token = getToken();

  const fetchDomains = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/admin/domains`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) throw new Error('Failed to fetch domains');

      const data = await response.json();
      setDomains(data.domains || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchDomains();
  }, [fetchDomains]);

  const handleAddDomain = async (e) => {
    e.preventDefault();
    setActionLoading({ ...actionLoading, add: true });

    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/domains`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          domain: newDomain,
          notes: newDomainNotes || null
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to add domain');
      }

      setActionResult({ add: { success: true, message: 'Domain added successfully!' } });
      setNewDomain('');
      setNewDomainNotes('');
      setShowAddModal(false);
      fetchDomains();
    } catch (err) {
      setActionResult({ add: { success: false, message: err.message } });
    } finally {
      setActionLoading({ ...actionLoading, add: false });
    }
  };

  const handleRemoveDomain = async (domain) => {
    if (!window.confirm(`Are you sure you want to remove ${domain}?`)) return;

    setActionLoading({ ...actionLoading, [domain]: true });

    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/domains/${encodeURIComponent(domain)}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) throw new Error('Failed to remove domain');

      setActionResult({ [domain]: { success: true, message: 'Domain removed' } });
      fetchDomains();
    } catch (err) {
      setActionResult({ [domain]: { success: false, message: err.message } });
    } finally {
      setActionLoading({ ...actionLoading, [domain]: false });
    }
  };

  const fetchVerificationInstructions = async (domain) => {
    setSelectedDomain(domain);
    setActionLoading({ ...actionLoading, instructions: true });

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/admin/domains/${encodeURIComponent(domain)}/verification-instructions`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) throw new Error('Failed to fetch instructions');

      const data = await response.json();
      setVerificationInstructions(data);
      setShowInstructionsModal(true);
    } catch (err) {
      setActionResult({ instructions: { success: false, message: err.message } });
    } finally {
      setActionLoading({ ...actionLoading, instructions: false });
    }
  };

  const fetchDomainStatus = async (domain) => {
    setSelectedDomain(domain);
    setActionLoading({ ...actionLoading, status: true });

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/admin/domains/${encodeURIComponent(domain)}/status`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) throw new Error('Failed to fetch status');

      const data = await response.json();
      setDomainStatus(data);
      setShowStatusModal(true);
    } catch (err) {
      setActionResult({ status: { success: false, message: err.message } });
    } finally {
      setActionLoading({ ...actionLoading, status: false });
    }
  };

  const verifyDomain = async (domain) => {
    setActionLoading({ ...actionLoading, [`verify-${domain}`]: true });

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/admin/domains/${encodeURIComponent(domain)}/verify-dns`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const data = await response.json();

      if (data.fully_verified) {
        setActionResult({
          [`verify-${domain}`]: {
            success: true,
            message: 'Domain verified successfully!'
          }
        });
        fetchDomains();
      } else {
        setActionResult({
          [`verify-${domain}`]: {
            success: false,
            message: data.next_steps?.map(s => s.instruction).join('. ') || 'Verification incomplete'
          }
        });
      }
    } catch (err) {
      setActionResult({
        [`verify-${domain}`]: { success: false, message: err.message }
      });
    } finally {
      setActionLoading({ ...actionLoading, [`verify-${domain}`]: false });
    }
  };

  const requestSSL = async (domain) => {
    setActionLoading({ ...actionLoading, [`ssl-${domain}`]: true });

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/admin/ssl/${encodeURIComponent(domain)}/request`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ challenge_type: 'http-01' })
        }
      );

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to request SSL');
      }

      setActionResult({
        [`ssl-${domain}`]: {
          success: true,
          message: 'SSL certificate requested. Complete the challenge to activate.'
        }
      });
      fetchDomains();
    } catch (err) {
      setActionResult({
        [`ssl-${domain}`]: { success: false, message: err.message }
      });
    } finally {
      setActionLoading({ ...actionLoading, [`ssl-${domain}`]: false });
    }
  };

  const getStatusBadge = (domain) => {
    if (!domain.is_active) {
      return <span className="status-badge inactive">Inactive</span>;
    }
    if (!domain.is_verified) {
      return <span className="status-badge pending">Pending Verification</span>;
    }
    if (domain.ssl_status === 'active') {
      return <span className="status-badge active">Active (SSL)</span>;
    }
    if (domain.ssl_status === 'pending') {
      return <span className="status-badge ssl-pending">Verified (SSL Pending)</span>;
    }
    return <span className="status-badge verified">Verified</span>;
  };

  const getSSLStatusBadge = (sslStatus) => {
    const badges = {
      'none': <span className="ssl-badge none">No SSL</span>,
      'pending': <span className="ssl-badge pending">Pending</span>,
      'active': <span className="ssl-badge active">Active</span>,
      'expired': <span className="ssl-badge expired">Expired</span>,
      'failed': <span className="ssl-badge failed">Failed</span>,
      'renewing': <span className="ssl-badge renewing">Renewing</span>,
    };
    return badges[sslStatus] || badges['none'];
  };

  if (loading && domains.length === 0) {
    return (
      <div className="admin-custom-domains-page">
        <div className="loading-state">Loading custom domains...</div>
      </div>
    );
  }

  // Access denied if user doesn't have admin permissions
  if (!canAccessDomains) {
    return (
      <div className="admin-custom-domains-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to manage custom domains.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-custom-domains-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Custom Domains</h1>
          <p>Manage custom domains for your organization's landing pages and microsites</p>
        </div>
        <button className="btn-primary" onClick={() => setShowAddModal(true)}>
          + Add Domain
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* Domain Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{domains.length}</div>
          <div className="stat-label">Total Domains</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{domains.filter(d => d.is_verified).length}</div>
          <div className="stat-label">Verified</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{domains.filter(d => d.ssl_status === 'active').length}</div>
          <div className="stat-label">SSL Active</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{domains.filter(d => !d.is_verified && d.is_active).length}</div>
          <div className="stat-label">Pending</div>
        </div>
      </div>

      {/* Domains List */}
      <section className="domains-section">
        <div className="section-header">
          <h2>All Domains</h2>
          <button className="btn-secondary" onClick={fetchDomains} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {domains.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🌐</div>
            <h3>No Custom Domains</h3>
            <p>Add your first custom domain to get started</p>
            <button className="btn-primary" onClick={() => setShowAddModal(true)}>
              Add Domain
            </button>
          </div>
        ) : (
          <div className="domains-table-wrapper">
            <table className="domains-table">
              <thead>
                <tr>
                  <th>Domain</th>
                  <th>Status</th>
                  <th>SSL</th>
                  <th>Added</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {domains.map((domain) => (
                  <tr key={domain.id}>
                    <td className="domain-cell">
                      <span className="domain-name">{domain.domain}</span>
                      {domain.verified_at && (
                        <span className="verified-date">
                          Verified {new Date(domain.verified_at).toLocaleDateString()}
                        </span>
                      )}
                    </td>
                    <td>{getStatusBadge(domain)}</td>
                    <td>{getSSLStatusBadge(domain.ssl_status)}</td>
                    <td className="date-cell">
                      {domain.created_at ? new Date(domain.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="actions-cell">
                      <div className="action-buttons">
                        <button
                          className="btn-action btn-info"
                          onClick={() => fetchDomainStatus(domain.domain)}
                          disabled={actionLoading.status}
                          title="View Status"
                        >
                          Status
                        </button>

                        {!domain.is_verified && (
                          <>
                            <button
                              className="btn-action btn-setup"
                              onClick={() => fetchVerificationInstructions(domain.domain)}
                              disabled={actionLoading.instructions}
                              title="Setup Instructions"
                            >
                              Setup
                            </button>
                            <button
                              className="btn-action btn-verify"
                              onClick={() => verifyDomain(domain.domain)}
                              disabled={actionLoading[`verify-${domain.domain}`]}
                              title="Verify DNS"
                            >
                              {actionLoading[`verify-${domain.domain}`] ? '...' : 'Verify'}
                            </button>
                          </>
                        )}

                        {domain.is_verified && domain.ssl_status !== 'active' && (
                          <button
                            className="btn-action btn-ssl"
                            onClick={() => requestSSL(domain.domain)}
                            disabled={actionLoading[`ssl-${domain.domain}`]}
                            title="Request SSL Certificate"
                          >
                            {actionLoading[`ssl-${domain.domain}`] ? '...' : 'Get SSL'}
                          </button>
                        )}

                        <button
                          className="btn-action btn-danger"
                          onClick={() => handleRemoveDomain(domain.domain)}
                          disabled={actionLoading[domain.domain]}
                          title="Remove Domain"
                        >
                          Remove
                        </button>
                      </div>

                      {actionResult[domain.domain] && (
                        <div className={`action-result ${actionResult[domain.domain].success ? 'success' : 'error'}`}>
                          {actionResult[domain.domain].message}
                        </div>
                      )}
                      {actionResult[`verify-${domain.domain}`] && (
                        <div className={`action-result ${actionResult[`verify-${domain.domain}`].success ? 'success' : 'error'}`}>
                          {actionResult[`verify-${domain.domain}`].message}
                        </div>
                      )}
                      {actionResult[`ssl-${domain.domain}`] && (
                        <div className={`action-result ${actionResult[`ssl-${domain.domain}`].success ? 'success' : 'error'}`}>
                          {actionResult[`ssl-${domain.domain}`].message}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Add Domain Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add Custom Domain</h2>
              <button className="modal-close" onClick={() => setShowAddModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleAddDomain}>
              <div className="modal-body">
                <div className="form-group">
                  <label htmlFor="domain">Domain Name</label>
                  <input
                    type="text"
                    id="domain"
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    placeholder="www.example.com"
                    required
                  />
                  <span className="form-hint">
                    Enter the domain without https:// (e.g., www.yourdomain.com)
                  </span>
                </div>
                <div className="form-group">
                  <label htmlFor="notes">Notes (optional)</label>
                  <textarea
                    id="notes"
                    value={newDomainNotes}
                    onChange={(e) => setNewDomainNotes(e.target.value)}
                    placeholder="Any notes about this domain..."
                    rows={3}
                  />
                </div>

                {actionResult.add && (
                  <div className={`form-result ${actionResult.add.success ? 'success' : 'error'}`}>
                    {actionResult.add.message}
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={actionLoading.add}>
                  {actionLoading.add ? 'Adding...' : 'Add Domain'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Verification Instructions Modal */}
      {showInstructionsModal && verificationInstructions && (
        <div className="modal-overlay" onClick={() => setShowInstructionsModal(false)}>
          <div className="modal-content modal-wide" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>DNS Setup for {verificationInstructions.domain}</h2>
              <button className="modal-close" onClick={() => setShowInstructionsModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="instructions-section">
                <h3>Step 1: Verify Ownership (TXT Record)</h3>
                <div className="dns-record-box">
                  <div className="record-row">
                    <span className="record-label">Record Type:</span>
                    <span className="record-value">TXT</span>
                  </div>
                  <div className="record-row">
                    <span className="record-label">Name/Host:</span>
                    <code className="record-value copyable">{verificationInstructions.txt_record_name}</code>
                  </div>
                  <div className="record-row">
                    <span className="record-label">Value:</span>
                    <code className="record-value copyable">{verificationInstructions.txt_record_value}</code>
                  </div>
                </div>
              </div>

              <div className="instructions-section">
                <h3>Step 2: Point Domain to Our Servers</h3>
                <p className="instruction-note">Choose ONE of the following options:</p>

                <div className="option-box">
                  <h4>Option A: CNAME Record (Recommended)</h4>
                  <div className="dns-record-box">
                    <div className="record-row">
                      <span className="record-label">Record Type:</span>
                      <span className="record-value">CNAME</span>
                    </div>
                    <div className="record-row">
                      <span className="record-label">Name/Host:</span>
                      <code className="record-value">{verificationInstructions.domain}</code>
                    </div>
                    <div className="record-row">
                      <span className="record-label">Value/Target:</span>
                      <code className="record-value copyable">{verificationInstructions.cname_target}</code>
                    </div>
                  </div>
                </div>

                <div className="option-box">
                  <h4>Option B: A Record</h4>
                  <div className="dns-record-box">
                    <div className="record-row">
                      <span className="record-label">Record Type:</span>
                      <span className="record-value">A</span>
                    </div>
                    <div className="record-row">
                      <span className="record-label">Name/Host:</span>
                      <code className="record-value">{verificationInstructions.domain}</code>
                    </div>
                    <div className="record-row">
                      <span className="record-label">Value/IP:</span>
                      <code className="record-value copyable">{verificationInstructions.a_record_ip}</code>
                    </div>
                  </div>
                </div>
              </div>

              <div className="instructions-section">
                <h3>Step 3: Wait & Verify</h3>
                <p>DNS changes can take up to 48 hours to propagate, though they typically complete within a few minutes to a few hours.</p>
                <p>Once you've added the records, click "Verify DNS" to check the configuration.</p>
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="btn-primary"
                onClick={() => {
                  setShowInstructionsModal(false);
                  verifyDomain(verificationInstructions.domain);
                }}
              >
                Verify DNS Now
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Domain Status Modal */}
      {showStatusModal && domainStatus && (
        <div className="modal-overlay" onClick={() => setShowStatusModal(false)}>
          <div className="modal-content modal-wide" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Status: {domainStatus.domain?.domain}</h2>
              <button className="modal-close" onClick={() => setShowStatusModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="status-grid">
                <div className="status-item">
                  <span className="status-label">Domain Active</span>
                  <span className={`status-indicator ${domainStatus.domain?.is_active ? 'yes' : 'no'}`}>
                    {domainStatus.domain?.is_active ? 'Yes' : 'No'}
                  </span>
                </div>
                <div className="status-item">
                  <span className="status-label">Ownership Verified</span>
                  <span className={`status-indicator ${domainStatus.domain?.is_verified ? 'yes' : 'no'}`}>
                    {domainStatus.domain?.is_verified ? 'Yes' : 'No'}
                  </span>
                </div>
                <div className="status-item">
                  <span className="status-label">SSL Status</span>
                  <span className="status-indicator">
                    {domainStatus.domain?.ssl_status || 'None'}
                  </span>
                </div>
                <div className="status-item">
                  <span className="status-label">Ready for Traffic</span>
                  <span className={`status-indicator ${domainStatus.ready_for_traffic ? 'yes' : 'no'}`}>
                    {domainStatus.ready_for_traffic ? 'Yes' : 'No'}
                  </span>
                </div>
              </div>

              {domainStatus.dns_configuration && (
                <div className="status-section">
                  <h3>DNS Configuration</h3>
                  <div className="dns-status-grid">
                    <div className="dns-check">
                      <span className={`check-icon ${domainStatus.dns_configuration.success ? 'pass' : 'fail'}`}>
                        {domainStatus.dns_configuration.success ? '✓' : '✗'}
                      </span>
                      <span>DNS Configured Correctly</span>
                    </div>
                    {domainStatus.dns_configuration.cname_found && (
                      <div className="dns-detail">
                        CNAME: {domainStatus.dns_configuration.cname_target || 'Found'}
                      </div>
                    )}
                    {domainStatus.dns_configuration.a_record_found && (
                      <div className="dns-detail">
                        A Record: {domainStatus.dns_configuration.a_record_ips?.join(', ') || 'Found'}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {domainStatus.txt_verification && (
                <div className="status-section">
                  <h3>TXT Verification</h3>
                  <div className="dns-check">
                    <span className={`check-icon ${domainStatus.txt_verification.success ? 'pass' : 'fail'}`}>
                      {domainStatus.txt_verification.success ? '✓' : '✗'}
                    </span>
                    <span>
                      {domainStatus.txt_verification.success
                        ? 'Ownership verified via TXT record'
                        : domainStatus.txt_verification.message || 'TXT record not found'}
                    </span>
                  </div>
                </div>
              )}

              {domainStatus.reachability && (
                <div className="status-section">
                  <h3>Reachability</h3>
                  <div className="dns-check">
                    <span className={`check-icon ${domainStatus.reachability.reachable ? 'pass' : 'fail'}`}>
                      {domainStatus.reachability.reachable ? '✓' : '✗'}
                    </span>
                    <span>
                      {domainStatus.reachability.reachable
                        ? `Reachable (${domainStatus.reachability.response_time_ms}ms)`
                        : 'Not reachable'}
                    </span>
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowStatusModal(false)}>
                Close
              </button>
              <button
                className="btn-primary"
                onClick={() => fetchDomainStatus(domainStatus.domain?.domain)}
              >
                Refresh Status
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminCustomDomains;
