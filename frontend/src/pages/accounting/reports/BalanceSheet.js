import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import '../AccountingShared.css';

function BalanceSheet() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [reportData, setReportData] = useState(null);
  const [expandedSections, setExpandedSections] = useState(new Set(['assets', 'liabilities', 'equity']));

  // Report options
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().split('T')[0]);
  const [comparisonType, setComparisonType] = useState('none');
  const [accountingBasis, setAccountingBasis] = useState('accrual');

  // Fetch report data
  const fetchReportData = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        as_of_date: asOfDate,
        comparison: comparisonType,
        basis: accountingBasis,
      };

      const data = await accountingAPI.getBalanceSheetReport(params);
      setReportData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching Balance Sheet:', err);
      setLoading(false);
    }
  }, [asOfDate, comparisonType, accountingBasis]);

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

  // Format date for display
  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
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

  // Set quick date
  const setQuickDate = (type) => {
    const today = new Date();
    let date;

    switch (type) {
      case 'today':
        date = today;
        break;
      case 'month_end':
        date = new Date(today.getFullYear(), today.getMonth(), 0);
        break;
      case 'quarter_end':
        const quarter = Math.floor(today.getMonth() / 3);
        date = new Date(today.getFullYear(), quarter * 3, 0);
        break;
      case 'year_end':
        date = new Date(today.getFullYear() - 1, 11, 31);
        break;
      default:
        return;
    }

    setAsOfDate(date.toISOString().split('T')[0]);
  };

  // Export to CSV
  const handleExportCSV = () => {
    if (!reportData) return;

    const rows = [];
    rows.push(['Balance Sheet']);
    rows.push([`As of ${formatDate(asOfDate)}`]);
    rows.push([]);

    // Assets
    rows.push(['ASSETS']);
    reportData.assets?.categories?.forEach(cat => {
      rows.push([cat.name]);
      cat.accounts?.forEach(acc => {
        rows.push([`  ${acc.name}`, acc.balance]);
      });
      rows.push([`Total ${cat.name}`, cat.total]);
    });
    rows.push(['TOTAL ASSETS', reportData.assets?.total]);
    rows.push([]);

    // Liabilities
    rows.push(['LIABILITIES']);
    reportData.liabilities?.categories?.forEach(cat => {
      rows.push([cat.name]);
      cat.accounts?.forEach(acc => {
        rows.push([`  ${acc.name}`, acc.balance]);
      });
      rows.push([`Total ${cat.name}`, cat.total]);
    });
    rows.push(['TOTAL LIABILITIES', reportData.liabilities?.total]);
    rows.push([]);

    // Equity
    rows.push(['EQUITY']);
    reportData.equity?.accounts?.forEach(acc => {
      rows.push([`  ${acc.name}`, acc.balance]);
    });
    rows.push(['TOTAL EQUITY', reportData.equity?.total]);
    rows.push([]);

    rows.push(['TOTAL LIABILITIES & EQUITY', reportData.total_liabilities_equity]);

    const csvContent = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `balance-sheet-${asOfDate}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Render account row
  const renderAccountRow = (account, level = 0) => {
    const hasComparison = comparisonType !== 'none' && account.comparison !== undefined;

    return (
      <div key={account.id || account.name} className={`report-row level-${level}`}>
        <div className="row-label">{account.name}</div>
        <div className="row-amount">{formatCurrency(account.balance)}</div>
        {hasComparison && (
          <>
            <div className="row-amount comparison">{formatCurrency(account.comparison)}</div>
            <div className={`row-amount change ${account.change >= 0 ? 'positive' : 'negative'}`}>
              {formatPercentage(account.change)}
            </div>
          </>
        )}
      </div>
    );
  };

  // Render category section
  const renderCategory = (category, parentSection) => {
    const sectionKey = `${parentSection}_${category.name}`;
    const hasComparison = comparisonType !== 'none';

    return (
      <div key={category.name} className="report-category">
        <div
          className="category-header clickable"
          onClick={() => toggleSection(sectionKey)}
        >
          <i className={`fas fa-chevron-${expandedSections.has(sectionKey) ? 'down' : 'right'}`}></i>
          <span className="category-name">{category.name}</span>
          <span className="category-total">{formatCurrency(category.total)}</span>
        </div>

        {expandedSections.has(sectionKey) && (
          <div className="category-accounts">
            {category.accounts?.map(account => renderAccountRow(account, 2))}
          </div>
        )}

        <div className="category-subtotal">
          <div className="row-label">Total {category.name}</div>
          <div className="row-amount">{formatCurrency(category.total)}</div>
          {hasComparison && category.comparison !== undefined && (
            <>
              <div className="row-amount comparison">{formatCurrency(category.comparison)}</div>
              <div className={`row-amount change ${category.change >= 0 ? 'positive' : 'negative'}`}>
                {formatPercentage(category.change)}
              </div>
            </>
          )}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Balance Sheet...</p>
        </div>
      </div>
    );
  }

  const hasComparison = comparisonType !== 'none';
  const assets = reportData?.assets || { total: 0, categories: [] };
  const liabilities = reportData?.liabilities || { total: 0, categories: [] };
  const equity = reportData?.equity || { total: 0, accounts: [] };
  const totalLiabilitiesEquity = reportData?.total_liabilities_equity || 0;

  // Check if balanced
  const isBalanced = Math.abs(assets.total - totalLiabilitiesEquity) < 0.01;

  return (
    <div className="accounting-page financial-report balance-sheet">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-balance-scale"></i> Balance Sheet</h1>
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

          <div className="quick-ranges">
            <button onClick={() => setQuickDate('today')}>Today</button>
            <button onClick={() => setQuickDate('month_end')}>Last Month End</button>
            <button onClick={() => setQuickDate('quarter_end')}>Last Quarter End</button>
            <button onClick={() => setQuickDate('year_end')}>Last Year End</button>
          </div>
        </div>

        <div className="toolbar-right">
          <select
            value={comparisonType}
            onChange={(e) => setComparisonType(e.target.value)}
            className="filter-select"
          >
            <option value="none">No Comparison</option>
            <option value="previous_month">Previous Month</option>
            <option value="previous_quarter">Previous Quarter</option>
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
          <span className="label">Total Assets</span>
          <span className="value">{formatCurrency(assets.total)}</span>
        </div>
        <div className="report-summary-card">
          <span className="label">Total Liabilities</span>
          <span className="value">{formatCurrency(liabilities.total)}</span>
        </div>
        <div className="report-summary-card">
          <span className="label">Total Equity</span>
          <span className="value">{formatCurrency(equity.total)}</span>
        </div>
        <div className={`report-summary-card ${isBalanced ? 'success' : 'danger'}`}>
          <span className="label">Balance Check</span>
          <span className="value">
            {isBalanced ? (
              <><i className="fas fa-check-circle"></i> Balanced</>
            ) : (
              <><i className="fas fa-exclamation-triangle"></i> Out of Balance</>
            )}
          </span>
        </div>
      </div>

      {/* Report Content */}
      <div className="report-container">
        <div className="report-header-row">
          <div className="company-name">{reportData?.company_name || 'Company Name'}</div>
          <div className="report-title">Balance Sheet</div>
          <div className="report-period">As of {formatDate(asOfDate)}</div>
          <div className="report-basis">{accountingBasis === 'accrual' ? 'Accrual Basis' : 'Cash Basis'}</div>
        </div>

        {/* Column Headers */}
        <div className="report-columns-header">
          <div className="col-label">Account</div>
          <div className="col-amount">Balance</div>
          {hasComparison && (
            <>
              <div className="col-amount">Prior Period</div>
              <div className="col-amount">Change</div>
            </>
          )}
        </div>

        {/* Assets Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('assets')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('assets') ? 'down' : 'right'}`}></i>
            <span className="section-title">ASSETS</span>
            <span className="section-total">{formatCurrency(assets.total)}</span>
          </div>

          {expandedSections.has('assets') && (
            <div className="section-content">
              {assets.categories?.map(category => renderCategory(category, 'assets'))}
            </div>
          )}

          <div className="section-total-row">
            <div className="row-label">TOTAL ASSETS</div>
            <div className="row-amount">{formatCurrency(assets.total)}</div>
            {hasComparison && assets.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(assets.comparison)}</div>
                <div className={`row-amount change ${assets.change >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(assets.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Liabilities Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('liabilities')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('liabilities') ? 'down' : 'right'}`}></i>
            <span className="section-title">LIABILITIES</span>
            <span className="section-total">{formatCurrency(liabilities.total)}</span>
          </div>

          {expandedSections.has('liabilities') && (
            <div className="section-content">
              {liabilities.categories?.map(category => renderCategory(category, 'liabilities'))}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Total Liabilities</div>
            <div className="row-amount">{formatCurrency(liabilities.total)}</div>
            {hasComparison && liabilities.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(liabilities.comparison)}</div>
                <div className={`row-amount change ${liabilities.change <= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(liabilities.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Equity Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('equity')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('equity') ? 'down' : 'right'}`}></i>
            <span className="section-title">EQUITY</span>
            <span className="section-total">{formatCurrency(equity.total)}</span>
          </div>

          {expandedSections.has('equity') && (
            <div className="section-content">
              {equity.accounts?.map(account => renderAccountRow(account, 1))}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Total Equity</div>
            <div className="row-amount">{formatCurrency(equity.total)}</div>
            {hasComparison && equity.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(equity.comparison)}</div>
                <div className={`row-amount change ${equity.change >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(equity.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Total Liabilities & Equity */}
        <div className="section-total-row">
          <div className="row-label">TOTAL LIABILITIES & EQUITY</div>
          <div className="row-amount">{formatCurrency(totalLiabilitiesEquity)}</div>
          {hasComparison && reportData?.total_liabilities_equity_comparison !== undefined && (
            <>
              <div className="row-amount comparison">
                {formatCurrency(reportData.total_liabilities_equity_comparison)}
              </div>
              <div className={`row-amount change ${reportData.total_liabilities_equity_change >= 0 ? 'positive' : 'negative'}`}>
                {formatPercentage(reportData.total_liabilities_equity_change)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default BalanceSheet;
