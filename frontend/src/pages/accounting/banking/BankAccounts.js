import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function BankAccounts() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [glAccounts, setGLAccounts] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [summary, setSummary] = useState({
    total_accounts: 0,
    total_balance: 0,
    connected_accounts: 0,
  });

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    account_type: 'checking',
    bank_name: '',
    account_number_last4: '',
    routing_number: '',
    gl_account_id: '',
    opening_balance: 0,
    opening_balance_date: new Date().toISOString().split('T')[0],
    is_active: true,
    notes: '',
  });

  // Fetch accounts
  const fetchAccounts = useCallback(async () => {
    try {
      setLoading(true);
      const data = await accountingAPI.getBankAccounts();
      setAccounts(data?.accounts || []);
      setSummary(data?.summary || {
        total_accounts: 0,
        total_balance: 0,
        connected_accounts: 0,
      });
      setLoading(false);
    } catch (err) {
      console.error('Error fetching bank accounts:', err);
      setLoading(false);
    }
  }, []);

  // Fetch GL accounts for mapping
  const fetchGLAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getChartOfAccounts({ type: 'asset' });
      // Filter for bank/cash type accounts
      const bankAccounts = (data?.accounts || []).filter(
        a => a.account_type === 'asset' && (a.sub_type === 'bank' || a.sub_type === 'cash')
      );
      setGLAccounts(bankAccounts.length > 0 ? bankAccounts : data?.accounts || []);
    } catch (err) {
      console.error('Error fetching GL accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
    fetchGLAccounts();
  }, [fetchAccounts, fetchGLAccounts]);

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(amount || 0);
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Open modal
  const openModal = (account = null) => {
    if (account) {
      setEditingAccount(account);
      setFormData({
        name: account.name || '',
        account_type: account.account_type || 'checking',
        bank_name: account.bank_name || '',
        account_number_last4: account.account_number_last4 || '',
        routing_number: account.routing_number || '',
        gl_account_id: account.gl_account_id || '',
        opening_balance: account.opening_balance || 0,
        opening_balance_date: account.opening_balance_date?.split('T')[0] || '',
        is_active: account.is_active !== false,
        notes: account.notes || '',
      });
    } else {
      setEditingAccount(null);
      setFormData({
        name: '',
        account_type: 'checking',
        bank_name: '',
        account_number_last4: '',
        routing_number: '',
        gl_account_id: '',
        opening_balance: 0,
        opening_balance_date: new Date().toISOString().split('T')[0],
        is_active: true,
        notes: '',
      });
    }
    setShowModal(true);
  };

  // Close modal
  const closeModal = () => {
    setShowModal(false);
    setEditingAccount(null);
  };

  // Handle save
  const handleSave = async () => {
    try {
      if (editingAccount) {
        await accountingAPI.updateBankAccount(editingAccount.id, formData);
      } else {
        await accountingAPI.createBankAccount(formData);
      }
      closeModal();
      fetchAccounts();
    } catch (err) {
      console.error('Error saving bank account:', err);
      toast.error('Failed to save bank account');
    }
  };

  // Handle deactivate
  const handleDeactivate = async (account) => {
    if (!window.confirm(`Are you sure you want to ${account.is_active ? 'deactivate' : 'activate'} this account?`)) return;
    try {
      await accountingAPI.updateBankAccount(account.id, { is_active: !account.is_active });
      fetchAccounts();
    } catch (err) {
      console.error('Error updating account:', err);
      toast.error('Failed to update account');
    }
  };

  // Sync transactions
  const handleSync = async (account) => {
    try {
      await accountingAPI.syncBankTransactions(account.id);
      toast.success('Sync initiated. Transactions will be updated shortly.');
      fetchAccounts();
    } catch (err) {
      console.error('Error syncing transactions:', err);
      toast.error('Failed to sync transactions');
    }
  };

  // Get account type icon
  const getAccountTypeIcon = (type) => {
    const icons = {
      checking: 'fa-money-check',
      savings: 'fa-piggy-bank',
      credit_card: 'fa-credit-card',
      money_market: 'fa-chart-line',
      loan: 'fa-hand-holding-usd',
    };
    return icons[type] || 'fa-university';
  };

  // Get connection status badge
  const getConnectionBadge = (account) => {
    if (account.plaid_connected) {
      return (
        <span className="connection-badge connected">
          <i className="fas fa-link"></i> Connected
        </span>
      );
    }
    return (
      <span className="connection-badge manual">
        <i className="fas fa-edit"></i> Manual
      </span>
    );
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Bank Accounts...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page bank-accounts">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Bank Accounts.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page bank-accounts">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-university"></i> Bank Accounts</h1>
            <p className="subtitle">Manage your bank accounts and connections</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={() => navigate('/accounting/banking/connect')}>
            <i className="fas fa-plug"></i> Connect Bank
          </button>
          <button className="btn-primary" onClick={() => openModal()}>
            <i className="fas fa-plus"></i> Add Account
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-university"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.total_accounts}</span>
            <span className="summary-label">Total Accounts</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-dollar-sign"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{formatCurrency(summary.total_balance)}</span>
            <span className="summary-label">Total Balance</span>
          </div>
        </div>
        <div className="summary-card success">
          <div className="summary-icon">
            <i className="fas fa-link"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.connected_accounts}</span>
            <span className="summary-label">Connected via Plaid</span>
          </div>
        </div>
      </div>

      {/* Accounts Grid */}
      <div className="bank-accounts-grid">
        {accounts.length > 0 ? (
          accounts.map(account => (
            <div key={account.id} className={`bank-account-card ${!account.is_active ? 'inactive' : ''}`}>
              <div className="card-header">
                <div className="account-icon">
                  <i className={`fas ${getAccountTypeIcon(account.account_type)}`}></i>
                </div>
                <div className="account-info">
                  <h3>{account.name}</h3>
                  <span className="bank-name">{account.bank_name}</span>
                </div>
                {getConnectionBadge(account)}
              </div>

              <div className="card-body">
                <div className="account-details">
                  <div className="detail-row">
                    <span className="label">Account Type</span>
                    <span className="value">{account.account_type?.replace('_', ' ')}</span>
                  </div>
                  <div className="detail-row">
                    <span className="label">Account #</span>
                    <span className="value">****{account.account_number_last4 || '----'}</span>
                  </div>
                  {account.last_sync_at && (
                    <div className="detail-row">
                      <span className="label">Last Synced</span>
                      <span className="value">{formatDate(account.last_sync_at)}</span>
                    </div>
                  )}
                </div>

                <div className="balance-section">
                  <span className="balance-label">Current Balance</span>
                  <span className={`balance-amount ${account.current_balance < 0 ? 'negative' : ''}`}>
                    {formatCurrency(account.current_balance)}
                  </span>
                </div>
              </div>

              <div className="card-actions">
                <button
                  className="action-btn"
                  onClick={() => navigate(`/accounting/banking/transactions?account=${account.id}`)}
                  title="View Transactions"
                >
                  <i className="fas fa-list"></i>
                </button>
                {account.plaid_connected && (
                  <button
                    className="action-btn"
                    onClick={() => handleSync(account)}
                    title="Sync Transactions"
                  >
                    <i className="fas fa-sync-alt"></i>
                  </button>
                )}
                <button
                  className="action-btn"
                  onClick={() => navigate(`/accounting/banking/reconcile?account=${account.id}`)}
                  title="Reconcile"
                >
                  <i className="fas fa-check-double"></i>
                </button>
                <button
                  className="action-btn"
                  onClick={() => openModal(account)}
                  title="Edit"
                >
                  <i className="fas fa-edit"></i>
                </button>
                <button
                  className={`action-btn ${account.is_active ? 'danger' : 'success'}`}
                  onClick={() => handleDeactivate(account)}
                  title={account.is_active ? 'Deactivate' : 'Activate'}
                >
                  <i className={`fas ${account.is_active ? 'fa-toggle-off' : 'fa-toggle-on'}`}></i>
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state full-width">
            <i className="fas fa-university"></i>
            <h3>No Bank Accounts</h3>
            <p>Add your first bank account to start tracking transactions.</p>
            <div className="empty-actions">
              <button className="btn-secondary" onClick={() => navigate('/accounting/banking/connect')}>
                <i className="fas fa-plug"></i> Connect via Plaid
              </button>
              <button className="btn-primary" onClick={() => openModal()}>
                <i className="fas fa-plus"></i> Add Manually
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Account Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingAccount ? 'Edit Bank Account' : 'Add Bank Account'}</h2>
              <button className="close-btn" onClick={closeModal}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              <div className="form-row">
                <div className="form-group">
                  <label>Account Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Main Operating Account"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Account Type *</label>
                  <select
                    value={formData.account_type}
                    onChange={(e) => setFormData(prev => ({ ...prev, account_type: e.target.value }))}
                  >
                    <option value="checking">Checking</option>
                    <option value="savings">Savings</option>
                    <option value="money_market">Money Market</option>
                    <option value="credit_card">Credit Card</option>
                    <option value="loan">Loan / Line of Credit</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Bank Name</label>
                  <input
                    type="text"
                    value={formData.bank_name}
                    onChange={(e) => setFormData(prev => ({ ...prev, bank_name: e.target.value }))}
                    placeholder="e.g., Chase Bank"
                  />
                </div>
                <div className="form-group">
                  <label>Account # (Last 4)</label>
                  <input
                    type="text"
                    value={formData.account_number_last4}
                    onChange={(e) => setFormData(prev => ({ ...prev, account_number_last4: e.target.value.slice(0, 4) }))}
                    placeholder="1234"
                    maxLength="4"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Routing Number</label>
                  <input
                    type="text"
                    value={formData.routing_number}
                    onChange={(e) => setFormData(prev => ({ ...prev, routing_number: e.target.value }))}
                    placeholder="9 digits"
                    maxLength="9"
                  />
                </div>
                <div className="form-group">
                  <label>GL Account *</label>
                  <select
                    value={formData.gl_account_id}
                    onChange={(e) => setFormData(prev => ({ ...prev, gl_account_id: e.target.value }))}
                    required
                  >
                    <option value="">Select GL Account</option>
                    {glAccounts.map(a => (
                      <option key={a.id} value={a.id}>{a.account_number} - {a.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Opening Balance</label>
                  <input
                    type="number"
                    value={formData.opening_balance}
                    onChange={(e) => setFormData(prev => ({ ...prev, opening_balance: parseFloat(e.target.value) || 0 }))}
                    step="0.01"
                  />
                </div>
                <div className="form-group">
                  <label>As of Date</label>
                  <input
                    type="date"
                    value={formData.opening_balance_date}
                    onChange={(e) => setFormData(prev => ({ ...prev, opening_balance_date: e.target.value }))}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                  placeholder="Additional notes..."
                  rows="2"
                />
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
                  />
                  Account is Active
                </label>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={closeModal}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleSave}>
                {editingAccount ? 'Update Account' : 'Add Account'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BankAccounts;
