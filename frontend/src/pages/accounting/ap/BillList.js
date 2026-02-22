import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function BillList() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [bills, setBills] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editingBill, setEditingBill] = useState(null);
  const [summary, setSummary] = useState({
    total_bills: 0,
    total_amount: 0,
    outstanding: 0,
    overdue: 0,
  });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [vendorFilter, setVendorFilter] = useState('');
  const [dateRange, setDateRange] = useState({ start: '', end: '' });

  // Form state
  const [formData, setFormData] = useState({
    vendor_id: '',
    bill_number: '',
    bill_date: new Date().toISOString().split('T')[0],
    due_date: '',
    reference: '',
    memo: '',
    lines: [{ account_id: '', description: '', quantity: 1, unit_price: 0, amount: 0 }],
  });

  // Fetch bills
  const fetchBills = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (searchTerm) params.search = searchTerm;
      if (statusFilter) params.status = statusFilter;
      if (vendorFilter) params.vendor_id = vendorFilter;
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end) params.end_date = dateRange.end;

      const data = await accountingAPI.getAPBills(params);
      setBills(data?.bills || []);
      setSummary(data?.summary || {
        total_bills: 0,
        total_amount: 0,
        outstanding: 0,
        overdue: 0,
      });
      setLoading(false);
    } catch (err) {
      console.error('Error fetching bills:', err);
      setLoading(false);
    }
  }, [searchTerm, statusFilter, vendorFilter, dateRange]);

  // Fetch vendors for dropdown
  const fetchVendors = useCallback(async () => {
    try {
      const data = await accountingAPI.getAPVendors({ is_active: true });
      setVendors(data?.vendors || []);
    } catch (err) {
      console.error('Error fetching vendors:', err);
    }
  }, []);

  // Fetch accounts for dropdown
  const fetchAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getChartOfAccounts({ type: 'expense' });
      setAccounts(data?.accounts || []);
    } catch (err) {
      console.error('Error fetching accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchBills();
  }, [fetchBills]);

  useEffect(() => {
    fetchVendors();
    fetchAccounts();
  }, [fetchVendors, fetchAccounts]);

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

  // Calculate due date from vendor payment terms
  const calculateDueDate = (billDate, vendorId) => {
    const vendor = vendors.find(v => v.id === vendorId);
    if (!vendor || !billDate) return '';

    const termDays = {
      'due_on_receipt': 0,
      'net_15': 15,
      'net_30': 30,
      'net_45': 45,
      'net_60': 60,
      'net_90': 90,
    };

    const days = termDays[vendor.payment_terms] || 30;
    const due = new Date(billDate);
    due.setDate(due.getDate() + days);
    return due.toISOString().split('T')[0];
  };

  // Handle vendor change
  const handleVendorChange = (vendorId) => {
    const dueDate = calculateDueDate(formData.bill_date, vendorId);
    setFormData(prev => ({
      ...prev,
      vendor_id: vendorId,
      due_date: dueDate,
    }));
  };

  // Handle bill date change
  const handleBillDateChange = (date) => {
    const dueDate = calculateDueDate(date, formData.vendor_id);
    setFormData(prev => ({
      ...prev,
      bill_date: date,
      due_date: dueDate,
    }));
  };

  // Handle line change
  const handleLineChange = (index, field, value) => {
    setFormData(prev => {
      const newLines = [...prev.lines];
      newLines[index] = { ...newLines[index], [field]: value };

      // Auto-calculate amount
      if (field === 'quantity' || field === 'unit_price') {
        const qty = field === 'quantity' ? parseFloat(value) || 0 : parseFloat(newLines[index].quantity) || 0;
        const price = field === 'unit_price' ? parseFloat(value) || 0 : parseFloat(newLines[index].unit_price) || 0;
        newLines[index].amount = qty * price;
      }

      return { ...prev, lines: newLines };
    });
  };

  // Add line
  const addLine = () => {
    setFormData(prev => ({
      ...prev,
      lines: [...prev.lines, { account_id: '', description: '', quantity: 1, unit_price: 0, amount: 0 }],
    }));
  };

  // Remove line
  const removeLine = (index) => {
    if (formData.lines.length <= 1) return;
    setFormData(prev => ({
      ...prev,
      lines: prev.lines.filter((_, i) => i !== index),
    }));
  };

  // Calculate total
  const calculateTotal = () => {
    return formData.lines.reduce((sum, line) => sum + (parseFloat(line.amount) || 0), 0);
  };

  // Open modal for create/edit
  const openModal = (bill = null) => {
    if (bill) {
      setEditingBill(bill);
      setFormData({
        vendor_id: bill.vendor_id || '',
        bill_number: bill.bill_number || '',
        bill_date: bill.bill_date?.split('T')[0] || '',
        due_date: bill.due_date?.split('T')[0] || '',
        reference: bill.reference || '',
        memo: bill.memo || '',
        lines: bill.lines?.length > 0 ? bill.lines : [{ account_id: '', description: '', quantity: 1, unit_price: 0, amount: 0 }],
      });
    } else {
      setEditingBill(null);
      setFormData({
        vendor_id: '',
        bill_number: '',
        bill_date: new Date().toISOString().split('T')[0],
        due_date: '',
        reference: '',
        memo: '',
        lines: [{ account_id: '', description: '', quantity: 1, unit_price: 0, amount: 0 }],
      });
    }
    setShowModal(true);
  };

  // Close modal
  const closeModal = () => {
    setShowModal(false);
    setEditingBill(null);
  };

  // Handle save
  const handleSave = async (status = 'draft') => {
    try {
      const payload = {
        ...formData,
        status,
        total_amount: calculateTotal(),
      };

      if (editingBill) {
        await accountingAPI.updateAPBill(editingBill.id, payload);
      } else {
        await accountingAPI.createAPBill(payload);
      }

      closeModal();
      fetchBills();
    } catch (err) {
      console.error('Error saving bill:', err);
      toast.error('Failed to save bill');
    }
  };

  // Handle approve
  const handleApprove = async (bill) => {
    if (!window.confirm('Are you sure you want to approve this bill?')) return;
    try {
      await accountingAPI.approveAPBill(bill.id);
      fetchBills();
    } catch (err) {
      console.error('Error approving bill:', err);
      toast.error('Failed to approve bill');
    }
  };

  // Handle void
  const handleVoid = async (bill) => {
    if (!window.confirm('Are you sure you want to void this bill?')) return;
    try {
      await accountingAPI.voidAPBill(bill.id);
      fetchBills();
    } catch (err) {
      console.error('Error voiding bill:', err);
      toast.error('Failed to void bill');
    }
  };

  // Get status badge class
  const getStatusBadge = (status) => {
    const badges = {
      draft: 'badge-draft',
      pending_approval: 'badge-pending',
      approved: 'badge-success',
      partial: 'badge-warning',
      paid: 'badge-info',
      voided: 'badge-error',
    };
    return badges[status] || 'badge-default';
  };

  // Check if bill is overdue
  const isOverdue = (bill) => {
    if (!bill.due_date || bill.status === 'paid' || bill.status === 'voided') return false;
    return new Date(bill.due_date) < new Date();
  };

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Bills...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page bill-list">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Bills.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page bill-list">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-file-invoice-dollar"></i> Bills</h1>
            <p className="subtitle">Manage vendor bills and payments</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={() => openModal()}>
            <i className="fas fa-plus"></i> New Bill
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-file-invoice"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{summary.total_bills}</span>
            <span className="summary-label">Total Bills</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon">
            <i className="fas fa-dollar-sign"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{formatCurrency(summary.total_amount)}</span>
            <span className="summary-label">Total Amount</span>
          </div>
        </div>
        <div className="summary-card warning">
          <div className="summary-icon">
            <i className="fas fa-clock"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{formatCurrency(summary.outstanding)}</span>
            <span className="summary-label">Outstanding</span>
          </div>
        </div>
        <div className="summary-card danger">
          <div className="summary-icon">
            <i className="fas fa-exclamation-triangle"></i>
          </div>
          <div className="summary-content">
            <span className="summary-value">{formatCurrency(summary.overdue)}</span>
            <span className="summary-label">Overdue</span>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar">
        <div className="toolbar-left">
          <div className="search-box">
            <i className="fas fa-search"></i>
            <input
              type="text"
              placeholder="Search bills..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="approved">Approved</option>
            <option value="partial">Partially Paid</option>
            <option value="paid">Paid</option>
            <option value="voided">Voided</option>
          </select>

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
          <button className="toolbar-btn" onClick={fetchBills} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Bills Table */}
      <div className="data-table">
        <div className="table-header">
          <div className="header-cell">Bill #</div>
          <div className="header-cell">Vendor</div>
          <div className="header-cell">Date</div>
          <div className="header-cell">Due Date</div>
          <div className="header-cell">Amount</div>
          <div className="header-cell">Balance</div>
          <div className="header-cell">Status</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {bills.length > 0 ? (
            bills.map(bill => (
              <div key={bill.id} className={`table-row ${isOverdue(bill) ? 'overdue' : ''}`}>
                <div className="cell">
                  <span className="bill-number">{bill.bill_number}</span>
                  {bill.reference && <span className="reference">Ref: {bill.reference}</span>}
                </div>
                <div className="cell">{bill.vendor_name}</div>
                <div className="cell">{formatDate(bill.bill_date)}</div>
                <div className="cell">
                  {formatDate(bill.due_date)}
                  {isOverdue(bill) && <span className="overdue-badge">Overdue</span>}
                </div>
                <div className="cell amount">{formatCurrency(bill.total_amount)}</div>
                <div className="cell amount">{formatCurrency(bill.balance_due)}</div>
                <div className="cell">
                  <span className={`status-badge ${getStatusBadge(bill.status)}`}>
                    {bill.status?.replace('_', ' ')}
                  </span>
                </div>
                <div className="cell actions">
                  <button
                    className="action-btn"
                    onClick={() => openModal(bill)}
                    title="Edit"
                    disabled={bill.status === 'voided'}
                  >
                    <i className="fas fa-edit"></i>
                  </button>
                  {bill.status === 'pending_approval' && (
                    <button
                      className="action-btn success"
                      onClick={() => handleApprove(bill)}
                      title="Approve"
                    >
                      <i className="fas fa-check"></i>
                    </button>
                  )}
                  {bill.status !== 'voided' && bill.status !== 'paid' && (
                    <button
                      className="action-btn danger"
                      onClick={() => handleVoid(bill)}
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
              <h3>No Bills Found</h3>
              <p>Create your first bill to get started.</p>
              <button className="btn-primary" onClick={() => openModal()}>
                <i className="fas fa-plus"></i> New Bill
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Bill Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content large" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingBill ? 'Edit Bill' : 'New Bill'}</h2>
              <button className="close-btn" onClick={closeModal}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              <div className="form-row">
                <div className="form-group">
                  <label>Vendor *</label>
                  <select
                    value={formData.vendor_id}
                    onChange={(e) => handleVendorChange(e.target.value)}
                    required
                  >
                    <option value="">Select Vendor</option>
                    {vendors.map(v => (
                      <option key={v.id} value={v.id}>{v.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Bill Number *</label>
                  <input
                    type="text"
                    value={formData.bill_number}
                    onChange={(e) => setFormData(prev => ({ ...prev, bill_number: e.target.value }))}
                    placeholder="BILL-0001"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Bill Date *</label>
                  <input
                    type="date"
                    value={formData.bill_date}
                    onChange={(e) => handleBillDateChange(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Due Date</label>
                  <input
                    type="date"
                    value={formData.due_date}
                    onChange={(e) => setFormData(prev => ({ ...prev, due_date: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>Reference</label>
                  <input
                    type="text"
                    value={formData.reference}
                    onChange={(e) => setFormData(prev => ({ ...prev, reference: e.target.value }))}
                    placeholder="PO# or Invoice#"
                  />
                </div>
              </div>

              {/* Line Items */}
              <div className="line-items-section">
                <h3>Line Items</h3>
                <div className="line-items-table">
                  <div className="line-header">
                    <div className="line-cell account">Account</div>
                    <div className="line-cell description">Description</div>
                    <div className="line-cell qty">Qty</div>
                    <div className="line-cell price">Unit Price</div>
                    <div className="line-cell amount">Amount</div>
                    <div className="line-cell actions"></div>
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
                      <div className="line-cell description">
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
                          value={line.quantity}
                          onChange={(e) => handleLineChange(index, 'quantity', e.target.value)}
                          min="1"
                        />
                      </div>
                      <div className="line-cell price">
                        <input
                          type="number"
                          value={line.unit_price}
                          onChange={(e) => handleLineChange(index, 'unit_price', e.target.value)}
                          step="0.01"
                          min="0"
                        />
                      </div>
                      <div className="line-cell amount">
                        {formatCurrency(line.amount)}
                      </div>
                      <div className="line-cell actions">
                        <button
                          type="button"
                          className="remove-line-btn"
                          onClick={() => removeLine(index)}
                          disabled={formData.lines.length <= 1}
                        >
                          <i className="fas fa-trash"></i>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                <button type="button" className="add-line-btn" onClick={addLine}>
                  <i className="fas fa-plus"></i> Add Line
                </button>
              </div>

              <div className="form-group">
                <label>Memo</label>
                <textarea
                  value={formData.memo}
                  onChange={(e) => setFormData(prev => ({ ...prev, memo: e.target.value }))}
                  placeholder="Internal notes..."
                  rows="2"
                />
              </div>

              {/* Total */}
              <div className="bill-total">
                <span className="total-label">Total:</span>
                <span className="total-amount">{formatCurrency(calculateTotal())}</span>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={closeModal}>
                Cancel
              </button>
              <button className="btn-secondary" onClick={() => handleSave('draft')}>
                Save as Draft
              </button>
              <button className="btn-primary" onClick={() => handleSave('pending_approval')}>
                Submit for Approval
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BillList;
