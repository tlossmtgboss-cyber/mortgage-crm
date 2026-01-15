import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';

function TrialBalance() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [reportData, setReportData] = useState(null);
  const [expandedTypes, setExpandedTypes] = useState(new Set(['asset', 'liability', 'equity', 'revenue', 'expense']));

  // Report options
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().split('T')[0]);
  const [showZeroBalances, setShowZeroBalances] = useState(false);
  const [reportType, setReportType] = useState('adjusted'); // unadjusted, adjusted, post_closing

  // Fetch report data
  const fetchReportData = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        as_of_date: asOfDate,
        include_zero_balances: showZeroBalances,
        type: reportType,
      };

      const data = await accountingAPI.getTrialBalanceReport(params);
      setReportData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching Trial Balance:', err);
      setLoading(false);
    }
  }, [asOfDate, showZeroBalances, reportType]);

  useEffect(() => {
    fetchReportData();
  }, [fetchReportData]);

  // Format currency
  const formatCurrency = (amount) => {
    if (!amount || amount === 0) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(Math.abs(amount));
  };

  // Format date for display
  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Toggle section expansion
  const toggleType = (type) => {
    setExpandedTypes(prev => {
      const newSet = new Set(prev);
      if (newSet.has(type)) {
        newSet.delete(type);
      } else {
        newSet.add(type);
      }
      return newSet;
    });
  };

  // Expand/Collapse all
  const expandAll = () => {
    setExpandedTypes(new Set(['asset', 'liability', 'equity', 'revenue', 'expense']));
  };

  const collapseAll = () => {
    setExpandedTypes(new Set());
  };

  // Export to CSV
  const handleExportCSV = () => {
    if (!reportData) return;

    const rows = [];
    rows.push(['Trial Balance']);
    rows.push([`As of ${formatDate(asOfDate)}`]);
    rows.push([]);
    rows.push(['Account Number', 'Account Name', 'Debit', 'Credit']);

    reportData.accounts?.forEach(account => {
      rows.push([
        account.account_number,
        account.name,
        account.debit || '',
        account.credit || '',
      ]);
    });

    rows.push([]);
    rows.push(['', 'TOTALS', reportData.total_debits, reportData.total_credits]);

    const csvContent = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trial-balance-${asOfDate}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Get accounts by type
  const getAccountsByType = (type) => {
    return (reportData?.accounts || []).filter(a => a.account_type === type);
  };

  // Calculate type totals
  const getTypeTotals = (type) => {
    const accounts = getAccountsByType(type);
    return {
      debits: accounts.reduce((sum, a) => sum + (a.debit || 0), 0),
      credits: accounts.reduce((sum, a) => sum + (a.credit || 0), 0),
    };
  };

  // Get type label
  const getTypeLabel = (type) => {
    const labels = {
      asset: 'Assets',
      liability: 'Liabilities',
      equity: 'Equity',
      revenue: 'Revenue',
      expense: 'Expenses',
    };
    return labels[type] || type;
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Trial Balance...</p>
        </div>
      </div>
    );
  }

  const totalDebits = reportData?.total_debits || 0;
  const totalCredits = reportData?.total_credits || 0;
  const isBalanced = Math.abs(totalDebits - totalCredits) < 0.01;
  const accountTypes = ['asset', 'liability', 'equity', 'revenue', 'expense'];

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page financial-report trial-balance">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Trial Balance.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page financial-report trial-balance">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-list-ol"></i> Trial Balance</h1>
            <p className="subtitle">As of {formatDate(asOfDate)}</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={handleExportCSV}>
            <i className="fas fa-file-csv"></i> Export CSV
          </button>
          <button className="btn-secondary" onClick={() => window.print()}>
            <i className="fas fa-file-pdf"></i> Print / PDF
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar report-toolbar">
        <div className="toolbar-left">
          <div className="date-picker">
            <label>As of Date:</label>
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
            />
          </div>

          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className="filter-select"
          >
            <option value="unadjusted">Unadjusted Trial Balance</option>
            <option value="adjusted">Adjusted Trial Balance</option>
            <option value="post_closing">Post-Closing Trial Balance</option>
          </select>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showZeroBalances}
              onChange={(e) => setShowZeroBalances(e.target.checked)}
            />
            Show Zero Balances
          </label>
        </div>

        <div className="toolbar-right">
          <button className="toolbar-btn" onClick={expandAll} title="Expand All">
            <i className="fas fa-expand-alt"></i>
          </button>
          <button className="toolbar-btn" onClick={collapseAll} title="Collapse All">
            <i className="fas fa-compress-alt"></i>
          </button>
          <button className="toolbar-btn" onClick={fetchReportData} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="report-summary-cards">
        <div className="report-summary-card">
          <span className="label">Total Debits</span>
          <span className="value">{formatCurrency(totalDebits)}</span>
        </div>
        <div className="report-summary-card">
          <span className="label">Total Credits</span>
          <span className="value">{formatCurrency(totalCredits)}</span>
        </div>
        <div className={`report-summary-card ${isBalanced ? 'success' : 'danger'}`}>
          <span className="label">Balance Status</span>
          <span className="value">
            {isBalanced ? (
              <><i className="fas fa-check-circle"></i> Balanced</>
            ) : (
              <><i className="fas fa-exclamation-triangle"></i> Out of Balance by {formatCurrency(Math.abs(totalDebits - totalCredits))}</>
            )}
          </span>
        </div>
        <div className="report-summary-card">
          <span className="label">Total Accounts</span>
          <span className="value">{reportData?.accounts?.length || 0}</span>
        </div>
      </div>

      {/* Report Content */}
      <div className="report-container trial-balance-report">
        <div className="report-header-row">
          <div className="company-name">{reportData?.company_name || 'Company Name'}</div>
          <div className="report-title">
            {reportType === 'unadjusted' && 'Unadjusted '}
            {reportType === 'post_closing' && 'Post-Closing '}
            Trial Balance
          </div>
          <div className="report-period">As of {formatDate(asOfDate)}</div>
        </div>

        {/* Column Headers */}
        <div className="trial-balance-header">
          <div className="col-number">Account #</div>
          <div className="col-name">Account Name</div>
          <div className="col-debit">Debit</div>
          <div className="col-credit">Credit</div>
        </div>

        {/* Accounts by Type */}
        {accountTypes.map(type => {
          const accounts = getAccountsByType(type);
          const totals = getTypeTotals(type);

          if (accounts.length === 0 && !showZeroBalances) return null;

          return (
            <div key={type} className="trial-balance-section">
              <div
                className="type-header clickable"
                onClick={() => toggleType(type)}
              >
                <i className={`fas fa-chevron-${expandedTypes.has(type) ? 'down' : 'right'}`}></i>
                <span className="type-name">{getTypeLabel(type)}</span>
                <span className="type-count">({accounts.length} accounts)</span>
                <div className="type-totals">
                  <span className="debit">{formatCurrency(totals.debits)}</span>
                  <span className="credit">{formatCurrency(totals.credits)}</span>
                </div>
              </div>

              {expandedTypes.has(type) && (
                <div className="type-accounts">
                  {accounts.map(account => (
                    <div key={account.id} className="account-row">
                      <div className="col-number">{account.account_number}</div>
                      <div className="col-name">{account.name}</div>
                      <div className="col-debit">{formatCurrency(account.debit)}</div>
                      <div className="col-credit">{formatCurrency(account.credit)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Totals Row */}
        <div className="trial-balance-totals">
          <div className="col-number"></div>
          <div className="col-name"><strong>TOTALS</strong></div>
          <div className="col-debit">
            <strong>{formatCurrency(totalDebits)}</strong>
          </div>
          <div className="col-credit">
            <strong>{formatCurrency(totalCredits)}</strong>
          </div>
        </div>

        {/* Balance Check */}
        {!isBalanced && (
          <div className="balance-warning">
            <i className="fas fa-exclamation-triangle"></i>
            <span>
              Warning: Trial Balance is out of balance by {formatCurrency(Math.abs(totalDebits - totalCredits))}.
              Please review journal entries for errors.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default TrialBalance;
