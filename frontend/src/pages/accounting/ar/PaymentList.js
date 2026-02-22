import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function PaymentList() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [payments, setPayments] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [openInvoices, setOpenInvoices] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 25, total: 0 });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [customerFilter, setCustomerFilter] = useState('');
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0],
    end: new Date().toISOString().split('T')[0],
  });

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    customer_id: searchParams.get('customer') || '',
    payment_date: new Date().toISOString().split('T')[0],
    payment_method: 'check',
    reference_number: '',
    deposit_to_account_id: '',
    amount: '',
    memo: '',
    applications: [], // { invoice_id, amount }
  });

  const paymentMethods = [
    { value: 'check', label: 'Check' },
    { value: 'cash', label: 'Cash' },
    { value: 'credit_card', label: 'Credit Card' },
    { value: 'ach', label: 'ACH/Bank Transfer' },
    { value: 'wire', label: 'Wire Transfer' },
    { value: 'other', label: 'Other' },
  ];

  // Fetch payments
  const fetchPayments = useCallback(async () => {
    try {
      const params = {
        page: pagination.page,
        limit: pagination.limit,
        start_date: dateRange.start,
        end_date: dateRange.end,
      };
      if (searchTerm) params.search = searchTerm;
      if (customerFilter) params.customer_id = customerFilter;

      const data = await accountingAPI.getARPayments(params);
      setPayments(data?.payments || []);
      setPagination(prev => ({ ...prev, total: data?.total || 0 }));
      setLoading(false);
    } catch (err) {
      console.error('Error fetching payments:', err);
      setLoading(false);
    }
  }, [pagination.page, pagination.limit, dateRange, searchTerm, customerFilter]);

  // Fetch reference data
  const fetchReferenceData = useCallback(async () => {
    try {
      const [customersData, accountsData] = await Promise.all([
        accountingAPI.getARCustomers({ is_active: true }),
        accountingAPI.getAccounts({ is_bank_account: true, is_active: true }),
      ]);
      setCustomers(customersData?.customers || []);
      setBankAccounts(accountsData?.accounts || []);
    } catch (err) {
      console.error('Error fetching reference data:', err);
    }
  }, []);

  // Fetch open invoices for a customer
  const fetchOpenInvoices = useCallback(async (customerId) => {
    if (!customerId) {
      setOpenInvoices([]);
      return;
    }
    try {
      const data = await accountingAPI.getARInvoices({
        customer_id: customerId,
        status: 'open', // sent, viewed, partial, overdue
      });
      setOpenInvoices(data?.invoices || []);
    } catch (err) {
      console.error('Error fetching invoices:', err);
    }
  }, []);

  useEffect(() => {
    fetchPayments();
  }, [fetchPayments]);

  useEffect(() => {
    fetchReferenceData();
  }, [fetchReferenceData]);

  // Check for invoice param and set up form
  useEffect(() => {
    const invoiceId = searchParams.get('invoice');
    if (invoiceId && showModal) {
      // Fetch invoice details and pre-populate
      accountingAPI.getARInvoice(invoiceId).then(invoice => {
        if (invoice) {
          setFormData(prev => ({
            ...prev,
            customer_id: invoice.customer_id,
            amount: invoice.balance_due,
            applications: [{ invoice_id: invoice.id, amount: invoice.balance_due }],
          }));
          fetchOpenInvoices(invoice.customer_id);
        }
      }).catch(console.error);
    }
  }, [searchParams, showModal, fetchOpenInvoices]);

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

  // Open create modal
  const openCreateModal = () => {
    const invoiceId = searchParams.get('invoice');
    const customerId = searchParams.get('customer') || '';

    setFormData({
      customer_id: customerId,
      payment_date: new Date().toISOString().split('T')[0],
      payment_method: 'check',
      reference_number: '',
      deposit_to_account_id: bankAccounts[0]?.id || '',
      amount: '',
      memo: '',
      applications: [],
    });

    if (customerId) {
      fetchOpenInvoices(customerId);
    }

    setShowModal(true);
  };

  // Handle form change
  const handleFormChange = (field, value) => {
    setFormData(prev => {
      const updated = { ...prev, [field]: value };

      // Fetch invoices when customer changes
      if (field === 'customer_id') {
        fetchOpenInvoices(value);
        updated.applications = [];
      }

      return updated;
    });
  };

  // Handle application change
  const handleApplicationChange = (invoiceId, amount) => {
    setFormData(prev => {
      const existingIdx = prev.applications.findIndex(a => a.invoice_id === invoiceId);
      const newApplications = [...prev.applications];

      if (amount && parseFloat(amount) > 0) {
        if (existingIdx >= 0) {
          newApplications[existingIdx].amount = parseFloat(amount);
        } else {
          newApplications.push({ invoice_id: invoiceId, amount: parseFloat(amount) });
        }
      } else if (existingIdx >= 0) {
        newApplications.splice(existingIdx, 1);
      }

      // Auto-calculate total
      const totalApplied = newApplications.reduce((sum, a) => sum + a.amount, 0);

      return {
        ...prev,
        applications: newApplications,
        amount: totalApplied || prev.amount,
      };
    });
  };

  // Get applied amount for an invoice
  const getAppliedAmount = (invoiceId) => {
    const app = formData.applications.find(a => a.invoice_id === invoiceId);
    return app?.amount || '';
  };

  // Apply full balance
  const applyFullBalance = (invoice) => {
    handleApplicationChange(invoice.id, invoice.balance_due);
  };

  // Calculate total applied
  const getTotalApplied = () => {
    return formData.applications.reduce((sum, a) => sum + (a.amount || 0), 0);
  };

  // Save payment
  const handleSave = async () => {
    if (!formData.customer_id) {
      toast.error('Please select a customer.');
      return;
    }
    if (!formData.amount || parseFloat(formData.amount) <= 0) {
      toast.error('Please enter a payment amount.');
      return;
    }
    if (!formData.deposit_to_account_id) {
      toast.error('Please select a deposit account.');
      return;
    }

    try {
      setSaving(true);

      const data = {
        customer_id: formData.customer_id,
        payment_date: formData.payment_date,
        payment_method: formData.payment_method,
        reference_number: formData.reference_number || null,
        deposit_to_account_id: formData.deposit_to_account_id,
        amount: parseFloat(formData.amount),
        memo: formData.memo || null,
        applications: formData.applications.filter(a => a.amount > 0),
      };

      await accountingAPI.createARPayment(data);
      setShowModal(false);
      fetchPayments();
    } catch (err) {
      console.error('Error saving payment:', err);
      toast.error(err.response?.data?.detail || 'Failed to save payment.');
    } finally {
      setSaving(false);
    }
  };

  // Delete payment
  const handleDelete = async (payment) => {
    if (!window.confirm('Are you sure you want to delete this payment? This will reopen any applied invoices.')) {
      return;
    }

    try {
      await accountingAPI.deleteARPayment(payment.id);
      fetchPayments();
    } catch (err) {
      console.error('Error deleting payment:', err);
      toast.error('Failed to delete payment.');
    }
  };

  const totalPages = Math.ceil(pagination.total / pagination.limit);
  const totalApplied = getTotalApplied();
  const unappliedAmount = parseFloat(formData.amount || 0) - totalApplied;

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
      <div className="accounting-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Payments.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-hand-holding-usd"></i> Payments Received</h1>
            <p className="subtitle">{pagination.total} payments</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={openCreateModal}>
            <i className="fas fa-plus"></i> Receive Payment
          </button>
        </div>
      </div>

      {/* Toolbar */}
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
            value={customerFilter}
            onChange={(e) => setCustomerFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Customers</option>
            {customers.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>

          <div className="date-range">
            <input
              type="date"
              value={dateRange.start}
              onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
              className="date-input"
            />
            <span className="date-separator">to</span>
            <input
              type="date"
              value={dateRange.end}
              onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
              className="date-input"
            />
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards three-col">
        <div className="summary-card">
          <div className="summary-icon green">
            <i className="fas fa-dollar-sign"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(payments.reduce((sum, p) => sum + (p.amount || 0), 0))}
            </span>
            <span className="summary-label">Total Received</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon blue">
            <i className="fas fa-receipt"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">{payments.length}</span>
            <span className="summary-label">Payments</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon orange">
            <i className="fas fa-file-invoice"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {payments.reduce((sum, p) => sum + (p.invoices_applied || 0), 0)}
            </span>
            <span className="summary-label">Invoices Paid</span>
          </div>
        </div>
      </div>

      {/* Payments Table */}
      <div className="data-table">
        <div className="table-header">
          <div className="header-cell date">Date</div>
          <div className="header-cell reference">Payment #</div>
          <div className="header-cell customer">Customer</div>
          <div className="header-cell method">Method</div>
          <div className="header-cell amount">Amount</div>
          <div className="header-cell reference">Reference</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {payments.length > 0 ? (
            payments.map(payment => (
              <div key={payment.id} className="table-row">
                <div className="cell date">{formatDate(payment.payment_date)}</div>
                <div className="cell reference">
                  <span className="payment-number">{payment.payment_number}</span>
                </div>
                <div className="cell customer">{payment.customer_name}</div>
                <div className="cell method">
                  <span className="method-badge">
                    {paymentMethods.find(m => m.value === payment.payment_method)?.label || payment.payment_method}
                  </span>
                </div>
                <div className="cell amount">{formatCurrency(payment.amount)}</div>
                <div className="cell reference">{payment.reference_number || '-'}</div>
                <div className="cell actions">
                  <button
                    className="action-btn"
                    onClick={() => navigate(`/accounting/ar/payments/${payment.id}`)}
                    title="View"
                  >
                    <i className="fas fa-eye"></i>
                  </button>
                  <button
                    className="action-btn delete"
                    onClick={() => handleDelete(payment)}
                    title="Delete"
                  >
                    <i className="fas fa-trash"></i>
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-hand-holding-usd"></i>
              <h3>No Payments Found</h3>
              <p>Try adjusting your filters or record a new payment.</p>
              <button className="btn-primary" onClick={openCreateModal}>
                <i className="fas fa-plus"></i> Receive Payment
              </button>
            </div>
          )}
        </div>

        {totalPages > 1 && (
          <div className="pagination">
            <button
              className="page-btn"
              onClick={() => setPagination(prev => ({ ...prev, page: prev.page - 1 }))}
              disabled={pagination.page === 1}
            >
              <i className="fas fa-chevron-left"></i>
            </button>
            <span className="page-info">Page {pagination.page} of {totalPages}</span>
            <button
              className="page-btn"
              onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
              disabled={pagination.page >= totalPages}
            >
              <i className="fas fa-chevron-right"></i>
            </button>
          </div>
        )}
      </div>

      {/* Payment Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content xlarge" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <i className="fas fa-hand-holding-usd"></i>
                Receive Payment
              </h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              {/* Payment Info */}
              <div className="form-section">
                <div className="form-row">
                  <div className="form-group">
                    <label>Customer <span className="required">*</span></label>
                    <select
                      value={formData.customer_id}
                      onChange={(e) => handleFormChange('customer_id', e.target.value)}
                    >
                      <option value="">Select Customer</option>
                      {customers.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Payment Date</label>
                    <input
                      type="date"
                      value={formData.payment_date}
                      onChange={(e) => handleFormChange('payment_date', e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Payment Method</label>
                    <select
                      value={formData.payment_method}
                      onChange={(e) => handleFormChange('payment_method', e.target.value)}
                    >
                      {paymentMethods.map(m => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Reference / Check #</label>
                    <input
                      type="text"
                      value={formData.reference_number}
                      onChange={(e) => handleFormChange('reference_number', e.target.value)}
                      placeholder="Check number, transaction ID, etc."
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Deposit To <span className="required">*</span></label>
                    <select
                      value={formData.deposit_to_account_id}
                      onChange={(e) => handleFormChange('deposit_to_account_id', e.target.value)}
                    >
                      <option value="">Select Account</option>
                      {bankAccounts.map(a => (
                        <option key={a.id} value={a.id}>{a.account_number} - {a.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Amount Received <span className="required">*</span></label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.amount}
                      onChange={(e) => handleFormChange('amount', e.target.value)}
                      placeholder="0.00"
                      className="amount-input"
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Memo</label>
                  <input
                    type="text"
                    value={formData.memo}
                    onChange={(e) => handleFormChange('memo', e.target.value)}
                    placeholder="Internal memo..."
                  />
                </div>
              </div>

              {/* Invoice Applications */}
              {formData.customer_id && (
                <div className="form-section">
                  <h3>Apply to Invoices</h3>

                  {openInvoices.length > 0 ? (
                    <div className="invoice-applications">
                      <div className="applications-header">
                        <div className="app-cell date">Date</div>
                        <div className="app-cell invoice">Invoice #</div>
                        <div className="app-cell amount">Original</div>
                        <div className="app-cell amount">Balance</div>
                        <div className="app-cell apply">Apply</div>
                      </div>

                      {openInvoices.map(invoice => (
                        <div key={invoice.id} className="application-row">
                          <div className="app-cell date">{formatDate(invoice.invoice_date)}</div>
                          <div className="app-cell invoice">{invoice.invoice_number}</div>
                          <div className="app-cell amount">{formatCurrency(invoice.total_amount)}</div>
                          <div className="app-cell amount">{formatCurrency(invoice.balance_due)}</div>
                          <div className="app-cell apply">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              max={invoice.balance_due}
                              value={getAppliedAmount(invoice.id)}
                              onChange={(e) => handleApplicationChange(invoice.id, e.target.value)}
                              placeholder="0.00"
                            />
                            <button
                              type="button"
                              className="apply-full-btn"
                              onClick={() => applyFullBalance(invoice)}
                              title="Apply full balance"
                            >
                              <i className="fas fa-check"></i>
                            </button>
                          </div>
                        </div>
                      ))}

                      <div className="applications-summary">
                        <div className="summary-row">
                          <span>Amount Received:</span>
                          <span>{formatCurrency(formData.amount)}</span>
                        </div>
                        <div className="summary-row">
                          <span>Applied to Invoices:</span>
                          <span>{formatCurrency(totalApplied)}</span>
                        </div>
                        <div className={`summary-row ${unappliedAmount !== 0 ? 'warning' : ''}`}>
                          <span>Unapplied:</span>
                          <span>{formatCurrency(unappliedAmount)}</span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="no-invoices-message">
                      <i className="fas fa-check-circle"></i>
                      <p>No open invoices for this customer.</p>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSave}
                disabled={saving || !formData.customer_id || !formData.amount}
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving...</>
                ) : (
                  <><i className="fas fa-check"></i> Save Payment</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PaymentList;
