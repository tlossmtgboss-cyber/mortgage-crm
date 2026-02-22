import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function PayBills() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [payments, setPayments] = useState([]);
  const [unpaidBills, setUnpaidBills] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [viewMode, setViewMode] = useState('payments'); // payments, pay
  const [summary, setSummary] = useState({
    total_payments: 0,
    total_paid: 0,
    this_month: 0,
  });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [vendorFilter, setVendorFilter] = useState('');
  const [dateRange, setDateRange] = useState({ start: '', end: '' });

  // Pay bills form
  const [selectedBills, setSelectedBills] = useState([]);
  const [paymentForm, setPaymentForm] = useState({
    payment_date: new Date().toISOString().split('T')[0],
    payment_method: 'check',
    bank_account_id: '',
    check_number: '',
    reference: '',
    memo: '',
  });

  // Fetch payments
  const fetchPayments = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (searchTerm) params.search = searchTerm;
      if (vendorFilter) params.vendor_id = vendorFilter;
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end) params.end_date = dateRange.end;

      const data = await accountingAPI.getAPPayments(params);
      setPayments(data?.payments || []);
      setSummary(data?.summary || {
        total_payments: 0,
        total_paid: 0,
        this_month: 0,
      });
      setLoading(false);
    } catch (err) {
      console.error('Error fetching payments:', err);
      setLoading(false);
    }
  }, [searchTerm, vendorFilter, dateRange]);

  // Fetch unpaid bills
  const fetchUnpaidBills = useCallback(async () => {
    try {
      const data = await accountingAPI.getAPBills({ status: 'approved' });
      setUnpaidBills(data?.bills || []);
    } catch (err) {
      console.error('Error fetching unpaid bills:', err);
    }
  }, []);

  // Fetch vendors
  const fetchVendors = useCallback(async () => {
    try {
      const data = await accountingAPI.getAPVendors({ is_active: true });
      setVendors(data?.vendors || []);
    } catch (err) {
      console.error('Error fetching vendors:', err);
    }
  }, []);

  // Fetch bank accounts
  const fetchBankAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getBankAccounts();
      setBankAccounts(data?.accounts || []);
    } catch (err) {
      console.error('Error fetching bank accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchPayments();
    fetchVendors();
  }, [fetchPayments, fetchVendors]);

  useEffect(() => {
    if (viewMode === 'pay') {
      fetchUnpaidBills();
      fetchBankAccounts();
    }
  }, [viewMode, fetchUnpaidBills, fetchBankAccounts]);

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

  // Toggle bill selection
  const toggleBillSelection = (bill) => {
    setSelectedBills(prev => {
      const exists = prev.find(b => b.id === bill.id);
      if (exists) {
        return prev.filter(b => b.id !== bill.id);
      } else {
        return [...prev, { ...bill, payment_amount: bill.balance_due }];
      }
    });
  };

  // Update payment amount for a bill
  const updatePaymentAmount = (billId, amount) => {
    setSelectedBills(prev =>
      prev.map(b =>
        b.id === billId ? { ...b, payment_amount: parseFloat(amount) || 0 } : b
      )
    );
  };

  // Calculate total payment
  const calculateTotalPayment = () => {
    return selectedBills.reduce((sum, bill) => sum + (bill.payment_amount || 0), 0);
  };

  // Select all bills for a vendor
  const selectAllForVendor = (vendorId) => {
    const vendorBills = unpaidBills.filter(b => b.vendor_id === vendorId);
    setSelectedBills(prev => {
      const existingIds = prev.map(b => b.id);
      const newBills = vendorBills
        .filter(b => !existingIds.includes(b.id))
        .map(b => ({ ...b, payment_amount: b.balance_due }));
      return [...prev, ...newBills];
    });
  };

  // Clear selection
  const clearSelection = () => {
    setSelectedBills([]);
  };

  // Handle payment submission
  const handleSubmitPayment = async () => {
    if (selectedBills.length === 0) {
      toast.error('Please select at least one bill to pay.');
      return;
    }

    if (!paymentForm.bank_account_id) {
      toast.error('Please select a bank account.');
      return;
    }

    try {
      const payload = {
        ...paymentForm,
        total_amount: calculateTotalPayment(),
        bills: selectedBills.map(b => ({
          bill_id: b.id,
          amount: b.payment_amount,
        })),
      };

      await accountingAPI.createAPPayment(payload);

      setSelectedBills([]);
      setPaymentForm({
        payment_date: new Date().toISOString().split('T')[0],
        payment_method: 'check',
        bank_account_id: '',
        check_number: '',
        reference: '',
        memo: '',
      });
      setViewMode('payments');
      fetchPayments();
    } catch (err) {
      console.error('Error creating payment:', err);
      toast.error('Failed to create payment');
    }
  };

  // Handle void payment
  const handleVoidPayment = async (payment) => {
    if (!window.confirm('Are you sure you want to void this payment? This will reopen the associated bills.')) return;
    try {
      await accountingAPI.voidAPPayment(payment.id);
      fetchPayments();
    } catch (err) {
      console.error('Error voiding payment:', err);
      toast.error('Failed to void payment');
    }
  };

  // Group bills by vendor
  const billsByVendor = unpaidBills.reduce((acc, bill) => {
    const vendorId = bill.vendor_id;
    if (!acc[vendorId]) {
      acc[vendorId] = {
        vendor_id: vendorId,
        vendor_name: bill.vendor_name,
        bills: [],
        total: 0,
      };
    }
    acc[vendorId].bills.push(bill);
    acc[vendorId].total += bill.balance_due || 0;
    return acc;
  }, {});

  // Get payment method label
  const getPaymentMethodLabel = (method) => {
    const labels = {
      check: 'Check',
      ach: 'ACH Transfer',
      wire: 'Wire Transfer',
      credit_card: 'Credit Card',
      cash: 'Cash',
    };
    return labels[method] || method;
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Payments...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page pay-bills">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Pay Bills.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page pay-bills">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-money-check-alt"></i> Bill Payments</h1>
            <p className="subtitle">Pay vendor bills and manage payments</p>
          </div>
        </div>
        <div className="header-right">
          <div className="view-toggle">
            <button
              className={`toggle-btn ${viewMode === 'payments' ? 'active' : ''}`}
              onClick={() => setViewMode('payments')}
            >
              <i className="fas fa-history"></i> Payment History
            </button>
            <button
              className={`toggle-btn ${viewMode === 'pay' ? 'active' : ''}`}
              onClick={() => setViewMode('pay')}
            >
              <i className="fas fa-credit-card"></i> Pay Bills
            </button>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-receipt"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.total_payments}</span>
            <span className="summary-label">Total Payments</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-dollar-sign"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{formatCurrency(summary.total_paid)}</span>
            <span className="summary-label">Total Paid</span>
          </div>
        </div>
        <div className="summary-card info">
          <div className="summary-icon">
            <i className="fas fa-calendar"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{formatCurrency(summary.this_month)}</span>
            <span className="summary-label">This Month</span>
          </div>
        </div>
        {viewMode === 'pay' && (
          <div className="summary-card success">
            <div className="summary-icon">
              <i className="fas fa-check-circle"></i>
            </div>
            <div className="summary-content">
              <span className="summary-value">{formatCurrency(calculateTotalPayment())}</span>
              <span className="summary-label">Selected for Payment</span>
            </div>
          </div>
        )}
      </div>

      {viewMode === 'payments' ? (
        <>
          {/* Payment History View */}
          <div className="toolbar">
            <div className="toolbar-left">
              <div className="search-box">
                <i className="fas fa-search"></i>
                <input
                  type="text"
                  placeholder="Search payments..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
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
            </div>

            <div className="toolbar-right">
              <button className="toolbar-btn" onClick={fetchPayments} title="Refresh">
                <i className="fas fa-sync-alt"></i>
              </button>
            </div>
          </div>

          {/* Payments Table */}
          <div className="data-table">
            <div className="table-header">
              <div className="header-cell">Payment #</div>
              <div className="header-cell">Vendor</div>
              <div className="header-cell">Date</div>
              <div className="header-cell">Method</div>
              <div className="header-cell">Reference</div>
              <div className="header-cell">Amount</div>
              <div className="header-cell">Status</div>
              <div className="header-cell actions">Actions</div>
            </div>

            <div className="table-body">
              {payments.length > 0 ? (
                payments.map(payment => (
                  <div key={payment.id} className="table-row">
                    <div className="cell">
                      <span className="payment-number">{payment.payment_number}</span>
                    </div>
                    <div className="cell">{payment.vendor_name}</div>
                    <div className="cell">{formatDate(payment.payment_date)}</div>
                    <div className="cell">{getPaymentMethodLabel(payment.payment_method)}</div>
                    <div className="cell">
                      {payment.check_number && <span>Check #{payment.check_number}</span>}
                      {payment.reference && !payment.check_number && <span>{payment.reference}</span>}
                    </div>
                    <div className="cell amount">{formatCurrency(payment.total_amount)}</div>
                    <div className="cell">
                      <span className={`status-badge ${payment.status === 'voided' ? 'badge-error' : 'badge-success'}`}>
                        {payment.status}
                      </span>
                    </div>
                    <div className="cell actions">
                      {payment.status !== 'voided' && (
                        <button
                          className="action-btn danger"
                          onClick={() => handleVoidPayment(payment)}
                          title="Void Payment"
                        >
                          <i className="fas fa-ban"></i>
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">
                  <i className="fas fa-money-check-alt"></i>
                  <h3>No Payments Found</h3>
                  <p>No payment history to display.</p>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Pay Bills View */}
          <div className="pay-bills-container">
            <div className="bills-selection">
              <div className="selection-header">
                <h3>Select Bills to Pay</h3>
                {selectedBills.length > 0 && (
                  <button className="btn-link" onClick={clearSelection}>
                    Clear Selection ({selectedBills.length})
                  </button>
                )}
              </div>

              {Object.values(billsByVendor).length > 0 ? (
                <div className="vendor-bills-list">
                  {Object.values(billsByVendor).map(vendor => (
                    <div key={vendor.vendor_id} className="vendor-section">
                      <div className="vendor-header">
                        <div className="vendor-info">
                          <span className="vendor-name">{vendor.vendor_name}</span>
                          <span className="vendor-total">{formatCurrency(vendor.total)} outstanding</span>
                        </div>
                        <button
                          className="btn-link"
                          onClick={() => selectAllForVendor(vendor.vendor_id)}
                        >
                          Select All
                        </button>
                      </div>

                      <div className="bills-list">
                        {vendor.bills.map(bill => {
                          const isSelected = selectedBills.some(b => b.id === bill.id);
                          const selectedBill = selectedBills.find(b => b.id === bill.id);

                          return (
                            <div key={bill.id} className={`bill-item ${isSelected ? 'selected' : ''}`}>
                              <div className="bill-checkbox">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleBillSelection(bill)}
                                />
                              </div>
                              <div className="bill-info">
                                <span className="bill-number">{bill.bill_number}</span>
                                <span className="bill-date">Due: {formatDate(bill.due_date)}</span>
                              </div>
                              <div className="bill-amount">
                                <span className="balance">{formatCurrency(bill.balance_due)}</span>
                                {isSelected && (
                                  <input
                                    type="number"
                                    className="payment-input"
                                    value={selectedBill?.payment_amount || 0}
                                    onChange={(e) => updatePaymentAmount(bill.id, e.target.value)}
                                    max={bill.balance_due}
                                    step="0.01"
                                  />
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state small">
                  <i className="fas fa-check-circle"></i>
                  <h3>All Caught Up!</h3>
                  <p>No approved bills waiting for payment.</p>
                </div>
              )}
            </div>

            <div className="payment-details">
              <h3>Payment Details</h3>

              <div className="form-group">
                <label>Payment Date *</label>
                <input
                  type="date"
                  value={paymentForm.payment_date}
                  onChange={(e) => setPaymentForm(prev => ({ ...prev, payment_date: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group">
                <label>Bank Account *</label>
                <select
                  value={paymentForm.bank_account_id}
                  onChange={(e) => setPaymentForm(prev => ({ ...prev, bank_account_id: e.target.value }))}
                  required
                >
                  <option value="">Select Account</option>
                  {bankAccounts.map(acc => (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} ({formatCurrency(acc.balance)})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Payment Method *</label>
                <select
                  value={paymentForm.payment_method}
                  onChange={(e) => setPaymentForm(prev => ({ ...prev, payment_method: e.target.value }))}
                >
                  <option value="check">Check</option>
                  <option value="ach">ACH Transfer</option>
                  <option value="wire">Wire Transfer</option>
                  <option value="credit_card">Credit Card</option>
                  <option value="cash">Cash</option>
                </select>
              </div>

              {paymentForm.payment_method === 'check' && (
                <div className="form-group">
                  <label>Check Number</label>
                  <input
                    type="text"
                    value={paymentForm.check_number}
                    onChange={(e) => setPaymentForm(prev => ({ ...prev, check_number: e.target.value }))}
                    placeholder="Check #"
                  />
                </div>
              )}

              <div className="form-group">
                <label>Reference</label>
                <input
                  type="text"
                  value={paymentForm.reference}
                  onChange={(e) => setPaymentForm(prev => ({ ...prev, reference: e.target.value }))}
                  placeholder="Reference number"
                />
              </div>

              <div className="form-group">
                <label>Memo</label>
                <textarea
                  value={paymentForm.memo}
                  onChange={(e) => setPaymentForm(prev => ({ ...prev, memo: e.target.value }))}
                  placeholder="Payment notes..."
                  rows="2"
                />
              </div>

              <div className="payment-summary">
                <div className="summary-row">
                  <span>Bills Selected:</span>
                  <span>{selectedBills.length}</span>
                </div>
                <div className="summary-row total">
                  <span>Total Payment:</span>
                  <span>{formatCurrency(calculateTotalPayment())}</span>
                </div>
              </div>

              <button
                className="btn-primary full-width"
                onClick={handleSubmitPayment}
                disabled={selectedBills.length === 0}
              >
                <i className="fas fa-check"></i> Process Payment
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default PayBills;
