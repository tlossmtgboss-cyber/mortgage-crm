import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function BankTransactions() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [transactions, setTransactions] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [glAccounts, setGLAccounts] = useState([]);
  const [selectedTransactions, setSelectedTransactions] = useState([]);
  const [showMatchModal, setShowMatchModal] = useState(false);
  const [matchingTransaction, setMatchingTransaction] = useState(null);
  const [summary, setSummary] = useState({
    total: 0,
    unmatched: 0,
    matched: 0,
    excluded: 0,
  });

  // Filters
  const [accountFilter, setAccountFilter] = useState(searchParams.get('account') || '');
  const [statusFilter, setStatusFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [dateRange, setDateRange] = useState({
    start: '',
    end: '',
  });

  // Categorization form
  const [categorizeForm, setCategorizeForm] = useState({
    account_id: '',
    payee: '',
    memo: '',
  });

  // Fetch transactions
  const fetchTransactions = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (accountFilter) params.bank_account_id = accountFilter;
      if (statusFilter) params.status = statusFilter;
      if (searchTerm) params.search = searchTerm;
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end) params.end_date = dateRange.end;

      const data = await accountingAPI.getBankTransactions(params);
      setTransactions(data?.transactions || []);
      setSummary(data?.summary || {
        total: 0,
        unmatched: 0,
        matched: 0,
        excluded: 0,
      });
      setLoading(false);
    } catch (err) {
      console.error('Error fetching transactions:', err);
      setLoading(false);
    }
  }, [accountFilter, statusFilter, searchTerm, dateRange]);

  // Fetch bank accounts
  const fetchBankAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getBankAccounts();
      setBankAccounts(data?.accounts || []);
    } catch (err) {
      console.error('Error fetching bank accounts:', err);
    }
  }, []);

  // Fetch GL accounts for categorization
  const fetchGLAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getChartOfAccounts();
      setGLAccounts(data?.accounts || []);
    } catch (err) {
      console.error('Error fetching GL accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  useEffect(() => {
    fetchBankAccounts();
    fetchGLAccounts();
  }, [fetchBankAccounts, fetchGLAccounts]);

  // Format currency
  const formatCurrency = (amount) => {
    const absAmount = Math.abs(amount || 0);
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(absAmount);
    return amount < 0 ? `-${formatted}` : formatted;
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

  // Toggle transaction selection
  const toggleSelection = (txnId) => {
    setSelectedTransactions(prev => {
      if (prev.includes(txnId)) {
        return prev.filter(id => id !== txnId);
      }
      return [...prev, txnId];
    });
  };

  // Select all visible
  const selectAll = () => {
    const unmatchedIds = transactions
      .filter(t => t.status === 'unmatched')
      .map(t => t.id);
    setSelectedTransactions(unmatchedIds);
  };

  // Clear selection
  const clearSelection = () => {
    setSelectedTransactions([]);
  };

  // Open match modal
  const openMatchModal = (transaction) => {
    setMatchingTransaction(transaction);
    setCategorizeForm({
      account_id: transaction.suggested_account_id || '',
      payee: transaction.payee || transaction.name || '',
      memo: transaction.memo || '',
    });
    setShowMatchModal(true);
  };

  // Close match modal
  const closeMatchModal = () => {
    setShowMatchModal(false);
    setMatchingTransaction(null);
  };

  // Handle categorize/match
  const handleCategorize = async () => {
    if (!categorizeForm.account_id) {
      toast.error('Please select an account to categorize this transaction.');
      return;
    }

    try {
      await accountingAPI.categorizeBankTransaction(matchingTransaction.id, {
        gl_account_id: categorizeForm.account_id,
        payee: categorizeForm.payee,
        memo: categorizeForm.memo,
        create_rule: document.getElementById('createRule')?.checked || false,
      });

      closeMatchModal();
      fetchTransactions();
    } catch (err) {
      console.error('Error categorizing transaction:', err);
      toast.error('Failed to categorize transaction');
    }
  };

  // Batch categorize
  const handleBatchCategorize = async (accountId) => {
    if (selectedTransactions.length === 0) return;

    try {
      await accountingAPI.batchCategorizeBankTransactions({
        transaction_ids: selectedTransactions,
        gl_account_id: accountId,
      });

      clearSelection();
      fetchTransactions();
    } catch (err) {
      console.error('Error batch categorizing:', err);
      toast.error('Failed to categorize transactions');
    }
  };

  // Exclude transaction
  const handleExclude = async (transaction) => {
    if (!window.confirm('Exclude this transaction from accounting? It will not be recorded in the general ledger.')) {
      return;
    }

    try {
      await accountingAPI.excludeBankTransaction(transaction.id);
      fetchTransactions();
    } catch (err) {
      console.error('Error excluding transaction:', err);
      toast.error('Failed to exclude transaction');
    }
  };

  // Undo match/exclude
  const handleUndo = async (transaction) => {
    try {
      await accountingAPI.undoBankTransaction(transaction.id);
      fetchTransactions();
    } catch (err) {
      console.error('Error undoing:', err);
      toast.error('Failed to undo');
    }
  };

  // Get status badge
  const getStatusBadge = (status) => {
    const badges = {
      unmatched: 'badge-warning',
      matched: 'badge-success',
      excluded: 'badge-default',
      pending: 'badge-info',
    };
    return badges[status] || 'badge-default';
  };

  // Group accounts by type for dropdown
  const groupedAccounts = glAccounts.reduce((acc, account) => {
    const type = account.account_type || 'Other';
    if (!acc[type]) acc[type] = [];
    acc[type].push(account);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Transactions...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page bank-transactions">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Bank Transactions.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page bank-transactions">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting/banking/accounts')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-exchange-alt"></i> Bank Transactions</h1>
            <p className="subtitle">Review and categorize imported transactions</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={() => navigate('/accounting/banking/rules')}>
            <i className="fas fa-magic"></i> Manage Rules
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-list"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.total}</span>
            <span className="summary-label">Total Transactions</span>
          </div>
        </div>
        <div className="summary-card warning">
          <div className="summary-icon">
            <i className="fas fa-question-circle"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.unmatched}</span>
            <span className="summary-label">To Review</span>
          </div>
        </div>
        <div className="summary-card success">
          <div className="summary-icon">
            <i className="fas fa-check-circle"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.matched}</span>
            <span className="summary-label">Categorized</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-ban"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.excluded}</span>
            <span className="summary-label">Excluded</span>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar">
        <div className="toolbar-left">
          <select
            value={accountFilter}
            onChange={(e) => setAccountFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Accounts</option>
            {bankAccounts.map(acc => (
              <option key={acc.id} value={acc.id}>{acc.name}</option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Statuses</option>
            <option value="unmatched">To Review</option>
            <option value="matched">Categorized</option>
            <option value="excluded">Excluded</option>
          </select>

          <div className="search-box">
            <i className="fas fa-search"></i>
            <input
              type="text"
              placeholder="Search transactions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>

        <div className="toolbar-right">
          {selectedTransactions.length > 0 && (
            <div className="batch-actions">
              <span className="selected-count">{selectedTransactions.length} selected</span>
              <button className="btn-link" onClick={clearSelection}>Clear</button>
            </div>
          )}
          <button className="toolbar-btn" onClick={fetchTransactions} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="data-table bank-txn-table">
        <div className="table-header">
          <div className="header-cell checkbox">
            <input
              type="checkbox"
              onChange={(e) => e.target.checked ? selectAll() : clearSelection()}
              checked={selectedTransactions.length > 0 && selectedTransactions.length === transactions.filter(t => t.status === 'unmatched').length}
            />
          </div>
          <div className="header-cell date">Date</div>
          <div className="header-cell description">Description</div>
          <div className="header-cell account">Account</div>
          <div className="header-cell amount">Amount</div>
          <div className="header-cell category">Category</div>
          <div className="header-cell status">Status</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {transactions.length > 0 ? (
            transactions.map(txn => (
              <div key={txn.id} className={`table-row ${selectedTransactions.includes(txn.id) ? 'selected' : ''}`}>
                <div className="cell checkbox">
                  {txn.status === 'unmatched' && (
                    <input
                      type="checkbox"
                      checked={selectedTransactions.includes(txn.id)}
                      onChange={() => toggleSelection(txn.id)}
                    />
                  )}
                </div>
                <div className="cell date">{formatDate(txn.date)}</div>
                <div className="cell description">
                  <span className="txn-name">{txn.name || txn.payee}</span>
                  {txn.memo && <span className="txn-memo">{txn.memo}</span>}
                </div>
                <div className="cell account">
                  <span className="bank-account-name">{txn.bank_account_name}</span>
                </div>
                <div className={`cell amount ${txn.amount < 0 ? 'negative' : 'positive'}`}>
                  {formatCurrency(txn.amount)}
                </div>
                <div className="cell category">
                  {txn.gl_account_name ? (
                    <span className="category-tag">{txn.gl_account_name}</span>
                  ) : txn.suggested_account_name ? (
                    <span className="suggested-tag">
                      <i className="fas fa-magic"></i> {txn.suggested_account_name}
                    </span>
                  ) : (
                    <span className="uncategorized">-</span>
                  )}
                </div>
                <div className="cell status">
                  <span className={`status-badge ${getStatusBadge(txn.status)}`}>
                    {txn.status}
                  </span>
                </div>
                <div className="cell actions">
                  {txn.status === 'unmatched' && (
                    <>
                      <button
                        className="action-btn primary"
                        onClick={() => openMatchModal(txn)}
                        title="Categorize"
                      >
                        <i className="fas fa-tag"></i>
                      </button>
                      <button
                        className="action-btn"
                        onClick={() => handleExclude(txn)}
                        title="Exclude"
                      >
                        <i className="fas fa-ban"></i>
                      </button>
                    </>
                  )}
                  {(txn.status === 'matched' || txn.status === 'excluded') && (
                    <button
                      className="action-btn"
                      onClick={() => handleUndo(txn)}
                      title="Undo"
                    >
                      <i className="fas fa-undo"></i>
                    </button>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-exchange-alt"></i>
              <h3>No Transactions Found</h3>
              <p>No transactions match your current filters.</p>
            </div>
          )}
        </div>
      </div>

      {/* Match/Categorize Modal */}
      {showMatchModal && matchingTransaction && (
        <div className="modal-overlay" onClick={closeMatchModal}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Categorize Transaction</h2>
              <button className="close-btn" onClick={closeMatchModal}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              {/* Transaction Details */}
              <div className="txn-details-card">
                <div className="txn-detail-row">
                  <span className="label">Date:</span>
                  <span className="value">{formatDate(matchingTransaction.date)}</span>
                </div>
                <div className="txn-detail-row">
                  <span className="label">Description:</span>
                  <span className="value">{matchingTransaction.name}</span>
                </div>
                <div className="txn-detail-row">
                  <span className="label">Amount:</span>
                  <span className={`value ${matchingTransaction.amount < 0 ? 'negative' : 'positive'}`}>
                    {formatCurrency(matchingTransaction.amount)}
                  </span>
                </div>
                <div className="txn-detail-row">
                  <span className="label">Bank Account:</span>
                  <span className="value">{matchingTransaction.bank_account_name}</span>
                </div>
              </div>

              {/* Categorization Form */}
              <div className="form-group">
                <label>Category (GL Account) *</label>
                <select
                  value={categorizeForm.account_id}
                  onChange={(e) => setCategorizeForm(prev => ({ ...prev, account_id: e.target.value }))}
                  required
                >
                  <option value="">Select Account</option>
                  {Object.entries(groupedAccounts).map(([type, accounts]) => (
                    <optgroup key={type} label={type.charAt(0).toUpperCase() + type.slice(1)}>
                      {accounts.map(a => (
                        <option key={a.id} value={a.id}>
                          {a.account_number} - {a.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Payee</label>
                <input
                  type="text"
                  value={categorizeForm.payee}
                  onChange={(e) => setCategorizeForm(prev => ({ ...prev, payee: e.target.value }))}
                  placeholder="Payee name"
                />
              </div>

              <div className="form-group">
                <label>Memo</label>
                <input
                  type="text"
                  value={categorizeForm.memo}
                  onChange={(e) => setCategorizeForm(prev => ({ ...prev, memo: e.target.value }))}
                  placeholder="Additional notes"
                />
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input type="checkbox" id="createRule" />
                  Create a rule to auto-categorize similar transactions
                </label>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={closeMatchModal}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleCategorize}>
                <i className="fas fa-check"></i> Categorize
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BankTransactions;
