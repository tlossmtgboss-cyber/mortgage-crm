import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../services/accountingApi';
import './AccountingDashboard.css';

function AccountingDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Dashboard data
  const [profitLoss, setProfitLoss] = useState(null);
  const [balanceSheet, setBalanceSheet] = useState(null);
  const [cashFlow, setCashFlow] = useState(null);
  const [arAging, setArAging] = useState(null);
  const [apAging, setApAging] = useState(null);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [recentEntries, setRecentEntries] = useState([]);
  const [financialRatios, setFinancialRatios] = useState(null);

  // Date range
  const [dateRange, setDateRange] = useState('mtd'); // mtd, qtd, ytd, custom

  // Fetch all dashboard data
  const fetchDashboardData = useCallback(async () => {
    try {
      setError(null);

      // Build date params based on range
      const today = new Date();
      let startDate, endDate;
      endDate = today.toISOString().split('T')[0];

      switch (dateRange) {
        case 'mtd':
          startDate = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
          break;
        case 'qtd':
          const quarter = Math.floor(today.getMonth() / 3);
          startDate = new Date(today.getFullYear(), quarter * 3, 1).toISOString().split('T')[0];
          break;
        case 'ytd':
          startDate = new Date(today.getFullYear(), 0, 1).toISOString().split('T')[0];
          break;
        default:
          startDate = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
      }

      const params = { start_date: startDate, end_date: endDate };

      // Fetch all data in parallel
      const results = await Promise.allSettled([
        accountingAPI.getProfitLoss(params),
        accountingAPI.getBalanceSheet({ as_of_date: endDate }),
        accountingAPI.getCashFlow(params),
        accountingAPI.getARAgingReport(),
        accountingAPI.getAPAgingReport(),
        accountingAPI.getBankAccounts(),
        accountingAPI.getJournalEntries({ limit: 10, status: 'posted' }),
        accountingAPI.getFinancialRatios(params),
      ]);

      // Process results
      if (results[0].status === 'fulfilled') setProfitLoss(results[0].value);
      if (results[1].status === 'fulfilled') setBalanceSheet(results[1].value);
      if (results[2].status === 'fulfilled') setCashFlow(results[2].value);
      if (results[3].status === 'fulfilled') setArAging(results[3].value);
      if (results[4].status === 'fulfilled') setApAging(results[4].value);
      if (results[5].status === 'fulfilled') setBankAccounts(results[5].value?.accounts || []);
      if (results[6].status === 'fulfilled') setRecentEntries(results[6].value?.entries || []);
      if (results[7].status === 'fulfilled') setFinancialRatios(results[7].value);

      setLoading(false);
      setRefreshing(false);
    } catch (err) {
      console.error('Error fetching accounting dashboard data:', err);
      setError('Failed to load accounting dashboard. Please try again.');
      setLoading(false);
      setRefreshing(false);
    }
  }, [dateRange]);

  useEffect(() => {
    fetchDashboardData();

    // Auto-refresh every 5 minutes
    const interval = setInterval(fetchDashboardData, 300000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboardData();
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount || 0);
  };

  const formatCurrencyDecimal = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount || 0);
  };

  const formatPercent = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format((value || 0) / 100);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const getChangeClass = (value) => {
    if (value > 0) return 'positive';
    if (value < 0) return 'negative';
    return 'neutral';
  };

  if (loading) {
    return (
      <div className="accounting-dashboard loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Accounting Dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="accounting-dashboard">
        <div className="dashboard-header">
          <div className="header-left">
            <h1><i className="fas fa-calculator"></i> Accounting</h1>
            <p className="subtitle">Full double-entry accounting system</p>
          </div>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={fetchDashboardData}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  // Calculate totals from data
  const totalRevenue = profitLoss?.revenue?.total || 0;
  const totalExpenses = profitLoss?.expenses?.total || 0;
  const netIncome = profitLoss?.net_income || (totalRevenue - totalExpenses);
  const grossMargin = totalRevenue > 0 ? ((totalRevenue - (profitLoss?.cost_of_revenue?.total || 0)) / totalRevenue) * 100 : 0;
  const totalCash = bankAccounts.reduce((sum, acc) => sum + (acc.current_balance || 0), 0);
  const totalAR = arAging?.total_outstanding || 0;
  const totalAP = apAging?.total_outstanding || 0;

  return (
    <div className="accounting-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-left">
          <h1><i className="fas fa-calculator"></i> Accounting</h1>
          <p className="subtitle">Financial overview and management</p>
        </div>
        <div className="header-right">
          <div className="date-range-selector">
            <button
              className={`range-btn ${dateRange === 'mtd' ? 'active' : ''}`}
              onClick={() => setDateRange('mtd')}
            >
              MTD
            </button>
            <button
              className={`range-btn ${dateRange === 'qtd' ? 'active' : ''}`}
              onClick={() => setDateRange('qtd')}
            >
              QTD
            </button>
            <button
              className={`range-btn ${dateRange === 'ytd' ? 'active' : ''}`}
              onClick={() => setDateRange('ytd')}
            >
              YTD
            </button>
          </div>
          <button
            className={`refresh-btn ${refreshing ? 'refreshing' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <i className={`fas fa-sync-alt ${refreshing ? 'fa-spin' : ''}`}></i>
          </button>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="quick-actions">
        <button className="action-btn primary" onClick={() => navigate('/accounting/invoices/new')}>
          <i className="fas fa-file-invoice-dollar"></i>
          <span>New Invoice</span>
        </button>
        <button className="action-btn" onClick={() => navigate('/accounting/bills/new')}>
          <i className="fas fa-file-invoice"></i>
          <span>Enter Bill</span>
        </button>
        <button className="action-btn" onClick={() => navigate('/accounting/journal-entries/new')}>
          <i className="fas fa-exchange-alt"></i>
          <span>Journal Entry</span>
        </button>
        <button className="action-btn" onClick={() => navigate('/accounting/payments/receive')}>
          <i className="fas fa-hand-holding-usd"></i>
          <span>Receive Payment</span>
        </button>
        <button className="action-btn" onClick={() => navigate('/accounting/payments/pay')}>
          <i className="fas fa-money-check-alt"></i>
          <span>Pay Bills</span>
        </button>
        <button className="action-btn" onClick={() => navigate('/accounting/banking')}>
          <i className="fas fa-university"></i>
          <span>Bank Feeds</span>
        </button>
      </div>

      {/* Key Metrics */}
      <div className="metrics-grid">
        <div className="metric-card revenue">
          <div className="metric-icon">
            <i className="fas fa-arrow-up"></i>
          </div>
          <div className="metric-content">
            <span className="metric-label">Revenue</span>
            <span className="metric-value">{formatCurrency(totalRevenue)}</span>
            {profitLoss?.revenue_change_pct && (
              <span className={`metric-change ${getChangeClass(profitLoss.revenue_change_pct)}`}>
                {profitLoss.revenue_change_pct > 0 ? '+' : ''}{profitLoss.revenue_change_pct.toFixed(1)}% vs prior
              </span>
            )}
          </div>
        </div>

        <div className="metric-card expenses">
          <div className="metric-icon">
            <i className="fas fa-arrow-down"></i>
          </div>
          <div className="metric-content">
            <span className="metric-label">Expenses</span>
            <span className="metric-value">{formatCurrency(totalExpenses)}</span>
            {profitLoss?.expense_change_pct && (
              <span className={`metric-change ${getChangeClass(-profitLoss.expense_change_pct)}`}>
                {profitLoss.expense_change_pct > 0 ? '+' : ''}{profitLoss.expense_change_pct.toFixed(1)}% vs prior
              </span>
            )}
          </div>
        </div>

        <div className={`metric-card net-income ${netIncome >= 0 ? 'positive' : 'negative'}`}>
          <div className="metric-icon">
            <i className="fas fa-chart-line"></i>
          </div>
          <div className="metric-content">
            <span className="metric-label">Net Income</span>
            <span className="metric-value">{formatCurrency(netIncome)}</span>
            <span className="metric-change">{formatPercent(grossMargin)} gross margin</span>
          </div>
        </div>

        <div className="metric-card cash">
          <div className="metric-icon">
            <i className="fas fa-wallet"></i>
          </div>
          <div className="metric-content">
            <span className="metric-label">Cash Position</span>
            <span className="metric-value">{formatCurrency(totalCash)}</span>
            <span className="metric-change">{bankAccounts.length} account{bankAccounts.length !== 1 ? 's' : ''}</span>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="content-grid">
        {/* AR Summary */}
        <div className="dashboard-card ar-summary">
          <div className="card-header">
            <h3><i className="fas fa-file-invoice-dollar"></i> Accounts Receivable</h3>
            <button className="view-all-btn" onClick={() => navigate('/accounting/ar')}>
              View All <i className="fas fa-chevron-right"></i>
            </button>
          </div>
          <div className="card-content">
            <div className="ar-total">
              <span className="label">Total Outstanding</span>
              <span className="value">{formatCurrency(totalAR)}</span>
            </div>
            <div className="aging-breakdown">
              <div className="aging-bucket current">
                <span className="bucket-label">Current</span>
                <span className="bucket-value">{formatCurrency(arAging?.buckets?.current || 0)}</span>
              </div>
              <div className="aging-bucket">
                <span className="bucket-label">1-30 Days</span>
                <span className="bucket-value">{formatCurrency(arAging?.buckets?.days_1_30 || 0)}</span>
              </div>
              <div className="aging-bucket warning">
                <span className="bucket-label">31-60 Days</span>
                <span className="bucket-value">{formatCurrency(arAging?.buckets?.days_31_60 || 0)}</span>
              </div>
              <div className="aging-bucket danger">
                <span className="bucket-label">61-90 Days</span>
                <span className="bucket-value">{formatCurrency(arAging?.buckets?.days_61_90 || 0)}</span>
              </div>
              <div className="aging-bucket critical">
                <span className="bucket-label">90+ Days</span>
                <span className="bucket-value">{formatCurrency(arAging?.buckets?.days_over_90 || 0)}</span>
              </div>
            </div>
            {arAging?.overdue_count > 0 && (
              <div className="overdue-alert">
                <i className="fas fa-exclamation-circle"></i>
                <span>{arAging.overdue_count} invoice{arAging.overdue_count !== 1 ? 's' : ''} overdue</span>
              </div>
            )}
          </div>
        </div>

        {/* AP Summary */}
        <div className="dashboard-card ap-summary">
          <div className="card-header">
            <h3><i className="fas fa-file-invoice"></i> Accounts Payable</h3>
            <button className="view-all-btn" onClick={() => navigate('/accounting/ap')}>
              View All <i className="fas fa-chevron-right"></i>
            </button>
          </div>
          <div className="card-content">
            <div className="ap-total">
              <span className="label">Total Outstanding</span>
              <span className="value">{formatCurrency(totalAP)}</span>
            </div>
            <div className="aging-breakdown">
              <div className="aging-bucket current">
                <span className="bucket-label">Current</span>
                <span className="bucket-value">{formatCurrency(apAging?.buckets?.current || 0)}</span>
              </div>
              <div className="aging-bucket">
                <span className="bucket-label">1-30 Days</span>
                <span className="bucket-value">{formatCurrency(apAging?.buckets?.days_1_30 || 0)}</span>
              </div>
              <div className="aging-bucket warning">
                <span className="bucket-label">31-60 Days</span>
                <span className="bucket-value">{formatCurrency(apAging?.buckets?.days_31_60 || 0)}</span>
              </div>
              <div className="aging-bucket danger">
                <span className="bucket-label">61-90 Days</span>
                <span className="bucket-value">{formatCurrency(apAging?.buckets?.days_61_90 || 0)}</span>
              </div>
              <div className="aging-bucket critical">
                <span className="bucket-label">90+ Days</span>
                <span className="bucket-value">{formatCurrency(apAging?.buckets?.days_over_90 || 0)}</span>
              </div>
            </div>
            {apAging?.pending_approval_count > 0 && (
              <div className="approval-alert">
                <i className="fas fa-clock"></i>
                <span>{apAging.pending_approval_count} bill{apAging.pending_approval_count !== 1 ? 's' : ''} pending approval</span>
              </div>
            )}
          </div>
        </div>

        {/* Bank Accounts */}
        <div className="dashboard-card bank-accounts">
          <div className="card-header">
            <h3><i className="fas fa-university"></i> Bank Accounts</h3>
            <button className="view-all-btn" onClick={() => navigate('/accounting/banking')}>
              Manage <i className="fas fa-chevron-right"></i>
            </button>
          </div>
          <div className="card-content">
            {bankAccounts.length > 0 ? (
              <div className="bank-list">
                {bankAccounts.slice(0, 4).map((account) => (
                  <div key={account.id} className="bank-item">
                    <div className="bank-info">
                      <span className="bank-name">{account.account_name}</span>
                      <span className="bank-institution">{account.institution_name}</span>
                    </div>
                    <div className="bank-balance">
                      <span className={`balance ${account.current_balance >= 0 ? 'positive' : 'negative'}`}>
                        {formatCurrencyDecimal(account.current_balance)}
                      </span>
                      {account.plaid_status === 'active' && (
                        <span className="sync-status connected">
                          <i className="fas fa-link"></i> Connected
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <i className="fas fa-university"></i>
                <p>No bank accounts connected</p>
                <button className="connect-btn" onClick={() => navigate('/accounting/banking/connect')}>
                  Connect Bank
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Financial Ratios */}
        <div className="dashboard-card financial-ratios">
          <div className="card-header">
            <h3><i className="fas fa-percentage"></i> Financial Ratios</h3>
            <button className="view-all-btn" onClick={() => navigate('/accounting/reports')}>
              Reports <i className="fas fa-chevron-right"></i>
            </button>
          </div>
          <div className="card-content">
            <div className="ratios-grid">
              <div className="ratio-item">
                <span className="ratio-label">Current Ratio</span>
                <span className="ratio-value">{(financialRatios?.current_ratio || 0).toFixed(2)}</span>
                <span className={`ratio-status ${(financialRatios?.current_ratio || 0) >= 1.5 ? 'good' : 'warning'}`}>
                  {(financialRatios?.current_ratio || 0) >= 1.5 ? 'Healthy' : 'Watch'}
                </span>
              </div>
              <div className="ratio-item">
                <span className="ratio-label">Quick Ratio</span>
                <span className="ratio-value">{(financialRatios?.quick_ratio || 0).toFixed(2)}</span>
                <span className={`ratio-status ${(financialRatios?.quick_ratio || 0) >= 1.0 ? 'good' : 'warning'}`}>
                  {(financialRatios?.quick_ratio || 0) >= 1.0 ? 'Healthy' : 'Watch'}
                </span>
              </div>
              <div className="ratio-item">
                <span className="ratio-label">Debt-to-Equity</span>
                <span className="ratio-value">{(financialRatios?.debt_to_equity || 0).toFixed(2)}</span>
                <span className={`ratio-status ${(financialRatios?.debt_to_equity || 0) <= 2.0 ? 'good' : 'warning'}`}>
                  {(financialRatios?.debt_to_equity || 0) <= 2.0 ? 'Healthy' : 'High'}
                </span>
              </div>
              <div className="ratio-item">
                <span className="ratio-label">Gross Margin</span>
                <span className="ratio-value">{formatPercent(financialRatios?.gross_margin || grossMargin)}</span>
                <span className={`ratio-status ${(financialRatios?.gross_margin || grossMargin) >= 30 ? 'good' : 'warning'}`}>
                  {(financialRatios?.gross_margin || grossMargin) >= 30 ? 'Good' : 'Low'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Transactions */}
        <div className="dashboard-card recent-transactions">
          <div className="card-header">
            <h3><i className="fas fa-exchange-alt"></i> Recent Journal Entries</h3>
            <button className="view-all-btn" onClick={() => navigate('/accounting/journal-entries')}>
              View All <i className="fas fa-chevron-right"></i>
            </button>
          </div>
          <div className="card-content">
            {recentEntries.length > 0 ? (
              <div className="transactions-list">
                {recentEntries.map((entry) => (
                  <div
                    key={entry.id}
                    className="transaction-item"
                    onClick={() => navigate(`/accounting/journal-entries/${entry.id}`)}
                  >
                    <div className="transaction-info">
                      <span className="transaction-number">{entry.entry_number}</span>
                      <span className="transaction-desc">{entry.description}</span>
                    </div>
                    <div className="transaction-meta">
                      <span className="transaction-date">{formatDate(entry.entry_date)}</span>
                      <span className="transaction-amount">{formatCurrency(entry.total_debits)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <i className="fas fa-exchange-alt"></i>
                <p>No recent journal entries</p>
              </div>
            )}
          </div>
        </div>

        {/* Cash Flow Summary */}
        <div className="dashboard-card cash-flow">
          <div className="card-header">
            <h3><i className="fas fa-water"></i> Cash Flow Summary</h3>
            <button className="view-all-btn" onClick={() => navigate('/accounting/reports/cash-flow')}>
              Full Report <i className="fas fa-chevron-right"></i>
            </button>
          </div>
          <div className="card-content">
            <div className="cash-flow-items">
              <div className="cf-item operating">
                <div className="cf-label">
                  <i className="fas fa-cogs"></i>
                  <span>Operating Activities</span>
                </div>
                <span className={`cf-value ${(cashFlow?.operating?.net || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {formatCurrency(cashFlow?.operating?.net || 0)}
                </span>
              </div>
              <div className="cf-item investing">
                <div className="cf-label">
                  <i className="fas fa-chart-line"></i>
                  <span>Investing Activities</span>
                </div>
                <span className={`cf-value ${(cashFlow?.investing?.net || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {formatCurrency(cashFlow?.investing?.net || 0)}
                </span>
              </div>
              <div className="cf-item financing">
                <div className="cf-label">
                  <i className="fas fa-hand-holding-usd"></i>
                  <span>Financing Activities</span>
                </div>
                <span className={`cf-value ${(cashFlow?.financing?.net || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {formatCurrency(cashFlow?.financing?.net || 0)}
                </span>
              </div>
              <div className="cf-item total">
                <div className="cf-label">
                  <i className="fas fa-sigma"></i>
                  <span>Net Change in Cash</span>
                </div>
                <span className={`cf-value ${(cashFlow?.net_change || 0) >= 0 ? 'positive' : 'negative'}`}>
                  {formatCurrency(cashFlow?.net_change || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Links */}
      <div className="nav-links">
        <div className="nav-section">
          <h4>Transactions</h4>
          <div className="nav-items">
            <button onClick={() => navigate('/accounting/journal-entries')}>
              <i className="fas fa-exchange-alt"></i> Journal Entries
            </button>
            <button onClick={() => navigate('/accounting/chart-of-accounts')}>
              <i className="fas fa-sitemap"></i> Chart of Accounts
            </button>
            <button onClick={() => navigate('/accounting/periods')}>
              <i className="fas fa-calendar-alt"></i> Accounting Periods
            </button>
          </div>
        </div>
        <div className="nav-section">
          <h4>Receivables</h4>
          <div className="nav-items">
            <button onClick={() => navigate('/accounting/ar/customers')}>
              <i className="fas fa-users"></i> Customers
            </button>
            <button onClick={() => navigate('/accounting/ar/invoices')}>
              <i className="fas fa-file-invoice-dollar"></i> Invoices
            </button>
            <button onClick={() => navigate('/accounting/ar/payments')}>
              <i className="fas fa-hand-holding-usd"></i> Payments
            </button>
          </div>
        </div>
        <div className="nav-section">
          <h4>Payables</h4>
          <div className="nav-items">
            <button onClick={() => navigate('/accounting/ap/vendors')}>
              <i className="fas fa-store"></i> Vendors
            </button>
            <button onClick={() => navigate('/accounting/ap/bills')}>
              <i className="fas fa-file-invoice"></i> Bills
            </button>
            <button onClick={() => navigate('/accounting/ap/payments')}>
              <i className="fas fa-money-check-alt"></i> Payments
            </button>
          </div>
        </div>
        <div className="nav-section">
          <h4>Reports</h4>
          <div className="nav-items">
            <button onClick={() => navigate('/accounting/reports/profit-loss')}>
              <i className="fas fa-chart-bar"></i> Profit & Loss
            </button>
            <button onClick={() => navigate('/accounting/reports/balance-sheet')}>
              <i className="fas fa-balance-scale"></i> Balance Sheet
            </button>
            <button onClick={() => navigate('/accounting/reports/cash-flow')}>
              <i className="fas fa-water"></i> Cash Flow
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AccountingDashboard;
