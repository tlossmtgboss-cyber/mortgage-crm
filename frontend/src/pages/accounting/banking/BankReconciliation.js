import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function BankReconciliation() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [reconciliationHistory, setReconciliationHistory] = useState([]);
  const [activeReconciliation, setActiveReconciliation] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [clearedTransactions, setClearedTransactions] = useState(new Set());

  // Reconciliation setup
  const [selectedAccount, setSelectedAccount] = useState(searchParams.get('account') || '');
  const [statementDate, setStatementDate] = useState(new Date().toISOString().split('T')[0]);
  const [statementBalance, setStatementBalance] = useState('');
  const [showSetupModal, setShowSetupModal] = useState(false);

  // Calculated values
  const [reconciliationSummary, setReconciliationSummary] = useState({
    beginning_balance: 0,
    cleared_deposits: 0,
    cleared_payments: 0,
    cleared_balance: 0,
    statement_balance: 0,
    difference: 0,
  });

  // Fetch bank accounts
  const fetchBankAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getBankAccounts();
      setBankAccounts(data?.accounts || []);
    } catch (err) {
      console.error('Error fetching bank accounts:', err);
    }
  }, []);

  // Fetch reconciliation history
  const fetchReconciliationHistory = useCallback(async () => {
    try {
      const params = selectedAccount ? { bank_account_id: selectedAccount } : {};
      const data = await accountingAPI.getReconciliationHistory(params);
      setReconciliationHistory(data?.reconciliations || []);
    } catch (err) {
      console.error('Error fetching history:', err);
    }
  }, [selectedAccount]);

  // Fetch transactions for reconciliation
  const fetchTransactions = useCallback(async () => {
    if (!activeReconciliation) return;

    try {
      setLoading(true);
      const data = await accountingAPI.getReconciliationTransactions(activeReconciliation.id);
      setTransactions(data?.transactions || []);

      // Initialize cleared transactions
      const cleared = new Set(
        (data?.transactions || [])
          .filter(t => t.is_cleared)
          .map(t => t.id)
      );
      setClearedTransactions(cleared);

      setLoading(false);
    } catch (err) {
      console.error('Error fetching transactions:', err);
      setLoading(false);
    }
  }, [activeReconciliation]);

  useEffect(() => {
    fetchBankAccounts();
  }, [fetchBankAccounts]);

  useEffect(() => {
    if (selectedAccount) {
      fetchReconciliationHistory();
    }
  }, [selectedAccount, fetchReconciliationHistory]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // Calculate reconciliation summary
  useEffect(() => {
    if (!activeReconciliation || !transactions.length) return;

    const clearedTxns = transactions.filter(t => clearedTransactions.has(t.id));
    const deposits = clearedTxns.filter(t => t.amount > 0).reduce((sum, t) => sum + t.amount, 0);
    const payments = clearedTxns.filter(t => t.amount < 0).reduce((sum, t) => sum + Math.abs(t.amount), 0);
    const clearedBalance = activeReconciliation.beginning_balance + deposits - payments;
    const stmtBalance = parseFloat(activeReconciliation.statement_balance) || 0;

    setReconciliationSummary({
      beginning_balance: activeReconciliation.beginning_balance,
      cleared_deposits: deposits,
      cleared_payments: payments,
      cleared_balance: clearedBalance,
      statement_balance: stmtBalance,
      difference: stmtBalance - clearedBalance,
    });
  }, [activeReconciliation, transactions, clearedTransactions]);

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

  // Start new reconciliation
  const handleStartReconciliation = async () => {
    if (!selectedAccount || !statementDate || !statementBalance) {
      toast.error('Please fill in all required fields.');
      return;
    }

    try {
      const data = await accountingAPI.startReconciliation({
        bank_account_id: selectedAccount,
        statement_date: statementDate,
        statement_balance: parseFloat(statementBalance),
      });

      setActiveReconciliation(data);
      setShowSetupModal(false);
    } catch (err) {
      console.error('Error starting reconciliation:', err);
      toast.error('Failed to start reconciliation');
    }
  };

  // Resume existing reconciliation
  const handleResumeReconciliation = async (reconciliation) => {
    try {
      const data = await accountingAPI.getReconciliation(reconciliation.id);
      setActiveReconciliation(data);
    } catch (err) {
      console.error('Error resuming reconciliation:', err);
      toast.error('Failed to resume reconciliation');
    }
  };

  // Toggle transaction cleared status
  const toggleCleared = (txnId) => {
    setClearedTransactions(prev => {
      const newSet = new Set(prev);
      if (newSet.has(txnId)) {
        newSet.delete(txnId);
      } else {
        newSet.add(txnId);
      }
      return newSet;
    });
  };

  // Clear all / Unclear all
  const clearAll = () => {
    setClearedTransactions(new Set(transactions.map(t => t.id)));
  };

  const unclearAll = () => {
    setClearedTransactions(new Set());
  };

  // Save progress
  const handleSaveProgress = async () => {
    try {
      setSaving(true);
      await accountingAPI.saveReconciliationProgress(activeReconciliation.id, {
        cleared_transaction_ids: Array.from(clearedTransactions),
      });
      setSaving(false);
      toast.success('Progress saved.');
    } catch (err) {
      console.error('Error saving progress:', err);
      toast.error('Failed to save progress');
      setSaving(false);
    }
  };

  // Complete reconciliation
  const handleComplete = async () => {
    if (Math.abs(reconciliationSummary.difference) > 0.01) {
      toast.success('The reconciliation does not balance. Please review your cleared transactions.');
      return;
    }

    if (!window.confirm('Are you sure you want to complete this reconciliation? This action cannot be undone.')) {
      return;
    }

    try {
      setSaving(true);
      await accountingAPI.completeReconciliation(activeReconciliation.id, {
        cleared_transaction_ids: Array.from(clearedTransactions),
      });

      setActiveReconciliation(null);
      fetchReconciliationHistory();
      setSaving(false);
      toast.success('Reconciliation completed successfully!');
    } catch (err) {
      console.error('Error completing reconciliation:', err);
      toast.error('Failed to complete reconciliation');
      setSaving(false);
    }
  };

  // Cancel reconciliation
  const handleCancel = async () => {
    if (!window.confirm('Are you sure you want to cancel this reconciliation? All progress will be lost.')) {
      return;
    }

    try {
      await accountingAPI.cancelReconciliation(activeReconciliation.id);
      setActiveReconciliation(null);
      fetchReconciliationHistory();
    } catch (err) {
      console.error('Error canceling reconciliation:', err);
      toast.error('Failed to cancel reconciliation');
    }
  };

  // Get account by ID
  const getAccountName = (accountId) => {
    const account = bankAccounts.find(a => a.id === accountId);
    return account?.name || 'Unknown';
  };

  if (loading && activeReconciliation) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Reconciliation...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page bank-reconciliation">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Bank Reconciliation.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page bank-reconciliation">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => activeReconciliation ? setActiveReconciliation(null) : navigate('/accounting/banking/accounts')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-check-double"></i> Bank Reconciliation</h1>
            <p className="subtitle">
              {activeReconciliation
                ? `Reconciling ${getAccountName(activeReconciliation.bank_account_id)} - ${formatDate(activeReconciliation.statement_date)}`
                : 'Match your books to your bank statement'
              }
            </p>
          </div>
        </div>
        <div className="header-right">
          {!activeReconciliation && (
            <button className="btn-primary" onClick={() => setShowSetupModal(true)}>
              <i className="fas fa-plus"></i> New Reconciliation
            </button>
          )}
        </div>
      </div>

      {activeReconciliation ? (
        <>
          {/* Reconciliation Summary */}
          <div className="reconciliation-summary">
            <div className="summary-section">
              <h3>Reconciliation Progress</h3>
              <div className="summary-grid">
                <div className="summary-item">
                  <span className="label">Beginning Balance</span>
                  <span className="value">{formatCurrency(reconciliationSummary.beginning_balance)}</span>
                </div>
                <div className="summary-item positive">
                  <span className="label">Cleared Deposits (+)</span>
                  <span className="value">{formatCurrency(reconciliationSummary.cleared_deposits)}</span>
                </div>
                <div className="summary-item negative">
                  <span className="label">Cleared Payments (-)</span>
                  <span className="value">{formatCurrency(reconciliationSummary.cleared_payments)}</span>
                </div>
                <div className="summary-item">
                  <span className="label">Cleared Balance</span>
                  <span className="value">{formatCurrency(reconciliationSummary.cleared_balance)}</span>
                </div>
                <div className="summary-item">
                  <span className="label">Statement Balance</span>
                  <span className="value">{formatCurrency(reconciliationSummary.statement_balance)}</span>
                </div>
                <div className={`summary-item difference ${Math.abs(reconciliationSummary.difference) < 0.01 ? 'balanced' : 'unbalanced'}`}>
                  <span className="label">Difference</span>
                  <span className="value">{formatCurrency(reconciliationSummary.difference)}</span>
                </div>
              </div>
            </div>

            <div className="action-buttons">
              <button className="btn-secondary" onClick={handleCancel}>
                Cancel
              </button>
              <button className="btn-secondary" onClick={handleSaveProgress} disabled={saving}>
                {saving ? 'Saving...' : 'Save Progress'}
              </button>
              <button
                className="btn-primary"
                onClick={handleComplete}
                disabled={saving || Math.abs(reconciliationSummary.difference) > 0.01}
              >
                <i className="fas fa-check"></i> Complete Reconciliation
              </button>
            </div>
          </div>

          {/* Toolbar */}
          <div className="toolbar">
            <div className="toolbar-left">
              <span className="cleared-count">
                {clearedTransactions.size} of {transactions.length} cleared
              </span>
            </div>
            <div className="toolbar-right">
              <button className="btn-link" onClick={clearAll}>Clear All</button>
              <button className="btn-link" onClick={unclearAll}>Unclear All</button>
            </div>
          </div>

          {/* Transactions Table */}
          <div className="data-table reconciliation-table">
            <div className="table-header">
              <div className="header-cell cleared">Cleared</div>
              <div className="header-cell date">Date</div>
              <div className="header-cell type">Type</div>
              <div className="header-cell description">Description</div>
              <div className="header-cell amount">Payment</div>
              <div className="header-cell amount">Deposit</div>
            </div>

            <div className="table-body">
              {transactions.length > 0 ? (
                transactions.map(txn => (
                  <div
                    key={txn.id}
                    className={`table-row ${clearedTransactions.has(txn.id) ? 'cleared' : ''}`}
                    onClick={() => toggleCleared(txn.id)}
                  >
                    <div className="cell cleared">
                      <input
                        type="checkbox"
                        checked={clearedTransactions.has(txn.id)}
                        onChange={() => toggleCleared(txn.id)}
                        onClick={e => e.stopPropagation()}
                      />
                    </div>
                    <div className="cell date">{formatDate(txn.date)}</div>
                    <div className="cell type">{txn.type}</div>
                    <div className="cell description">
                      <span className="txn-payee">{txn.payee || txn.name}</span>
                      {txn.reference && <span className="txn-ref">#{txn.reference}</span>}
                    </div>
                    <div className="cell amount negative">
                      {txn.amount < 0 ? formatCurrency(Math.abs(txn.amount)) : ''}
                    </div>
                    <div className="cell amount positive">
                      {txn.amount > 0 ? formatCurrency(txn.amount) : ''}
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">
                  <i className="fas fa-check-circle"></i>
                  <h3>No Transactions</h3>
                  <p>There are no unreconciled transactions for this period.</p>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Account Selection */}
          <div className="toolbar">
            <div className="toolbar-left">
              <select
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="filter-select"
              >
                <option value="">Select Bank Account</option>
                {bankAccounts.map(acc => (
                  <option key={acc.id} value={acc.id}>{acc.name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Reconciliation History */}
          <div className="section">
            <h3>Reconciliation History</h3>

            {reconciliationHistory.length > 0 ? (
              <div className="data-table">
                <div className="table-header">
                  <div className="header-cell">Account</div>
                  <div className="header-cell">Statement Date</div>
                  <div className="header-cell">Statement Balance</div>
                  <div className="header-cell">Status</div>
                  <div className="header-cell">Completed</div>
                  <div className="header-cell actions">Actions</div>
                </div>

                <div className="table-body">
                  {reconciliationHistory.map(rec => (
                    <div key={rec.id} className="table-row">
                      <div className="cell">{getAccountName(rec.bank_account_id)}</div>
                      <div className="cell">{formatDate(rec.statement_date)}</div>
                      <div className="cell amount">{formatCurrency(rec.statement_balance)}</div>
                      <div className="cell">
                        <span className={`status-badge ${rec.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>
                          {rec.status}
                        </span>
                      </div>
                      <div className="cell">{rec.completed_at ? formatDate(rec.completed_at) : '-'}</div>
                      <div className="cell actions">
                        {rec.status === 'in_progress' && (
                          <button
                            className="action-btn primary"
                            onClick={() => handleResumeReconciliation(rec)}
                            title="Resume"
                          >
                            <i className="fas fa-play"></i>
                          </button>
                        )}
                        {rec.status === 'completed' && (
                          <button
                            className="action-btn"
                            onClick={() => navigate(`/accounting/banking/reconciliation/${rec.id}`)}
                            title="View Details"
                          >
                            <i className="fas fa-eye"></i>
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <i className="fas fa-check-double"></i>
                <h3>No Reconciliation History</h3>
                <p>
                  {selectedAccount
                    ? 'Start your first reconciliation for this account.'
                    : 'Select a bank account to view reconciliation history.'}
                </p>
                {selectedAccount && (
                  <button className="btn-primary" onClick={() => setShowSetupModal(true)}>
                    <i className="fas fa-plus"></i> Start Reconciliation
                  </button>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {/* Setup Modal */}
      {showSetupModal && (
        <div className="modal-overlay" onClick={() => setShowSetupModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Start Reconciliation</h2>
              <button className="close-btn" onClick={() => setShowSetupModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              <div className="info-box">
                <i className="fas fa-info-circle"></i>
                <p>Enter the ending date and balance from your bank statement to begin reconciling.</p>
              </div>

              <div className="form-group">
                <label>Bank Account *</label>
                <select
                  value={selectedAccount}
                  onChange={(e) => setSelectedAccount(e.target.value)}
                  required
                >
                  <option value="">Select Account</option>
                  {bankAccounts.map(acc => (
                    <option key={acc.id} value={acc.id}>{acc.name}</option>
                  ))}
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Statement Date *</label>
                  <input
                    type="date"
                    value={statementDate}
                    onChange={(e) => setStatementDate(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Statement Ending Balance *</label>
                  <input
                    type="number"
                    value={statementBalance}
                    onChange={(e) => setStatementBalance(e.target.value)}
                    placeholder="0.00"
                    step="0.01"
                    required
                  />
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowSetupModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleStartReconciliation}>
                <i className="fas fa-play"></i> Start Reconciliation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BankReconciliation;
