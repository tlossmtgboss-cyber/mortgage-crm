import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import '../AccountingShared.css';

function ProfitLoss() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [reportData, setReportData] = useState(null);
  const [expandedSections, setExpandedSections] = useState(new Set(['revenue', 'expenses']));

  // Date range
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0], // Jan 1
    end: new Date().toISOString().split('T')[0], // Today
  });
  const [comparisonType, setComparisonType] = useState('none'); // none, previous_period, previous_year
  const [accountingBasis, setAccountingBasis] = useState('accrual'); // accrual, cash

  // Fetch report data
  const fetchReportData = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        start_date: dateRange.start,
        end_date: dateRange.end,
        comparison: comparisonType,
        basis: accountingBasis,
      };

      const data = await accountingAPI.getProfitLossReport(params);
      setReportData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching P&L report:', err);
      setLoading(false);
    }
  }, [dateRange, comparisonType, accountingBasis]);

  useEffect(() => {
    fetchReportData();
  }, [fetchReportData]);

  // Format currency
  const formatCurrency = (amount) => {
    const value = parseFloat(amount) || 0;
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(Math.abs(value));
  };

  // Format percentage
  const formatPercentage = (value) => {
    if (value === null || value === undefined) return '-';
    return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
  };

  // Format date range for display
  const formatDateRange = () => {
    const start = new Date(dateRange.start);
    const end = new Date(dateRange.end);
    return `${start.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} - ${end.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
  };

  // Toggle section expansion
  const toggleSection = (section) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev);
      if (newSet.has(section)) {
        newSet.delete(section);
      } else {
        newSet.add(section);
      }
      return newSet;
    });
  };

  // Set quick date range
  const setQuickRange = (range) => {
    const today = new Date();
    let start, end;

    switch (range) {
      case 'this_month':
        start = new Date(today.getFullYear(), today.getMonth(), 1);
        end = today;
        break;
      case 'last_month':
        start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        end = new Date(today.getFullYear(), today.getMonth(), 0);
        break;
      case 'this_quarter':
        const quarter = Math.floor(today.getMonth() / 3);
        start = new Date(today.getFullYear(), quarter * 3, 1);
        end = today;
        break;
      case 'last_quarter':
        const lastQuarter = Math.floor(today.getMonth() / 3) - 1;
        const year = lastQuarter < 0 ? today.getFullYear() - 1 : today.getFullYear();
        const q = lastQuarter < 0 ? 3 : lastQuarter;
        start = new Date(year, q * 3, 1);
        end = new Date(year, q * 3 + 3, 0);
        break;
      case 'this_year':
        start = new Date(today.getFullYear(), 0, 1);
        end = today;
        break;
      case 'last_year':
        start = new Date(today.getFullYear() - 1, 0, 1);
        end = new Date(today.getFullYear() - 1, 11, 31);
        break;
      default:
        return;
    }

    setDateRange({
      start: start.toISOString().split('T')[0],
      end: end.toISOString().split('T')[0],
    });
  };

  // Export to PDF
  const handleExportPDF = () => {
    window.print();
  };

  // Export to CSV
  const handleExportCSV = () => {
    if (!reportData) return;

    const rows = [];
    rows.push(['Profit & Loss Statement']);
    rows.push([formatDateRange()]);
    rows.push([]);

    // Revenue section
    rows.push(['REVENUE']);
    reportData.revenue?.accounts?.forEach(acc => {
      rows.push([`  ${acc.name}`, acc.amount]);
    });
    rows.push(['Total Revenue', reportData.revenue?.total]);
    rows.push([]);

    // Expenses section
    rows.push(['EXPENSES']);
    reportData.expenses?.categories?.forEach(cat => {
      rows.push([cat.name]);
      cat.accounts?.forEach(acc => {
        rows.push([`  ${acc.name}`, acc.amount]);
      });
      rows.push([`Total ${cat.name}`, cat.total]);
    });
    rows.push(['Total Expenses', reportData.expenses?.total]);
    rows.push([]);

    // Net Income
    rows.push(['NET INCOME', reportData.net_income]);

    const csvContent = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `profit-loss-${dateRange.start}-to-${dateRange.end}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Render account row
  const renderAccountRow = (account, level = 0) => {
    const hasComparison = comparisonType !== 'none' && account.comparison !== undefined;

    return (
      <div key={account.id || account.name} className={`report-row level-${level}`}>
        <div className="row-label">{account.name}</div>
        <div className={`row-amount ${account.amount < 0 ? 'negative' : ''}`}>
          {formatCurrency(account.amount)}
        </div>
        {hasComparison && (
          <>
            <div className="row-amount comparison">
              {formatCurrency(account.comparison)}
            </div>
            <div className={`row-amount change ${account.change >= 0 ? 'positive' : 'negative'}`}>
              {formatPercentage(account.change)}
            </div>
          </>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Profit & Loss Report...</p>
        </div>
      </div>
    );
  }

  const hasComparison = comparisonType !== 'none';
  const revenue = reportData?.revenue || { total: 0, accounts: [] };
  const expenses = reportData?.expenses || { total: 0, categories: [] };
  const grossProfit = reportData?.gross_profit || 0;
  const netIncome = reportData?.net_income || 0;

  return (
    <div className="accounting-page financial-report profit-loss">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-chart-line"></i> Profit & Loss</h1>
            <p className="subtitle">{formatDateRange()}</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={handleExportCSV}>
            <i className="fas fa-file-csv"></i> Export CSV
          </button>
          <button className="btn-secondary" onClick={handleExportPDF}>
            <i className="fas fa-file-pdf"></i> Print / PDF
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar report-toolbar">
        <div className="toolbar-left">
          <div className="date-range-picker">
            <input
              type="date"
              value={dateRange.start}
              onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
            />
            <span>to</span>
            <input
              type="date"
              value={dateRange.end}
              onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
            />
          </div>

          <div className="quick-ranges">
            <button onClick={() => setQuickRange('this_month')}>This Month</button>
            <button onClick={() => setQuickRange('last_month')}>Last Month</button>
            <button onClick={() => setQuickRange('this_quarter')}>This Quarter</button>
            <button onClick={() => setQuickRange('this_year')}>This Year</button>
          </div>
        </div>

        <div className="toolbar-right">
          <select
            value={comparisonType}
            onChange={(e) => setComparisonType(e.target.value)}
            className="filter-select"
          >
            <option value="none">No Comparison</option>
            <option value="previous_period">Previous Period</option>
            <option value="previous_year">Previous Year</option>
          </select>

          <select
            value={accountingBasis}
            onChange={(e) => setAccountingBasis(e.target.value)}
            className="filter-select"
          >
            <option value="accrual">Accrual Basis</option>
            <option value="cash">Cash Basis</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="report-summary-cards">
        <div className="report-summary-card">
          <span className="label">Total Revenue</span>
          <span className="value positive">{formatCurrency(revenue.total)}</span>
        </div>
        <div className="report-summary-card">
          <span className="label">Total Expenses</span>
          <span className="value negative">{formatCurrency(expenses.total)}</span>
        </div>
        <div className={`report-summary-card ${netIncome >= 0 ? 'success' : 'danger'}`}>
          <span className="label">Net Income</span>
          <span className="value">{formatCurrency(netIncome)}</span>
        </div>
        {revenue.total > 0 && (
          <div className="report-summary-card">
            <span className="label">Profit Margin</span>
            <span className="value">{((netIncome / revenue.total) * 100).toFixed(1)}%</span>
          </div>
        )}
      </div>

      {/* Report Content */}
      <div className="report-container">
        <div className="report-header-row">
          <div className="company-name">{reportData?.company_name || 'Company Name'}</div>
          <div className="report-title">Profit & Loss Statement</div>
          <div className="report-period">{formatDateRange()}</div>
          <div className="report-basis">{accountingBasis === 'accrual' ? 'Accrual Basis' : 'Cash Basis'}</div>
        </div>

        {/* Column Headers */}
        <div className="report-columns-header">
          <div className="col-label">Account</div>
          <div className="col-amount">Amount</div>
          {hasComparison && (
            <>
              <div className="col-amount">Prior Period</div>
              <div className="col-amount">Change</div>
            </>
          )}
        </div>

        {/* Revenue Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('revenue')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('revenue') ? 'down' : 'right'}`}></i>
            <span className="section-title">Revenue</span>
            <span className="section-total">{formatCurrency(revenue.total)}</span>
          </div>

          {expandedSections.has('revenue') && (
            <div className="section-content">
              {revenue.accounts?.map(account => renderAccountRow(account, 1))}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Total Revenue</div>
            <div className="row-amount">{formatCurrency(revenue.total)}</div>
            {hasComparison && revenue.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(revenue.comparison)}</div>
                <div className={`row-amount change ${revenue.change >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(revenue.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Cost of Goods Sold Section (if applicable) */}
        {reportData?.cogs && reportData.cogs.total > 0 && (
          <>
            <div className="report-section">
              <div
                className="section-header clickable"
                onClick={() => toggleSection('cogs')}
              >
                <i className={`fas fa-chevron-${expandedSections.has('cogs') ? 'down' : 'right'}`}></i>
                <span className="section-title">Cost of Goods Sold</span>
                <span className="section-total">{formatCurrency(reportData.cogs.total)}</span>
              </div>

              {expandedSections.has('cogs') && (
                <div className="section-content">
                  {reportData.cogs.accounts?.map(account => renderAccountRow(account, 1))}
                </div>
              )}

              <div className="section-subtotal">
                <div className="row-label">Total COGS</div>
                <div className="row-amount">{formatCurrency(reportData.cogs.total)}</div>
              </div>
            </div>

            <div className="report-gross-profit">
              <div className="row-label">Gross Profit</div>
              <div className={`row-amount ${grossProfit >= 0 ? 'positive' : 'negative'}`}>
                {formatCurrency(grossProfit)}
              </div>
            </div>
          </>
        )}

        {/* Expenses Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('expenses')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('expenses') ? 'down' : 'right'}`}></i>
            <span className="section-title">Expenses</span>
            <span className="section-total">{formatCurrency(expenses.total)}</span>
          </div>

          {expandedSections.has('expenses') && (
            <div className="section-content">
              {expenses.categories?.map(category => (
                <div key={category.name} className="expense-category">
                  <div
                    className="category-header clickable"
                    onClick={() => toggleSection(`exp_${category.name}`)}
                  >
                    <i className={`fas fa-chevron-${expandedSections.has(`exp_${category.name}`) ? 'down' : 'right'}`}></i>
                    <span className="category-name">{category.name}</span>
                    <span className="category-total">{formatCurrency(category.total)}</span>
                  </div>

                  {expandedSections.has(`exp_${category.name}`) && (
                    <div className="category-accounts">
                      {category.accounts?.map(account => renderAccountRow(account, 2))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Total Expenses</div>
            <div className="row-amount">{formatCurrency(expenses.total)}</div>
            {hasComparison && expenses.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(expenses.comparison)}</div>
                <div className={`row-amount change ${expenses.change <= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(expenses.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Net Income */}
        <div className="report-net-income">
          <div className="row-label">Net Income</div>
          <div className={`row-amount ${netIncome >= 0 ? 'positive' : 'negative'}`}>
            {formatCurrency(netIncome)}
          </div>
          {hasComparison && reportData?.net_income_comparison !== undefined && (
            <>
              <div className="row-amount comparison">
                {formatCurrency(reportData.net_income_comparison)}
              </div>
              <div className={`row-amount change ${reportData.net_income_change >= 0 ? 'positive' : 'negative'}`}>
                {formatPercentage(reportData.net_income_change)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default ProfitLoss;
