import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function InvoiceList() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 25, total: 0 });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [customerFilter, setCustomerFilter] = useState(searchParams.get('customer') || '');
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0],
    end: new Date().toISOString().split('T')[0],
  });

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState('create');
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const initialFormData = {
    customer_id: searchParams.get('customer') || '',
    invoice_date: new Date().toISOString().split('T')[0],
    due_date: '',
    reference_number: '',
    notes: '',
    terms: '',
    lines: [
      { account_id: '', description: '', quantity: 1, unit_price: '', amount: '' },
    ],
  };
  const [formData, setFormData] = useState(initialFormData);

  const statusOptions = [
    { value: 'all', label: 'All Status' },
    { value: 'draft', label: 'Draft', color: '#6b7280' },
    { value: 'sent', label: 'Sent', color: '#3b82f6' },
    { value: 'viewed', label: 'Viewed', color: '#B8924A' },
    { value: 'partial', label: 'Partial', color: '#f97316' },
    { value: 'paid', label: 'Paid', color: '#22c55e' },
    { value: 'overdue', label: 'Overdue', color: '#ef4444' },
    { value: 'void', label: 'Void', color: '#6b7280' },
  ];

  // Fetch invoices
  const fetchInvoices = useCallback(async () => {
    try {
      setError(null);
      const params = {
        page: pagination.page,
        limit: pagination.limit,
        start_date: dateRange.start,
        end_date: dateRange.end,
      };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (searchTerm) params.search = searchTerm;
      if (customerFilter) params.customer_id = customerFilter;

      const data = await accountingAPI.getARInvoices(params);
      setInvoices(data?.invoices || []);
      setPagination(prev => ({ ...prev, total: data?.total || 0 }));
      setLoading(false);
    } catch (err) {
      console.error('Error fetching invoices:', err);
      setError('Failed to load invoices. Please try again.');
      setLoading(false);
    }
  }, [pagination.page, pagination.limit, statusFilter, dateRange, searchTerm, customerFilter]);

  // Fetch customers and accounts
  const fetchReferenceData = useCallback(async () => {
    try {
      const [customersData, accountsData] = await Promise.all([
        accountingAPI.getARCustomers({ is_active: true }),
        accountingAPI.getAccounts({ account_type: 'revenue', is_active: true }),
      ]);
      setCustomers(customersData?.customers || []);
      setAccounts(accountsData?.accounts || []);
    } catch (err) {
      console.error('Error fetching reference data:', err);
    }
  }, []);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  useEffect(() => {
    fetchReferenceData();
  }, [fetchReferenceData]);

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

  // Calculate line amount
  const calculateLineAmount = (line) => {
    const qty = parseFloat(line.quantity) || 0;
    const price = parseFloat(line.unit_price) || 0;
    return qty * price;
  };

  // Calculate totals
  const calculateTotals = () => {
    let subtotal = 0;
    formData.lines.forEach(line => {
      subtotal += calculateLineAmount(line);
    });
    return { subtotal, total: subtotal };
  };

  // Calculate due date based on customer terms
  const calculateDueDate = (customerId, invoiceDate) => {
    const customer = customers.find(c => c.id === customerId);
    if (!customer || !invoiceDate) return '';

    const terms = customer.payment_terms || 'net_30';
    const days = {
      'due_on_receipt': 0,
      'net_15': 15,
      'net_30': 30,
      'net_45': 45,
      'net_60': 60,
      'net_90': 90,
    }[terms] || 30;

    const due = new Date(invoiceDate);
    due.setDate(due.getDate() + days);
    return due.toISOString().split('T')[0];
  };

  // Open create modal
  const openCreateModal = () => {
    setModalMode('create');
    setSelectedInvoice(null);
    const customerId = searchParams.get('customer') || '';
    const invoiceDate = new Date().toISOString().split('T')[0];
    setFormData({
      ...initialFormData,
      customer_id: customerId,
      invoice_date: invoiceDate,
      due_date: customerId ? calculateDueDate(customerId, invoiceDate) : '',
    });
    setShowModal(true);
  };

  // Open edit modal
  const openEditModal = async (invoice) => {
    if (invoice.status !== 'draft') {
      toast.error('Only draft invoices can be edited.');
      return;
    }
    setModalMode('edit');
    setSelectedInvoice(invoice);

    try {
      const fullInvoice = await accountingAPI.getARInvoice(invoice.id);
      setFormData({
        customer_id: fullInvoice.customer_id || '',
        invoice_date: fullInvoice.invoice_date?.split('T')[0] || '',
        due_date: fullInvoice.due_date?.split('T')[0] || '',
        reference_number: fullInvoice.reference_number || '',
        notes: fullInvoice.notes || '',
        terms: fullInvoice.terms || '',
        lines: fullInvoice.lines?.map(line => ({
          id: line.id,
          account_id: line.account_id || '',
          description: line.description || '',
          quantity: line.quantity || 1,
          unit_price: line.unit_price || '',
          amount: line.amount || '',
        })) || [{ account_id: '', description: '', quantity: 1, unit_price: '', amount: '' }],
      });
      setShowModal(true);
    } catch (err) {
      console.error('Error fetching invoice:', err);
      toast.error('Failed to load invoice details.');
    }
  };

  // Handle form change
  const handleFormChange = (field, value) => {
    setFormData(prev => {
      const updated = { ...prev, [field]: value };

      // Auto-calculate due date when customer or invoice date changes
      if (field === 'customer_id' || field === 'invoice_date') {
        const customerId = field === 'customer_id' ? value : prev.customer_id;
        const invoiceDate = field === 'invoice_date' ? value : prev.invoice_date;
        if (customerId && invoiceDate) {
          updated.due_date = calculateDueDate(customerId, invoiceDate);
        }
      }

      return updated;
    });
  };

  // Handle line change
  const handleLineChange = (index, field, value) => {
    setFormData(prev => {
      const newLines = [...prev.lines];
      newLines[index] = { ...newLines[index], [field]: value };

      // Auto-calculate amount
      if (field === 'quantity' || field === 'unit_price') {
        newLines[index].amount = calculateLineAmount(newLines[index]);
      }

      return { ...prev, lines: newLines };
    });
  };

  // Add line
  const addLine = () => {
    setFormData(prev => ({
      ...prev,
      lines: [...prev.lines, { account_id: '', description: '', quantity: 1, unit_price: '', amount: '' }],
    }));
  };

  // Remove line
  const removeLine = (index) => {
    if (formData.lines.length <= 1) {
      toast.error('Invoice must have at least 1 line item.');
      return;
    }
    setFormData(prev => ({
      ...prev,
      lines: prev.lines.filter((_, i) => i !== index),
    }));
  };

  // Save invoice
  const handleSave = async (asDraft = true) => {
    if (!formData.customer_id) {
      toast.error('Please select a customer.');
      return;
    }

    const validLines = formData.lines.filter(line =>
      line.account_id && (parseFloat(line.amount) > 0 || parseFloat(line.unit_price) > 0)
    );

    if (validLines.length === 0) {
      toast.error('Invoice must have at least 1 valid line item.');
      return;
    }

    try {
      setSaving(true);

      const data = {
        customer_id: formData.customer_id,
        invoice_date: formData.invoice_date,
        due_date: formData.due_date,
        reference_number: formData.reference_number || null,
        notes: formData.notes || null,
        terms: formData.terms || null,
        status: asDraft ? 'draft' : 'sent',
        lines: validLines.map(line => ({
          account_id: line.account_id,
          description: line.description || null,
          quantity: parseFloat(line.quantity) || 1,
          unit_price: parseFloat(line.unit_price) || 0,
          amount: parseFloat(line.amount) || calculateLineAmount(line),
        })),
      };

      if (modalMode === 'create') {
        await accountingAPI.createARInvoice(data);
      } else {
        await accountingAPI.updateARInvoice(selectedInvoice.id, data);
      }

      setShowModal(false);
      fetchInvoices();
    } catch (err) {
      console.error('Error saving invoice:', err);
      toast.error(err.response?.data?.detail || 'Failed to save invoice. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Send invoice
  const handleSend = async (invoice) => {
    if (invoice.status !== 'draft') {
      toast.success('Only draft invoices can be sent.');
      return;
    }

    if (!window.confirm('Send this invoice to the customer?')) return;

    try {
      await accountingAPI.sendARInvoice(invoice.id);
      fetchInvoices();
    } catch (err) {
      console.error('Error sending invoice:', err);
      toast.error('Failed to send invoice.');
    }
  };

  // Void invoice
  const handleVoid = async (invoice) => {
    if (invoice.status === 'paid') {
      toast.error('Paid invoices cannot be voided.');
      return;
    }

    const reason = window.prompt('Reason for voiding this invoice:');
    if (!reason) return;

    try {
      await accountingAPI.voidARInvoice(invoice.id, { reason });
      fetchInvoices();
    } catch (err) {
      console.error('Error voiding invoice:', err);
      toast.error('Failed to void invoice.');
    }
  };

  // Get status badge
  const getStatusBadge = (status) => {
    const statusInfo = statusOptions.find(s => s.value === status) || statusOptions[1];
    return (
      <span
        className="status-badge"
        style={{ backgroundColor: `${statusInfo.color}15`, color: statusInfo.color }}
      >
        {statusInfo.label}
      </span>
    );
  };

  const totalPages = Math.ceil(pagination.total / pagination.limit);
  const { subtotal, total } = calculateTotals();

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Invoices...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Invoices.</p>
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
            <h1><i className="fas fa-file-invoice-dollar"></i> Invoices</h1>
            <p className="subtitle">{pagination.total} invoices</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={openCreateModal}>
            <i className="fas fa-plus"></i> New Invoice
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
              placeholder="Search invoices..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            {statusOptions.map(status => (
              <option key={status.value} value={status.value}>{status.label}</option>
            ))}
          </select>

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
      <div className="summary-cards four-col">
        <div className="summary-card">
          <div className="summary-icon blue">
            <i className="fas fa-file-invoice"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">{invoices.length}</span>
            <span className="summary-label">Total Invoices</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon green">
            <i className="fas fa-check-circle"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(invoices.filter(i => i.status === 'paid').reduce((sum, i) => sum + (i.total_amount || 0), 0))}
            </span>
            <span className="summary-label">Paid</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon orange">
            <i className="fas fa-clock"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(invoices.filter(i => ['sent', 'viewed', 'partial'].includes(i.status)).reduce((sum, i) => sum + (i.balance_due || 0), 0))}
            </span>
            <span className="summary-label">Outstanding</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon red">
            <i className="fas fa-exclamation-triangle"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(invoices.filter(i => i.status === 'overdue').reduce((sum, i) => sum + (i.balance_due || 0), 0))}
            </span>
            <span className="summary-label">Overdue</span>
          </div>
        </div>
      </div>

      {/* Invoices Table */}
      <div className="data-table">
        <div className="table-header">
          <div className="header-cell date">Date</div>
          <div className="header-cell invoice-num">Invoice #</div>
          <div className="header-cell customer">Customer</div>
          <div className="header-cell date">Due Date</div>
          <div className="header-cell amount">Amount</div>
          <div className="header-cell amount">Balance</div>
          <div className="header-cell status">Status</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {invoices.length > 0 ? (
            invoices.map(invoice => (
              <div key={invoice.id} className={`table-row ${invoice.status}`}>
                <div className="cell date">{formatDate(invoice.invoice_date)}</div>
                <div className="cell invoice-num">
                  <span className="invoice-number">{invoice.invoice_number}</span>
                </div>
                <div className="cell customer">
                  <span className="customer-name">{invoice.customer_name}</span>
                </div>
                <div className="cell date">
                  <span className={invoice.status === 'overdue' ? 'overdue-text' : ''}>
                    {formatDate(invoice.due_date)}
                  </span>
                </div>
                <div className="cell amount">{formatCurrency(invoice.total_amount)}</div>
                <div className="cell amount">
                  {invoice.balance_due > 0 ? formatCurrency(invoice.balance_due) : '-'}
                </div>
                <div className="cell status">{getStatusBadge(invoice.status)}</div>
                <div className="cell actions">
                  <button
                    className="action-btn"
                    onClick={() => navigate(`/accounting/ar/invoices/${invoice.id}`)}
                    title="View"
                  >
                    <i className="fas fa-eye"></i>
                  </button>
                  {invoice.status === 'draft' && (
                    <>
                      <button
                        className="action-btn"
                        onClick={() => openEditModal(invoice)}
                        title="Edit"
                      >
                        <i className="fas fa-edit"></i>
                      </button>
                      <button
                        className="action-btn send"
                        onClick={() => handleSend(invoice)}
                        title="Send"
                      >
                        <i className="fas fa-paper-plane"></i>
                      </button>
                    </>
                  )}
                  {['sent', 'viewed', 'partial', 'overdue'].includes(invoice.status) && (
                    <button
                      className="action-btn payment"
                      onClick={() => navigate(`/accounting/ar/payments/new?invoice=${invoice.id}`)}
                      title="Record Payment"
                    >
                      <i className="fas fa-dollar-sign"></i>
                    </button>
                  )}
                  {invoice.status !== 'paid' && invoice.status !== 'void' && (
                    <button
                      className="action-btn void"
                      onClick={() => handleVoid(invoice)}
                      title="Void"
                    >
                      <i className="fas fa-ban"></i>
                    </button>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-file-invoice-dollar"></i>
              <h3>No Invoices Found</h3>
              <p>Try adjusting your filters or create a new invoice.</p>
              <button className="btn-primary" onClick={openCreateModal}>
                <i className="fas fa-plus"></i> Create Invoice
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

      {/* Invoice Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content xlarge" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <i className={`fas fa-${modalMode === 'create' ? 'plus' : 'edit'}`}></i>
                {modalMode === 'create' ? 'New Invoice' : 'Edit Invoice'}
              </h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              {/* Invoice Header */}
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
                    <label>Reference Number</label>
                    <input
                      type="text"
                      value={formData.reference_number}
                      onChange={(e) => handleFormChange('reference_number', e.target.value)}
                      placeholder="PO #, etc."
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Invoice Date</label>
                    <input
                      type="date"
                      value={formData.invoice_date}
                      onChange={(e) => handleFormChange('invoice_date', e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label>Due Date</label>
                    <input
                      type="date"
                      value={formData.due_date}
                      onChange={(e) => handleFormChange('due_date', e.target.value)}
                    />
                  </div>
                </div>
              </div>

              {/* Line Items */}
              <div className="form-section">
                <div className="section-header">
                  <h3>Line Items</h3>
                  <button type="button" className="link-btn" onClick={addLine}>
                    <i className="fas fa-plus"></i> Add Line
                  </button>
                </div>

                <div className="lines-table">
                  <div className="lines-header-row">
                    <div className="line-cell account">Account</div>
                    <div className="line-cell desc">Description</div>
                    <div className="line-cell qty">Qty</div>
                    <div className="line-cell price">Price</div>
                    <div className="line-cell amount">Amount</div>
                    <div className="line-cell action"></div>
                  </div>

                  {formData.lines.map((line, index) => (
                    <div key={index} className="line-row">
                      <div className="line-cell account">
                        <select
                          value={line.account_id}
                          onChange={(e) => handleLineChange(index, 'account_id', e.target.value)}
                        >
                          <option value="">Select Account</option>
                          {accounts.map(a => (
                            <option key={a.id} value={a.id}>{a.account_number} - {a.name}</option>
                          ))}
                        </select>
                      </div>
                      <div className="line-cell desc">
                        <input
                          type="text"
                          value={line.description}
                          onChange={(e) => handleLineChange(index, 'description', e.target.value)}
                          placeholder="Description"
                        />
                      </div>
                      <div className="line-cell qty">
                        <input
                          type="number"
                          min="1"
                          value={line.quantity}
                          onChange={(e) => handleLineChange(index, 'quantity', e.target.value)}
                        />
                      </div>
                      <div className="line-cell price">
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={line.unit_price}
                          onChange={(e) => handleLineChange(index, 'unit_price', e.target.value)}
                          placeholder="0.00"
                        />
                      </div>
                      <div className="line-cell amount">
                        <span className="amount-display">{formatCurrency(calculateLineAmount(line))}</span>
                      </div>
                      <div className="line-cell action">
                        <button
                          className="remove-line-btn"
                          onClick={() => removeLine(index)}
                          disabled={formData.lines.length <= 1}
                        >
                          <i className="fas fa-times"></i>
                        </button>
                      </div>
                    </div>
                  ))}

                  <div className="totals-row">
                    <div className="line-cell account"></div>
                    <div className="line-cell desc"></div>
                    <div className="line-cell qty"></div>
                    <div className="line-cell price"><strong>Total:</strong></div>
                    <div className="line-cell amount">
                      <strong>{formatCurrency(total)}</strong>
                    </div>
                    <div className="line-cell action"></div>
                  </div>
                </div>
              </div>

              {/* Notes & Terms */}
              <div className="form-section">
                <div className="form-row">
                  <div className="form-group">
                    <label>Notes to Customer</label>
                    <textarea
                      value={formData.notes}
                      onChange={(e) => handleFormChange('notes', e.target.value)}
                      placeholder="Notes that will appear on the invoice..."
                      rows={3}
                    />
                  </div>
                  <div className="form-group">
                    <label>Terms & Conditions</label>
                    <textarea
                      value={formData.terms}
                      onChange={(e) => handleFormChange('terms', e.target.value)}
                      placeholder="Payment terms, late fees, etc."
                      rows={3}
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="btn-secondary"
                onClick={() => handleSave(true)}
                disabled={saving}
              >
                {saving ? <i className="fas fa-spinner fa-spin"></i> : <i className="fas fa-save"></i>}
                {' '}Save as Draft
              </button>
              <button
                className="btn-primary"
                onClick={() => handleSave(false)}
                disabled={saving}
              >
                {saving ? <i className="fas fa-spinner fa-spin"></i> : <i className="fas fa-paper-plane"></i>}
                {' '}Save & Send
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default InvoiceList;
