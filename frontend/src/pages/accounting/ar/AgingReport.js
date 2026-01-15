import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';

function AgingReport() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [agingData, setAgingData] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [expandedCustomers, setExpandedCustomers] = useState(new Set());

  // Filters
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().split('T')[0]);
  const [customerFilter, setCustomerFilter] = useState('');
  const [showZeroBalance, setShowZeroBalance] = useState(false);

  // Fetch aging data
  const fetchAgingData = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        as_of_date: asOfDate,
        include_zero_balance: showZeroBalance,
      };
      if (customerFilter) params.customer_id = customerFilter;

      const data = await accountingAPI.getARAgingReport(params);
      setAgingData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching aging data:', err);
      setLoading(false);
    }
  }, [asOfDate, customerFilter, showZeroBalance]);

  // Fetch customers for filter
  const fetchCustomers = useCallback(async () => {
    try {
      const data = await accountingAPI.getARCustomers({ is_active: true });
      setCustomers(data?.customers || []);
    } catch (err) {
      console.error('Error fetching customers:', err);
    }
  }, []);

  useEffect(() => {
    fetchAgingData();
  }, [fetchAgingData]);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

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

  // Toggle customer expansion
  const toggleCustomer = (customerId) => {
    const newExpanded = new Set(expandedCustomers);
    if (newExpanded.has(customerId)) {
      newExpanded.delete(customerId);
    } else {
      newExpanded.add(customerId);
    }
    setExpandedCustomers(newExpanded);
  };

  // Expand/collapse all
  const expandAll = () => {
    if (agingData?.customers) {
      setExpandedCustomers(new Set(agingData.customers.map(c => c.customer_id)));
    }
  };

  const collapseAll = () => {
    setExpandedCustomers(new Set());
  };

  // Export to CSV
  const exportToCSV = () => {
    if (!agingData?.customers) return;

    const headers = ['Customer', 'Current', '1-30 Days', '31-60 Days', '61-90 Days', 'Over 90 Days', 'Total'];
    const rows = agingData.customers.map(c => [
      c.customer_name,
      c.current,
      c.days_1_30,
      c.days_31_60,
      c.days_61_90,
      c.days_over_90,
      c.total,
    ]);

    // Add totals row
    rows.push([
      'TOTAL',
      agingData.summary.current,
      agingData.summary.days_1_30,
      agingData.summary.days_31_60,
      agingData.summary.days_61_90,
      agingData.summary.days_over_90,
      agingData.summary.total,
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(r => r.join(',')),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ar-aging-${asOfDate}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Calculate percentage
  const calculatePercentage = (amount, total) => {
    if (!total || total === 0) return 0;
    return ((amount / total) * 100).toFixed(1);
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Aging Report...</p>
        </div>
      </div>
    );
  }

  const summary = agingData?.summary || {};
  const customerData = agingData?.customers || [];

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page aging-report">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access AR Aging Report.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page aging-report">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-chart-bar"></i> AR Aging Report</h1>
            <p className="subtitle">As of {formatDate(asOfDate)}</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={exportToCSV}>
            <i className="fas fa-download"></i> Export CSV
          </button>
          <button className="btn-secondary" onClick={() => window.print()}>
            <i className="fas fa-print"></i> Print
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar">
        <div className="toolbar-left">
          <div className="form-group inline">
            <label>As of Date:</label>
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="date-input"
            />
          </div>

          <select
            value={customerFilter}
            onChange={(e) => setCustomerFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Customers</option>
            {customers.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showZeroBalance}
              onChange={(e) => setShowZeroBalance(e.target.checked)}
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
          <button className="toolbar-btn" onClick={fetchAgingData} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="aging-summary-cards">
        <div className="aging-card current">
          <div className="aging-card-header">
            <span className="aging-label">Current</span>
            <span className="aging-percentage">{calculatePercentage(summary.current, summary.total)}%</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.current)}</div>
          <div className="aging-bar">
            <div
              className="aging-bar-fill"
              style={{ width: `${calculatePercentage(summary.current, summary.total)}%` }}
            ></div>
          </div>
        </div>

        <div className="aging-card days-1-30">
          <div className="aging-card-header">
            <span className="aging-label">1-30 Days</span>
            <span className="aging-percentage">{calculatePercentage(summary.days_1_30, summary.total)}%</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.days_1_30)}</div>
          <div className="aging-bar">
            <div
              className="aging-bar-fill"
              style={{ width: `${calculatePercentage(summary.days_1_30, summary.total)}%` }}
            ></div>
          </div>
        </div>

        <div className="aging-card days-31-60">
          <div className="aging-card-header">
            <span className="aging-label">31-60 Days</span>
            <span className="aging-percentage">{calculatePercentage(summary.days_31_60, summary.total)}%</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.days_31_60)}</div>
          <div className="aging-bar">
            <div
              className="aging-bar-fill"
              style={{ width: `${calculatePercentage(summary.days_31_60, summary.total)}%` }}
            ></div>
          </div>
        </div>

        <div className="aging-card days-61-90">
          <div className="aging-card-header">
            <span className="aging-label">61-90 Days</span>
            <span className="aging-percentage">{calculatePercentage(summary.days_61_90, summary.total)}%</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.days_61_90)}</div>
          <div className="aging-bar">
            <div
              className="aging-bar-fill"
              style={{ width: `${calculatePercentage(summary.days_61_90, summary.total)}%` }}
            ></div>
          </div>
        </div>

        <div className="aging-card over-90">
          <div className="aging-card-header">
            <span className="aging-label">Over 90 Days</span>
            <span className="aging-percentage">{calculatePercentage(summary.days_over_90, summary.total)}%</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.days_over_90)}</div>
          <div className="aging-bar">
            <div
              className="aging-bar-fill"
              style={{ width: `${calculatePercentage(summary.days_over_90, summary.total)}%` }}
            ></div>
          </div>
        </div>

        <div className="aging-card total">
          <div className="aging-card-header">
            <span className="aging-label">Total Outstanding</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.total)}</div>
          <div className="aging-count">{customerData.length} customers</div>
        </div>
      </div>

      {/* Aging Table */}
      <div className="aging-table">
        <div className="table-header">
          <div className="header-cell expand"></div>
          <div className="header-cell customer">Customer</div>
          <div className="header-cell amount">Current</div>
          <div className="header-cell amount">1-30</div>
          <div className="header-cell amount">31-60</div>
          <div className="header-cell amount">61-90</div>
          <div className="header-cell amount">90+</div>
          <div className="header-cell amount total">Total</div>
        </div>

        <div className="table-body">
          {customerData.length > 0 ? (
            customerData.map(customer => (
              <div key={customer.customer_id} className="customer-section">
                <div
                  className="customer-row"
                  onClick={() => toggleCustomer(customer.customer_id)}
                >
                  <div className="cell expand">
                    {customer.invoices?.length > 0 && (
                      <i className={`fas fa-chevron-${expandedCustomers.has(customer.customer_id) ? 'down' : 'right'}`}></i>
                    )}
                  </div>
                  <div className="cell customer">
                    <span className="customer-name">{customer.customer_name}</span>
                  </div>
                  <div className="cell amount">{customer.current > 0 ? formatCurrency(customer.current) : '-'}</div>
                  <div className="cell amount">{customer.days_1_30 > 0 ? formatCurrency(customer.days_1_30) : '-'}</div>
                  <div className="cell amount">{customer.days_31_60 > 0 ? formatCurrency(customer.days_31_60) : '-'}</div>
                  <div className="cell amount">{customer.days_61_90 > 0 ? formatCurrency(customer.days_61_90) : '-'}</div>
                  <div className="cell amount overdue">{customer.days_over_90 > 0 ? formatCurrency(customer.days_over_90) : '-'}</div>
                  <div className="cell amount total">{formatCurrency(customer.total)}</div>
                </div>

                {/* Invoice Details */}
                {expandedCustomers.has(customer.customer_id) && customer.invoices?.length > 0 && (
                  <div className="invoice-details">
                    {customer.invoices.map(invoice => (
                      <div key={invoice.id} className="invoice-row">
                        <div className="cell expand"></div>
                        <div className="cell customer">
                          <span className="invoice-info">
                            <span className="invoice-number">{invoice.invoice_number}</span>
                            <span className="invoice-date">{formatDate(invoice.invoice_date)}</span>
                            <span className="days-past-due">
                              {invoice.days_past_due > 0 ? `${invoice.days_past_due} days past due` : 'Current'}
                            </span>
                          </span>
                        </div>
                        <div className="cell amount">{invoice.aging_bucket === 'current' ? formatCurrency(invoice.balance_due) : '-'}</div>
                        <div className="cell amount">{invoice.aging_bucket === '1-30' ? formatCurrency(invoice.balance_due) : '-'}</div>
                        <div className="cell amount">{invoice.aging_bucket === '31-60' ? formatCurrency(invoice.balance_due) : '-'}</div>
                        <div className="cell amount">{invoice.aging_bucket === '61-90' ? formatCurrency(invoice.balance_due) : '-'}</div>
                        <div className="cell amount">{invoice.aging_bucket === '90+' ? formatCurrency(invoice.balance_due) : '-'}</div>
                        <div className="cell amount total">{formatCurrency(invoice.balance_due)}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-chart-bar"></i>
              <h3>No Outstanding Receivables</h3>
              <p>All customer balances are zero as of {formatDate(asOfDate)}.</p>
            </div>
          )}
        </div>

        {/* Totals Row */}
        {customerData.length > 0 && (
          <div className="totals-row">
            <div className="cell expand"></div>
            <div className="cell customer"><strong>TOTAL</strong></div>
            <div className="cell amount"><strong>{formatCurrency(summary.current)}</strong></div>
            <div className="cell amount"><strong>{formatCurrency(summary.days_1_30)}</strong></div>
            <div className="cell amount"><strong>{formatCurrency(summary.days_31_60)}</strong></div>
            <div className="cell amount"><strong>{formatCurrency(summary.days_61_90)}</strong></div>
            <div className="cell amount overdue"><strong>{formatCurrency(summary.days_over_90)}</strong></div>
            <div className="cell amount total"><strong>{formatCurrency(summary.total)}</strong></div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgingReport;
