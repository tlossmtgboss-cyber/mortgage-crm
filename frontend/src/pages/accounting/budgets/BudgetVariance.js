import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';

function BudgetVariance() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [budgets, setBudgets] = useState([]);
  const [varianceData, setVarianceData] = useState(null);
  const [expandedSections, setExpandedSections] = useState(new Set(['revenue', 'expenses']));

  // Filters
  const [selectedBudget, setSelectedBudget] = useState(searchParams.get('budget') || '');
  const [periodType, setPeriodType] = useState('ytd'); // ytd, monthly, quarterly
  const [selectedPeriod, setSelectedPeriod] = useState(new Date().getMonth()); // 0-11 for monthly
  const [showPercentages, setShowPercentages] = useState(true);

  // Month names
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const quarters = ['Q1 (Jan-Mar)', 'Q2 (Apr-Jun)', 'Q3 (Jul-Sep)', 'Q4 (Oct-Dec)'];

  // Fetch budgets for dropdown
  const fetchBudgets = useCallback(async () => {
    try {
      const data = await accountingAPI.getBudgets({ status: 'approved' });
      setBudgets(data?.budgets || []);

      // Auto-select first budget if none selected
      if (!selectedBudget && data?.budgets?.length > 0) {
        setSelectedBudget(data.budgets[0].id);
      }
    } catch (err) {
      console.error('Error fetching budgets:', err);
    }
  }, [selectedBudget]);

  // Fetch variance data
  const fetchVarianceData = useCallback(async () => {
    if (!selectedBudget) return;

    try {
      setLoading(true);
      const params = {
        budget_id: selectedBudget,
        period_type: periodType,
      };

      if (periodType === 'monthly') {
        params.month = selectedPeriod;
      } else if (periodType === 'quarterly') {
        params.quarter = selectedPeriod;
      }

      const data = await accountingAPI.getBudgetVariance(params);
      setVarianceData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching variance data:', err);
      setLoading(false);
    }
  }, [selectedBudget, periodType, selectedPeriod]);

  useEffect(() => {
    fetchBudgets();
  }, [fetchBudgets]);

  useEffect(() => {
    fetchVarianceData();
  }, [fetchVarianceData]);

  // Format currency
  const formatCurrency = (amount) => {
    const value = parseFloat(amount) || 0;
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(Math.abs(value));
    return value < 0 ? `(${formatted})` : formatted;
  };

  // Format percentage
  const formatPercentage = (value) => {
    if (value === null || value === undefined || !isFinite(value)) return '-';
    return `${value >= 0 ? '' : ''}${value.toFixed(1)}%`;
  };

  // Calculate variance percentage
  const calcVariancePercent = (actual, budget) => {
    if (!budget || budget === 0) return null;
    return ((actual - budget) / Math.abs(budget)) * 100;
  };

  // Determine variance status (favorable/unfavorable)
  const getVarianceStatus = (variance, accountType) => {
    if (variance === 0) return 'neutral';
    // For revenue: positive variance is favorable
    // For expenses: negative variance is favorable
    if (accountType === 'revenue') {
      return variance > 0 ? 'favorable' : 'unfavorable';
    } else {
      return variance < 0 ? 'favorable' : 'unfavorable';
    }
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

  // Export to CSV
  const handleExportCSV = () => {
    if (!varianceData) return;

    const rows = [];
    rows.push(['Budget Variance Report']);
    rows.push([varianceData.budget_name]);
    rows.push([`Period: ${varianceData.period_label}`]);
    rows.push([]);
    rows.push(['Account', 'Budget', 'Actual', 'Variance $', 'Variance %', 'Status']);

    // Revenue
    rows.push(['REVENUE']);
    varianceData.revenue?.items?.forEach(item => {
      rows.push([
        item.account_name,
        item.budget,
        item.actual,
        item.variance,
        item.variance_percent ? `${item.variance_percent.toFixed(1)}%` : '-',
        item.status,
      ]);
    });
    rows.push(['Total Revenue', varianceData.revenue?.budget, varianceData.revenue?.actual, varianceData.revenue?.variance]);
    rows.push([]);

    // Expenses
    rows.push(['EXPENSES']);
    varianceData.expenses?.items?.forEach(item => {
      rows.push([
        item.account_name,
        item.budget,
        item.actual,
        item.variance,
        item.variance_percent ? `${item.variance_percent.toFixed(1)}%` : '-',
        item.status,
      ]);
    });
    rows.push(['Total Expenses', varianceData.expenses?.budget, varianceData.expenses?.actual, varianceData.expenses?.variance]);
    rows.push([]);

    rows.push(['NET', varianceData.net?.budget, varianceData.net?.actual, varianceData.net?.variance]);

    const csvContent = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `budget-variance-${varianceData.budget_name}-${varianceData.period_label}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Render variance row
  const renderVarianceRow = (item, level = 1) => {
    const variancePercent = calcVariancePercent(item.actual, item.budget);
    const status = getVarianceStatus(item.variance, item.account_type);

    return (
      <div key={item.account_id || item.account_name} className={`variance-row level-${level}`}>
        <div className="cell account">{item.account_name}</div>
        <div className="cell amount">{formatCurrency(item.budget)}</div>
        <div className="cell amount">{formatCurrency(item.actual)}</div>
        <div className={`cell amount variance ${status}`}>
          {formatCurrency(item.variance)}
        </div>
        {showPercentages && (
          <div className={`cell amount variance-pct ${status}`}>
            {formatPercentage(variancePercent)}
          </div>
        )}
        <div className="cell status">
          <span className={`status-indicator ${status}`}>
            {status === 'favorable' && <i className="fas fa-check-circle"></i>}
            {status === 'unfavorable' && <i className="fas fa-exclamation-circle"></i>}
            {status === 'neutral' && <i className="fas fa-minus-circle"></i>}
          </span>
        </div>
      </div>
    );
  };

  if (loading && selectedBudget) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Variance Report...</p>
        </div>
      </div>
    );
  }

  const revenue = varianceData?.revenue || { budget: 0, actual: 0, variance: 0, items: [] };
  const expenses = varianceData?.expenses || { budget: 0, actual: 0, variance: 0, items: [] };
  const net = varianceData?.net || { budget: 0, actual: 0, variance: 0 };

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page budget-variance">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Budget Variance.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page budget-variance">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting/budgets')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-chart-bar"></i> Budget vs Actual</h1>
            <p className="subtitle">
              {varianceData?.period_label || 'Select a budget to view variance'}
            </p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={handleExportCSV} disabled={!varianceData}>
            <i className="fas fa-download"></i> Export CSV
          </button>
          <button className="btn-secondary" onClick={() => window.print()} disabled={!varianceData}>
            <i className="fas fa-print"></i> Print
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar report-toolbar">
        <div className="toolbar-left">
          <select
            value={selectedBudget}
            onChange={(e) => setSelectedBudget(e.target.value)}
            className="filter-select"
          >
            <option value="">Select Budget</option>
            {budgets.map(budget => (
              <option key={budget.id} value={budget.id}>
                {budget.name} (FY {budget.fiscal_year})
              </option>
            ))}
          </select>

          <select
            value={periodType}
            onChange={(e) => {
              setPeriodType(e.target.value);
              setSelectedPeriod(e.target.value === 'quarterly' ? 0 : new Date().getMonth());
            }}
            className="filter-select"
          >
            <option value="ytd">Year to Date</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
          </select>

          {periodType === 'monthly' && (
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(parseInt(e.target.value))}
              className="filter-select"
            >
              {months.map((month, i) => (
                <option key={i} value={i}>{month}</option>
              ))}
            </select>
          )}

          {periodType === 'quarterly' && (
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(parseInt(e.target.value))}
              className="filter-select"
            >
              {quarters.map((quarter, i) => (
                <option key={i} value={i}>{quarter}</option>
              ))}
            </select>
          )}
        </div>

        <div className="toolbar-right">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showPercentages}
              onChange={(e) => setShowPercentages(e.target.checked)}
            />
            Show Percentages
          </label>
        </div>
      </div>

      {selectedBudget && varianceData ? (
        <>
          {/* Summary Cards */}
          <div className="variance-summary-cards">
            <div className="variance-card">
              <div className="card-header">
                <span className="label">Revenue</span>
              </div>
              <div className="card-content">
                <div className="metric">
                  <span className="metric-label">Budget</span>
                  <span className="metric-value">{formatCurrency(revenue.budget)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Actual</span>
                  <span className="metric-value">{formatCurrency(revenue.actual)}</span>
                </div>
                <div className={`metric variance ${getVarianceStatus(revenue.variance, 'revenue')}`}>
                  <span className="metric-label">Variance</span>
                  <span className="metric-value">{formatCurrency(revenue.variance)}</span>
                </div>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${Math.min((revenue.actual / revenue.budget) * 100, 100)}%` }}
                ></div>
              </div>
              <span className="progress-label">
                {revenue.budget > 0 ? ((revenue.actual / revenue.budget) * 100).toFixed(1) : 0}% of budget
              </span>
            </div>

            <div className="variance-card">
              <div className="card-header">
                <span className="label">Expenses</span>
              </div>
              <div className="card-content">
                <div className="metric">
                  <span className="metric-label">Budget</span>
                  <span className="metric-value">{formatCurrency(expenses.budget)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Actual</span>
                  <span className="metric-value">{formatCurrency(expenses.actual)}</span>
                </div>
                <div className={`metric variance ${getVarianceStatus(expenses.variance, 'expense')}`}>
                  <span className="metric-label">Variance</span>
                  <span className="metric-value">{formatCurrency(expenses.variance)}</span>
                </div>
              </div>
              <div className="progress-bar expense">
                <div
                  className="progress-fill"
                  style={{ width: `${Math.min((expenses.actual / expenses.budget) * 100, 100)}%` }}
                ></div>
              </div>
              <span className="progress-label">
                {expenses.budget > 0 ? ((expenses.actual / expenses.budget) * 100).toFixed(1) : 0}% of budget
              </span>
            </div>

            <div className={`variance-card highlight ${getVarianceStatus(net.variance, 'revenue')}`}>
              <div className="card-header">
                <span className="label">Net Income</span>
              </div>
              <div className="card-content">
                <div className="metric">
                  <span className="metric-label">Budget</span>
                  <span className="metric-value">{formatCurrency(net.budget)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Actual</span>
                  <span className="metric-value">{formatCurrency(net.actual)}</span>
                </div>
                <div className="metric variance">
                  <span className="metric-label">Variance</span>
                  <span className="metric-value">{formatCurrency(net.variance)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Detailed Variance Table */}
          <div className="variance-report">
            <div className="report-header-row">
              <div className="company-name">{varianceData?.company_name || 'Company Name'}</div>
              <div className="report-title">Budget vs Actual Variance Report</div>
              <div className="report-period">{varianceData?.period_label}</div>
            </div>

            {/* Column Headers */}
            <div className="variance-columns-header">
              <div className="col account">Account</div>
              <div className="col amount">Budget</div>
              <div className="col amount">Actual</div>
              <div className="col amount">Variance $</div>
              {showPercentages && <div className="col amount">Variance %</div>}
              <div className="col status">Status</div>
            </div>

            {/* Revenue Section */}
            <div className="variance-section">
              <div
                className="section-header clickable"
                onClick={() => toggleSection('revenue')}
              >
                <i className={`fas fa-chevron-${expandedSections.has('revenue') ? 'down' : 'right'}`}></i>
                <span className="section-title">Revenue</span>
              </div>

              {expandedSections.has('revenue') && (
                <div className="section-content">
                  {revenue.items?.map(item => renderVarianceRow({ ...item, account_type: 'revenue' }))}
                </div>
              )}

              <div className="section-total">
                <div className="cell account">Total Revenue</div>
                <div className="cell amount">{formatCurrency(revenue.budget)}</div>
                <div className="cell amount">{formatCurrency(revenue.actual)}</div>
                <div className={`cell amount variance ${getVarianceStatus(revenue.variance, 'revenue')}`}>
                  {formatCurrency(revenue.variance)}
                </div>
                {showPercentages && (
                  <div className={`cell amount variance-pct ${getVarianceStatus(revenue.variance, 'revenue')}`}>
                    {formatPercentage(calcVariancePercent(revenue.actual, revenue.budget))}
                  </div>
                )}
                <div className="cell status"></div>
              </div>
            </div>

            {/* Expenses Section */}
            <div className="variance-section">
              <div
                className="section-header clickable"
                onClick={() => toggleSection('expenses')}
              >
                <i className={`fas fa-chevron-${expandedSections.has('expenses') ? 'down' : 'right'}`}></i>
                <span className="section-title">Expenses</span>
              </div>

              {expandedSections.has('expenses') && (
                <div className="section-content">
                  {expenses.items?.map(item => renderVarianceRow({ ...item, account_type: 'expense' }))}
                </div>
              )}

              <div className="section-total">
                <div className="cell account">Total Expenses</div>
                <div className="cell amount">{formatCurrency(expenses.budget)}</div>
                <div className="cell amount">{formatCurrency(expenses.actual)}</div>
                <div className={`cell amount variance ${getVarianceStatus(expenses.variance, 'expense')}`}>
                  {formatCurrency(expenses.variance)}
                </div>
                {showPercentages && (
                  <div className={`cell amount variance-pct ${getVarianceStatus(expenses.variance, 'expense')}`}>
                    {formatPercentage(calcVariancePercent(expenses.actual, expenses.budget))}
                  </div>
                )}
                <div className="cell status"></div>
              </div>
            </div>

            {/* Net Income Row */}
            <div className="net-income-row">
              <div className="cell account"><strong>Net Income</strong></div>
              <div className="cell amount"><strong>{formatCurrency(net.budget)}</strong></div>
              <div className="cell amount"><strong>{formatCurrency(net.actual)}</strong></div>
              <div className={`cell amount variance ${getVarianceStatus(net.variance, 'revenue')}`}>
                <strong>{formatCurrency(net.variance)}</strong>
              </div>
              {showPercentages && (
                <div className={`cell amount variance-pct ${getVarianceStatus(net.variance, 'revenue')}`}>
                  <strong>{formatPercentage(calcVariancePercent(net.actual, net.budget))}</strong>
                </div>
              )}
              <div className="cell status">
                <span className={`status-indicator ${getVarianceStatus(net.variance, 'revenue')}`}>
                  {getVarianceStatus(net.variance, 'revenue') === 'favorable' && <i className="fas fa-check-circle"></i>}
                  {getVarianceStatus(net.variance, 'revenue') === 'unfavorable' && <i className="fas fa-exclamation-circle"></i>}
                </span>
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="variance-legend">
            <div className="legend-item">
              <span className="status-indicator favorable"><i className="fas fa-check-circle"></i></span>
              <span>Favorable Variance</span>
            </div>
            <div className="legend-item">
              <span className="status-indicator unfavorable"><i className="fas fa-exclamation-circle"></i></span>
              <span>Unfavorable Variance</span>
            </div>
            <div className="legend-item">
              <span className="status-indicator neutral"><i className="fas fa-minus-circle"></i></span>
              <span>On Budget</span>
            </div>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <i className="fas fa-chart-bar"></i>
          <h3>Select a Budget</h3>
          <p>Choose an approved budget from the dropdown to view the variance report.</p>
          {budgets.length === 0 && (
            <button className="btn-primary" onClick={() => navigate('/accounting/budgets')}>
              <i className="fas fa-plus"></i> Create Budget
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default BudgetVariance;
