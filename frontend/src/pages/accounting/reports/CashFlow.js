import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import '../AccountingShared.css';

function CashFlow() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [reportData, setReportData] = useState(null);
  const [expandedSections, setExpandedSections] = useState(new Set(['operating', 'investing', 'financing']));

  // Date range
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
    end: new Date().toISOString().split('T')[0],
  });
  const [reportMethod, setReportMethod] = useState('indirect'); // indirect, direct
  const [comparisonType, setComparisonType] = useState('none');

  // Fetch report data
  const fetchReportData = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        start_date: dateRange.start,
        end_date: dateRange.end,
        method: reportMethod,
        comparison: comparisonType,
      };

      const data = await accountingAPI.getCashFlowReport(params);
      setReportData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching Cash Flow report:', err);
      setLoading(false);
    }
  }, [dateRange, reportMethod, comparisonType]);

  useEffect(() => {
    fetchReportData();
  }, [fetchReportData]);

  // Format currency
  const formatCurrency = (amount) => {
    const value = parseFloat(amount) || 0;
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(Math.abs(value));
    return value < 0 ? `(${formatted})` : formatted;
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

  // Export to CSV
  const handleExportCSV = () => {
    if (!reportData) return;

    const rows = [];
    rows.push(['Cash Flow Statement']);
    rows.push([formatDateRange()]);
    rows.push([]);

    // Operating Activities
    rows.push(['CASH FLOWS FROM OPERATING ACTIVITIES']);
    if (reportMethod === 'indirect') {
      rows.push(['Net Income', reportData.operating?.net_income]);
      rows.push(['Adjustments to reconcile net income:']);
      reportData.operating?.adjustments?.forEach(adj => {
        rows.push([`  ${adj.name}`, adj.amount]);
      });
      rows.push(['Changes in operating assets and liabilities:']);
      reportData.operating?.changes?.forEach(chg => {
        rows.push([`  ${chg.name}`, chg.amount]);
      });
    } else {
      reportData.operating?.items?.forEach(item => {
        rows.push([`  ${item.name}`, item.amount]);
      });
    }
    rows.push(['Net Cash from Operating Activities', reportData.operating?.total]);
    rows.push([]);

    // Investing Activities
    rows.push(['CASH FLOWS FROM INVESTING ACTIVITIES']);
    reportData.investing?.items?.forEach(item => {
      rows.push([`  ${item.name}`, item.amount]);
    });
    rows.push(['Net Cash from Investing Activities', reportData.investing?.total]);
    rows.push([]);

    // Financing Activities
    rows.push(['CASH FLOWS FROM FINANCING ACTIVITIES']);
    reportData.financing?.items?.forEach(item => {
      rows.push([`  ${item.name}`, item.amount]);
    });
    rows.push(['Net Cash from Financing Activities', reportData.financing?.total]);
    rows.push([]);

    rows.push(['NET INCREASE (DECREASE) IN CASH', reportData.net_change]);
    rows.push(['Cash at Beginning of Period', reportData.beginning_cash]);
    rows.push(['Cash at End of Period', reportData.ending_cash]);

    const csvContent = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cash-flow-${dateRange.start}-to-${dateRange.end}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Render line item
  const renderLineItem = (item, level = 1) => {
    const hasComparison = comparisonType !== 'none' && item.comparison !== undefined;

    return (
      <div key={item.name} className={`report-row level-${level}`}>
        <div className="row-label">{item.name}</div>
        <div className={`row-amount ${item.amount < 0 ? 'negative' : ''}`}>
          {formatCurrency(item.amount)}
        </div>
        {hasComparison && (
          <>
            <div className="row-amount comparison">{formatCurrency(item.comparison)}</div>
            <div className={`row-amount change ${item.change >= 0 ? 'positive' : 'negative'}`}>
              {formatPercentage(item.change)}
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
          <p>Loading Cash Flow Statement...</p>
        </div>
      </div>
    );
  }

  const hasComparison = comparisonType !== 'none';
  const operating = reportData?.operating || { total: 0 };
  const investing = reportData?.investing || { total: 0 };
  const financing = reportData?.financing || { total: 0 };
  const netChange = reportData?.net_change || 0;
  const beginningCash = reportData?.beginning_cash || 0;
  const endingCash = reportData?.ending_cash || 0;

  return (
    <div className="accounting-page financial-report cash-flow">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-money-bill-wave"></i> Cash Flow Statement</h1>
            <p className="subtitle">{formatDateRange()}</p>
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
            <button onClick={() => setQuickRange('this_quarter')}>This Quarter</button>
            <button onClick={() => setQuickRange('this_year')}>This Year</button>
          </div>
        </div>

        <div className="toolbar-right">
          <select
            value={reportMethod}
            onChange={(e) => setReportMethod(e.target.value)}
            className="filter-select"
          >
            <option value="indirect">Indirect Method</option>
            <option value="direct">Direct Method</option>
          </select>

          <select
            value={comparisonType}
            onChange={(e) => setComparisonType(e.target.value)}
            className="filter-select"
          >
            <option value="none">No Comparison</option>
            <option value="previous_period">Previous Period</option>
            <option value="previous_year">Previous Year</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="report-summary-cards">
        <div className={`report-summary-card ${operating.total >= 0 ? 'success' : 'warning'}`}>
          <span className="label">Operating Activities</span>
          <span className="value">{formatCurrency(operating.total)}</span>
        </div>
        <div className={`report-summary-card ${investing.total >= 0 ? 'info' : ''}`}>
          <span className="label">Investing Activities</span>
          <span className="value">{formatCurrency(investing.total)}</span>
        </div>
        <div className={`report-summary-card ${financing.total >= 0 ? 'info' : ''}`}>
          <span className="label">Financing Activities</span>
          <span className="value">{formatCurrency(financing.total)}</span>
        </div>
        <div className={`report-summary-card ${netChange >= 0 ? 'success' : 'danger'}`}>
          <span className="label">Net Cash Change</span>
          <span className="value">{formatCurrency(netChange)}</span>
        </div>
      </div>

      {/* Report Content */}
      <div className="report-container">
        <div className="report-header-row">
          <div className="company-name">{reportData?.company_name || 'Company Name'}</div>
          <div className="report-title">Statement of Cash Flows</div>
          <div className="report-period">{formatDateRange()}</div>
          <div className="report-method">{reportMethod === 'indirect' ? 'Indirect Method' : 'Direct Method'}</div>
        </div>

        {/* Column Headers */}
        <div className="report-columns-header">
          <div className="col-label">Description</div>
          <div className="col-amount">Amount</div>
          {hasComparison && (
            <>
              <div className="col-amount">Prior Period</div>
              <div className="col-amount">Change</div>
            </>
          )}
        </div>

        {/* Operating Activities Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('operating')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('operating') ? 'down' : 'right'}`}></i>
            <span className="section-title">Cash Flows from Operating Activities</span>
            <span className={`section-total ${operating.total >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(operating.total)}
            </span>
          </div>

          {expandedSections.has('operating') && (
            <div className="section-content">
              {reportMethod === 'indirect' ? (
                <>
                  {/* Net Income */}
                  <div className="report-row level-1 highlight">
                    <div className="row-label">Net Income</div>
                    <div className="row-amount">{formatCurrency(operating.net_income)}</div>
                  </div>

                  {/* Adjustments */}
                  {operating.adjustments?.length > 0 && (
                    <>
                      <div className="subsection-header">
                        Adjustments to reconcile net income to net cash:
                      </div>
                      {operating.adjustments?.map(item => renderLineItem(item, 2))}
                    </>
                  )}

                  {/* Changes in Working Capital */}
                  {operating.changes?.length > 0 && (
                    <>
                      <div className="subsection-header">
                        Changes in operating assets and liabilities:
                      </div>
                      {operating.changes?.map(item => renderLineItem(item, 2))}
                    </>
                  )}
                </>
              ) : (
                <>
                  {/* Direct Method Items */}
                  {operating.items?.map(item => renderLineItem(item, 1))}
                </>
              )}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Net Cash Provided by Operating Activities</div>
            <div className={`row-amount ${operating.total >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(operating.total)}
            </div>
            {hasComparison && operating.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(operating.comparison)}</div>
                <div className={`row-amount change ${operating.change >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(operating.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Investing Activities Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('investing')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('investing') ? 'down' : 'right'}`}></i>
            <span className="section-title">Cash Flows from Investing Activities</span>
            <span className={`section-total ${investing.total >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(investing.total)}
            </span>
          </div>

          {expandedSections.has('investing') && (
            <div className="section-content">
              {investing.items?.length > 0 ? (
                investing.items.map(item => renderLineItem(item, 1))
              ) : (
                <div className="report-row level-1 empty">
                  <div className="row-label">No investing activities</div>
                  <div className="row-amount">-</div>
                </div>
              )}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Net Cash Used in Investing Activities</div>
            <div className={`row-amount ${investing.total >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(investing.total)}
            </div>
            {hasComparison && investing.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(investing.comparison)}</div>
                <div className={`row-amount change ${investing.change >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(investing.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Financing Activities Section */}
        <div className="report-section">
          <div
            className="section-header clickable"
            onClick={() => toggleSection('financing')}
          >
            <i className={`fas fa-chevron-${expandedSections.has('financing') ? 'down' : 'right'}`}></i>
            <span className="section-title">Cash Flows from Financing Activities</span>
            <span className={`section-total ${financing.total >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(financing.total)}
            </span>
          </div>

          {expandedSections.has('financing') && (
            <div className="section-content">
              {financing.items?.length > 0 ? (
                financing.items.map(item => renderLineItem(item, 1))
              ) : (
                <div className="report-row level-1 empty">
                  <div className="row-label">No financing activities</div>
                  <div className="row-amount">-</div>
                </div>
              )}
            </div>
          )}

          <div className="section-subtotal">
            <div className="row-label">Net Cash from Financing Activities</div>
            <div className={`row-amount ${financing.total >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(financing.total)}
            </div>
            {hasComparison && financing.comparison !== undefined && (
              <>
                <div className="row-amount comparison">{formatCurrency(financing.comparison)}</div>
                <div className={`row-amount change ${financing.change >= 0 ? 'positive' : 'negative'}`}>
                  {formatPercentage(financing.change)}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Summary Section */}
        <div className="report-summary-section">
          <div className="summary-row highlight">
            <div className="row-label">Net Increase (Decrease) in Cash</div>
            <div className={`row-amount ${netChange >= 0 ? 'positive' : 'negative'}`}>
              {formatCurrency(netChange)}
            </div>
          </div>

          <div className="summary-row">
            <div className="row-label">Cash at Beginning of Period</div>
            <div className="row-amount">{formatCurrency(beginningCash)}</div>
          </div>

          <div className="summary-row total">
            <div className="row-label">Cash at End of Period</div>
            <div className="row-amount">{formatCurrency(endingCash)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CashFlow;
