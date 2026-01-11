import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import '../AccountingShared.css';

function APAgingReport() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [agingData, setAgingData] = useState(null);
  const [vendors, setVendors] = useState([]);
  const [expandedVendors, setExpandedVendors] = useState(new Set());

  // Filters
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().split('T')[0]);
  const [vendorFilter, setVendorFilter] = useState('');
  const [showZeroBalance, setShowZeroBalance] = useState(false);

  // Fetch aging data
  const fetchAgingData = useCallback(async () => {
    try {
      setLoading(true);
      const params = {
        as_of_date: asOfDate,
        include_zero_balance: showZeroBalance,
      };
      if (vendorFilter) params.vendor_id = vendorFilter;

      const data = await accountingAPI.getAPAgingReport(params);
      setAgingData(data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching aging data:', err);
      setLoading(false);
    }
  }, [asOfDate, vendorFilter, showZeroBalance]);

  // Fetch vendors for filter
  const fetchVendors = useCallback(async () => {
    try {
      const data = await accountingAPI.getAPVendors({ is_active: true });
      setVendors(data?.vendors || []);
    } catch (err) {
      console.error('Error fetching vendors:', err);
    }
  }, []);

  useEffect(() => {
    fetchAgingData();
  }, [fetchAgingData]);

  useEffect(() => {
    fetchVendors();
  }, [fetchVendors]);

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

  // Toggle vendor expansion
  const toggleVendor = (vendorId) => {
    const newExpanded = new Set(expandedVendors);
    if (newExpanded.has(vendorId)) {
      newExpanded.delete(vendorId);
    } else {
      newExpanded.add(vendorId);
    }
    setExpandedVendors(newExpanded);
  };

  // Expand/collapse all
  const expandAll = () => {
    if (agingData?.vendors) {
      setExpandedVendors(new Set(agingData.vendors.map(v => v.vendor_id)));
    }
  };

  const collapseAll = () => {
    setExpandedVendors(new Set());
  };

  // Export to CSV
  const exportToCSV = () => {
    if (!agingData?.vendors) return;

    const headers = ['Vendor', 'Current', '1-30 Days', '31-60 Days', '61-90 Days', 'Over 90 Days', 'Total'];
    const rows = agingData.vendors.map(v => [
      v.vendor_name,
      v.current,
      v.days_1_30,
      v.days_31_60,
      v.days_61_90,
      v.days_over_90,
      v.total,
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
    a.download = `ap-aging-${asOfDate}.csv`;
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
  const vendorData = agingData?.vendors || [];

  return (
    <div className="accounting-page aging-report ap-aging">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-chart-bar"></i> AP Aging Report</h1>
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
            value={vendorFilter}
            onChange={(e) => setVendorFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Vendors</option>
            {vendors.map(v => (
              <option key={v.id} value={v.id}>{v.name}</option>
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
            <span className="aging-label">Total Payable</span>
          </div>
          <div className="aging-amount">{formatCurrency(summary.total)}</div>
          <div className="aging-count">{vendorData.length} vendors</div>
        </div>
      </div>

      {/* Aging Table */}
      <div className="aging-table">
        <div className="table-header">
          <div className="header-cell expand"></div>
          <div className="header-cell vendor">Vendor</div>
          <div className="header-cell amount">Current</div>
          <div className="header-cell amount">1-30</div>
          <div className="header-cell amount">31-60</div>
          <div className="header-cell amount">61-90</div>
          <div className="header-cell amount">90+</div>
          <div className="header-cell amount total">Total</div>
        </div>

        <div className="table-body">
          {vendorData.length > 0 ? (
            vendorData.map(vendor => (
              <div key={vendor.vendor_id} className="vendor-section">
                <div
                  className="vendor-row"
                  onClick={() => toggleVendor(vendor.vendor_id)}
                >
                  <div className="cell expand">
                    {vendor.bills?.length > 0 && (
                      <i className={`fas fa-chevron-${expandedVendors.has(vendor.vendor_id) ? 'down' : 'right'}`}></i>
                    )}
                  </div>
                  <div className="cell vendor">
                    <span className="vendor-name">{vendor.vendor_name}</span>
                  </div>
                  <div className="cell amount">{vendor.current > 0 ? formatCurrency(vendor.current) : '-'}</div>
                  <div className="cell amount">{vendor.days_1_30 > 0 ? formatCurrency(vendor.days_1_30) : '-'}</div>
                  <div className="cell amount">{vendor.days_31_60 > 0 ? formatCurrency(vendor.days_31_60) : '-'}</div>
                  <div className="cell amount">{vendor.days_61_90 > 0 ? formatCurrency(vendor.days_61_90) : '-'}</div>
                  <div className="cell amount overdue">{vendor.days_over_90 > 0 ? formatCurrency(vendor.days_over_90) : '-'}</div>
                  <div className="cell amount total">{formatCurrency(vendor.total)}</div>
                </div>

                {/* Bill Details */}
                {expandedVendors.has(vendor.vendor_id) && vendor.bills?.length > 0 && (
                  <div className="bill-details">
                    {vendor.bills.map(bill => (
                      <div key={bill.id} className="bill-row">
                        <div className="cell expand"></div>
                        <div className="cell vendor">
                          <span className="bill-info">
                            <span className="bill-number">{bill.bill_number}</span>
                            <span className="bill-date">{formatDate(bill.bill_date)}</span>
                            <span className="days-past-due">
                              {bill.days_past_due > 0 ? `${bill.days_past_due} days past due` : 'Current'}
                            </span>
                          </span>
                        </div>
                        <div className="cell amount">{bill.aging_bucket === 'current' ? formatCurrency(bill.balance_due) : '-'}</div>
                        <div className="cell amount">{bill.aging_bucket === '1-30' ? formatCurrency(bill.balance_due) : '-'}</div>
                        <div className="cell amount">{bill.aging_bucket === '31-60' ? formatCurrency(bill.balance_due) : '-'}</div>
                        <div className="cell amount">{bill.aging_bucket === '61-90' ? formatCurrency(bill.balance_due) : '-'}</div>
                        <div className="cell amount">{bill.aging_bucket === '90+' ? formatCurrency(bill.balance_due) : '-'}</div>
                        <div className="cell amount total">{formatCurrency(bill.balance_due)}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-chart-bar"></i>
              <h3>No Outstanding Payables</h3>
              <p>All vendor balances are zero as of {formatDate(asOfDate)}.</p>
            </div>
          )}
        </div>

        {/* Totals Row */}
        {vendorData.length > 0 && (
          <div className="totals-row">
            <div className="cell expand"></div>
            <div className="cell vendor"><strong>TOTAL</strong></div>
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

export default APAgingReport;
