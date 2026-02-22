import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function PlaidConnect() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [institutions, setInstitutions] = useState([]);
  const [linkToken, setLinkToken] = useState(null);

  // Fetch connected institutions
  const fetchInstitutions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await accountingAPI.getPlaidItems();
      setInstitutions(data?.items || []);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching institutions:', err);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInstitutions();
  }, [fetchInstitutions]);

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Initialize Plaid Link
  const initializePlaidLink = async () => {
    try {
      setConnecting(true);
      const data = await accountingAPI.createPlaidLinkToken();
      setLinkToken(data?.link_token);

      // In production, this would open the Plaid Link modal
      // For now, we'll simulate the flow
      openPlaidLink(data?.link_token);
    } catch (err) {
      console.error('Error creating link token:', err);
      toast.error('Failed to initialize bank connection. Please try again.');
      setConnecting(false);
    }
  };

  // Open Plaid Link (simulation in dev, actual Plaid Link in prod)
  const openPlaidLink = async (token) => {
    // Check if Plaid Link is available (loaded via script)
    if (window.Plaid) {
      const handler = window.Plaid.create({
        token: token,
        onSuccess: async (publicToken, metadata) => {
          await handlePlaidSuccess(publicToken, metadata);
        },
        onExit: (err, metadata) => {
          setConnecting(false);
          if (err) {
            console.error('Plaid Link error:', err);
          }
        },
        onEvent: (eventName, metadata) => {
          console.log('Plaid event:', eventName, metadata);
        },
      });
      handler.open();
    } else {
      // Simulation mode - show a mock connection flow
      const confirmed = window.confirm(
        'Plaid Link would open here.\n\n' +
        'In production, you would:\n' +
        '1. Select your bank\n' +
        '2. Enter your credentials\n' +
        '3. Select accounts to link\n\n' +
        'Click OK to simulate a successful connection.'
      );

      if (confirmed) {
        // Simulate success
        await handlePlaidSuccess('mock_public_token', {
          institution: { name: 'Mock Bank', institution_id: 'mock_inst' },
          accounts: [
            { id: 'mock_1', name: 'Checking', mask: '1234', type: 'depository', subtype: 'checking' },
            { id: 'mock_2', name: 'Savings', mask: '5678', type: 'depository', subtype: 'savings' },
          ],
        });
      } else {
        setConnecting(false);
      }
    }
  };

  // Handle Plaid success
  const handlePlaidSuccess = async (publicToken, metadata) => {
    try {
      await accountingAPI.exchangePlaidToken({
        public_token: publicToken,
        institution: metadata.institution,
        accounts: metadata.accounts,
      });

      setConnecting(false);
      fetchInstitutions();
      toast.success('Bank connected successfully! Accounts will begin syncing shortly.');
    } catch (err) {
      console.error('Error exchanging token:', err);
      toast.error('Failed to complete bank connection. Please try again.');
      setConnecting(false);
    }
  };

  // Update connection (re-authenticate)
  const handleUpdateConnection = async (institution) => {
    try {
      setConnecting(true);
      const data = await accountingAPI.createPlaidLinkToken({
        access_token: institution.access_token_id,
        mode: 'update',
      });
      openPlaidLink(data?.link_token);
    } catch (err) {
      console.error('Error updating connection:', err);
      toast.error('Failed to update connection. Please try again.');
      setConnecting(false);
    }
  };

  // Disconnect institution
  const handleDisconnect = async (institution) => {
    if (!window.confirm(`Are you sure you want to disconnect ${institution.institution_name}? This will stop syncing all connected accounts.`)) {
      return;
    }

    try {
      await accountingAPI.disconnectPlaidItem(institution.id);
      fetchInstitutions();
    } catch (err) {
      console.error('Error disconnecting:', err);
      toast.error('Failed to disconnect. Please try again.');
    }
  };

  // Sync institution
  const handleSync = async (institution) => {
    try {
      await accountingAPI.syncPlaidItem(institution.id);
      toast.success('Sync initiated. Transactions will be updated shortly.');
      fetchInstitutions();
    } catch (err) {
      console.error('Error syncing:', err);
      toast.error('Failed to sync. Please try again.');
    }
  };

  // Get status badge
  const getStatusBadge = (status) => {
    const badges = {
      healthy: { class: 'badge-success', icon: 'fa-check-circle', text: 'Connected' },
      needs_attention: { class: 'badge-warning', icon: 'fa-exclamation-triangle', text: 'Needs Attention' },
      error: { class: 'badge-error', icon: 'fa-times-circle', text: 'Error' },
      disconnected: { class: 'badge-default', icon: 'fa-unlink', text: 'Disconnected' },
    };
    const badge = badges[status] || badges.healthy;
    return (
      <span className={`status-badge ${badge.class}`}>
        <i className={`fas ${badge.icon}`}></i> {badge.text}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Connections...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page plaid-connect">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Plaid Connect.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page plaid-connect">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting/banking/accounts')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-plug"></i> Connect Bank</h1>
            <p className="subtitle">Securely connect your bank accounts via Plaid</p>
          </div>
        </div>
        <div className="header-right">
          <button
            className="btn-primary"
            onClick={initializePlaidLink}
            disabled={connecting}
          >
            {connecting ? (
              <>
                <i className="fas fa-spinner fa-spin"></i> Connecting...
              </>
            ) : (
              <>
                <i className="fas fa-plus"></i> Connect New Bank
              </>
            )}
          </button>
        </div>
      </div>

      {/* How It Works Section */}
      <div className="info-section">
        <h3><i className="fas fa-shield-alt"></i> Secure Bank Connection</h3>
        <div className="info-steps">
          <div className="step">
            <div className="step-number">1</div>
            <div className="step-content">
              <h4>Select Your Bank</h4>
              <p>Choose from thousands of supported financial institutions</p>
            </div>
          </div>
          <div className="step">
            <div className="step-number">2</div>
            <div className="step-content">
              <h4>Login Securely</h4>
              <p>Enter your bank credentials directly with your bank via Plaid</p>
            </div>
          </div>
          <div className="step">
            <div className="step-number">3</div>
            <div className="step-content">
              <h4>Select Accounts</h4>
              <p>Choose which accounts to connect for automatic syncing</p>
            </div>
          </div>
          <div className="step">
            <div className="step-number">4</div>
            <div className="step-content">
              <h4>Auto-Sync</h4>
              <p>Transactions import automatically, keeping your books up to date</p>
            </div>
          </div>
        </div>
        <div className="security-note">
          <i className="fas fa-lock"></i>
          <span>Your credentials are never stored on our servers. All connections are encrypted and secured by Plaid.</span>
        </div>
      </div>

      {/* Connected Institutions */}
      <div className="section">
        <h3>Connected Institutions</h3>

        {institutions.length > 0 ? (
          <div className="institutions-list">
            {institutions.map(institution => (
              <div key={institution.id} className="institution-card">
                <div className="institution-header">
                  <div className="institution-logo">
                    {institution.logo_url ? (
                      <img src={institution.logo_url} alt={institution.institution_name} />
                    ) : (
                      <i className="fas fa-university"></i>
                    )}
                  </div>
                  <div className="institution-info">
                    <h4>{institution.institution_name}</h4>
                    <span className="institution-id">ID: {institution.institution_id}</span>
                  </div>
                  {getStatusBadge(institution.status)}
                </div>

                <div className="institution-accounts">
                  <h5>Connected Accounts ({institution.accounts?.length || 0})</h5>
                  <ul className="account-list">
                    {institution.accounts?.map(account => (
                      <li key={account.id}>
                        <span className="account-name">{account.name}</span>
                        <span className="account-mask">****{account.mask}</span>
                        <span className="account-type">{account.subtype}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="institution-meta">
                  <div className="meta-item">
                    <span className="label">Last Synced:</span>
                    <span className="value">{formatDate(institution.last_sync_at)}</span>
                  </div>
                  <div className="meta-item">
                    <span className="label">Connected:</span>
                    <span className="value">{formatDate(institution.created_at)}</span>
                  </div>
                </div>

                <div className="institution-actions">
                  <button
                    className="action-btn"
                    onClick={() => handleSync(institution)}
                    title="Sync Now"
                  >
                    <i className="fas fa-sync-alt"></i> Sync
                  </button>
                  {institution.status === 'needs_attention' && (
                    <button
                      className="action-btn warning"
                      onClick={() => handleUpdateConnection(institution)}
                      title="Update Connection"
                    >
                      <i className="fas fa-redo"></i> Re-authenticate
                    </button>
                  )}
                  <button
                    className="action-btn danger"
                    onClick={() => handleDisconnect(institution)}
                    title="Disconnect"
                  >
                    <i className="fas fa-unlink"></i> Disconnect
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <i className="fas fa-plug"></i>
            <h3>No Banks Connected</h3>
            <p>Connect your bank accounts to automatically import transactions.</p>
            <button
              className="btn-primary"
              onClick={initializePlaidLink}
              disabled={connecting}
            >
              <i className="fas fa-plus"></i> Connect Your First Bank
            </button>
          </div>
        )}
      </div>

      {/* FAQ Section */}
      <div className="faq-section">
        <h3>Frequently Asked Questions</h3>
        <div className="faq-grid">
          <div className="faq-item">
            <h4>Is my data secure?</h4>
            <p>Yes, Plaid uses bank-level encryption and never stores your login credentials. They are a trusted provider used by thousands of companies including Venmo, Robinhood, and Coinbase.</p>
          </div>
          <div className="faq-item">
            <h4>How often do transactions sync?</h4>
            <p>Transactions typically sync automatically every few hours. You can also manually trigger a sync at any time.</p>
          </div>
          <div className="faq-item">
            <h4>What if my bank isn't supported?</h4>
            <p>Plaid supports over 11,000 financial institutions. If yours isn't listed, you can add transactions manually or via CSV import.</p>
          </div>
          <div className="faq-item">
            <h4>Can I disconnect at any time?</h4>
            <p>Yes, you can disconnect any bank at any time. Your historical transaction data will be preserved.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PlaidConnect;
