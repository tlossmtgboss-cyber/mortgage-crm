import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function CustomerList() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 25, total: 0 });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState('create');
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    company_name: '',
    email: '',
    phone: '',
    billing_address: '',
    billing_city: '',
    billing_state: '',
    billing_zip: '',
    shipping_address: '',
    shipping_city: '',
    shipping_state: '',
    shipping_zip: '',
    payment_terms: 'net_30',
    credit_limit: '',
    tax_id: '',
    notes: '',
    is_active: true,
  });

  const paymentTermsOptions = [
    { value: 'due_on_receipt', label: 'Due on Receipt' },
    { value: 'net_15', label: 'Net 15' },
    { value: 'net_30', label: 'Net 30' },
    { value: 'net_45', label: 'Net 45' },
    { value: 'net_60', label: 'Net 60' },
    { value: 'net_90', label: 'Net 90' },
  ];

  // Fetch customers
  const fetchCustomers = useCallback(async () => {
    try {
      setError(null);
      const params = {
        page: pagination.page,
        limit: pagination.limit,
        is_active: statusFilter === 'active' ? true : statusFilter === 'inactive' ? false : undefined,
      };
      if (searchTerm) {
        params.search = searchTerm;
      }

      const data = await accountingAPI.getARCustomers(params);
      setCustomers(data?.customers || []);
      setPagination(prev => ({ ...prev, total: data?.total || 0 }));
      setLoading(false);
    } catch (err) {
      console.error('Error fetching customers:', err);
      setError('Failed to load customers. Please try again.');
      setLoading(false);
    }
  }, [pagination.page, pagination.limit, statusFilter, searchTerm]);

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

  // Open create modal
  const openCreateModal = () => {
    setModalMode('create');
    setSelectedCustomer(null);
    setFormData({
      name: '',
      company_name: '',
      email: '',
      phone: '',
      billing_address: '',
      billing_city: '',
      billing_state: '',
      billing_zip: '',
      shipping_address: '',
      shipping_city: '',
      shipping_state: '',
      shipping_zip: '',
      payment_terms: 'net_30',
      credit_limit: '',
      tax_id: '',
      notes: '',
      is_active: true,
    });
    setShowModal(true);
  };

  // Open edit modal
  const openEditModal = async (customer) => {
    setModalMode('edit');
    setSelectedCustomer(customer);
    setFormData({
      name: customer.name || '',
      company_name: customer.company_name || '',
      email: customer.email || '',
      phone: customer.phone || '',
      billing_address: customer.billing_address || '',
      billing_city: customer.billing_city || '',
      billing_state: customer.billing_state || '',
      billing_zip: customer.billing_zip || '',
      shipping_address: customer.shipping_address || '',
      shipping_city: customer.shipping_city || '',
      shipping_state: customer.shipping_state || '',
      shipping_zip: customer.shipping_zip || '',
      payment_terms: customer.payment_terms || 'net_30',
      credit_limit: customer.credit_limit || '',
      tax_id: customer.tax_id || '',
      notes: customer.notes || '',
      is_active: customer.is_active !== false,
    });
    setShowModal(true);
  };

  // Handle form change
  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Copy billing to shipping
  const copyBillingToShipping = () => {
    setFormData(prev => ({
      ...prev,
      shipping_address: prev.billing_address,
      shipping_city: prev.billing_city,
      shipping_state: prev.billing_state,
      shipping_zip: prev.billing_zip,
    }));
  };

  // Save customer
  const handleSave = async () => {
    if (!formData.name) {
      toast.error('Please enter a customer name.');
      return;
    }

    try {
      setSaving(true);

      const data = {
        ...formData,
        credit_limit: formData.credit_limit ? parseFloat(formData.credit_limit) : null,
      };

      if (modalMode === 'create') {
        await accountingAPI.createARCustomer(data);
      } else {
        await accountingAPI.updateARCustomer(selectedCustomer.id, data);
      }

      setShowModal(false);
      fetchCustomers();
    } catch (err) {
      console.error('Error saving customer:', err);
      toast.error(err.response?.data?.detail || 'Failed to save customer. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Pagination
  const totalPages = Math.ceil(pagination.total / pagination.limit);

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Customers...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Customers.</p>
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
            <h1><i className="fas fa-users"></i> Customers</h1>
            <p className="subtitle">{pagination.total} customers</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={openCreateModal}>
            <i className="fas fa-plus"></i> New Customer
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
              placeholder="Search customers..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className="clear-btn" onClick={() => setSearchTerm('')}>
                <i className="fas fa-times"></i>
              </button>
            )}
          </div>

          <div className="filter-group">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="filter-select"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>

        <div className="toolbar-right">
          <button className="toolbar-btn" onClick={fetchCustomers} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards four-col">
        <div className="summary-card">
          <div className="summary-icon blue">
            <i className="fas fa-users"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">{customers.length}</span>
            <span className="summary-label">Total Customers</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon green">
            <i className="fas fa-file-invoice-dollar"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(customers.reduce((sum, c) => sum + (c.total_invoiced || 0), 0))}
            </span>
            <span className="summary-label">Total Invoiced</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon orange">
            <i className="fas fa-clock"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(customers.reduce((sum, c) => sum + (c.outstanding_balance || 0), 0))}
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
              {formatCurrency(customers.reduce((sum, c) => sum + (c.overdue_amount || 0), 0))}
            </span>
            <span className="summary-label">Overdue</span>
          </div>
        </div>
      </div>

      {/* Customers Table */}
      <div className="data-table">
        <div className="table-header">
          <div className="header-cell name">Customer</div>
          <div className="header-cell contact">Contact</div>
          <div className="header-cell terms">Terms</div>
          <div className="header-cell amount">Invoiced</div>
          <div className="header-cell amount">Outstanding</div>
          <div className="header-cell amount">Overdue</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {customers.length > 0 ? (
            customers.map(customer => (
              <div key={customer.id} className={`table-row ${!customer.is_active ? 'inactive' : ''}`}>
                <div className="cell name">
                  <div className="customer-info">
                    <span className="customer-name">{customer.name}</span>
                    {customer.company_name && (
                      <span className="company-name">{customer.company_name}</span>
                    )}
                  </div>
                </div>
                <div className="cell contact">
                  <div className="contact-info">
                    {customer.email && <span className="email">{customer.email}</span>}
                    {customer.phone && <span className="phone">{customer.phone}</span>}
                  </div>
                </div>
                <div className="cell terms">
                  <span className="terms-badge">
                    {paymentTermsOptions.find(t => t.value === customer.payment_terms)?.label || customer.payment_terms}
                  </span>
                </div>
                <div className="cell amount">{formatCurrency(customer.total_invoiced)}</div>
                <div className="cell amount">{formatCurrency(customer.outstanding_balance)}</div>
                <div className="cell amount overdue">
                  {customer.overdue_amount > 0 ? formatCurrency(customer.overdue_amount) : '-'}
                </div>
                <div className="cell actions">
                  <button
                    className="action-btn"
                    onClick={() => navigate(`/accounting/ar/customers/${customer.id}`)}
                    title="View Details"
                  >
                    <i className="fas fa-eye"></i>
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => openEditModal(customer)}
                    title="Edit"
                  >
                    <i className="fas fa-edit"></i>
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => navigate(`/accounting/ar/invoices/new?customer=${customer.id}`)}
                    title="Create Invoice"
                  >
                    <i className="fas fa-file-invoice"></i>
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-users"></i>
              <h3>No Customers Found</h3>
              <p>
                {searchTerm || statusFilter !== 'all'
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Get started by adding your first customer.'}
              </p>
              {!searchTerm && statusFilter === 'all' && (
                <button className="btn-primary" onClick={openCreateModal}>
                  <i className="fas fa-plus"></i> Add Customer
                </button>
              )}
            </div>
          )}
        </div>

        {/* Pagination */}
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

      {/* Customer Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <i className={`fas fa-${modalMode === 'create' ? 'plus' : 'edit'}`}></i>
                {modalMode === 'create' ? 'New Customer' : 'Edit Customer'}
              </h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              {/* Basic Info */}
              <div className="form-section">
                <h3>Basic Information</h3>
                <div className="form-row">
                  <div className="form-group">
                    <label>Customer Name <span className="required">*</span></label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => handleFormChange('name', e.target.value)}
                      placeholder="Contact name"
                    />
                  </div>
                  <div className="form-group">
                    <label>Company Name</label>
                    <input
                      type="text"
                      value={formData.company_name}
                      onChange={(e) => handleFormChange('company_name', e.target.value)}
                      placeholder="Company name"
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Email</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={(e) => handleFormChange('email', e.target.value)}
                      placeholder="email@example.com"
                    />
                  </div>
                  <div className="form-group">
                    <label>Phone</label>
                    <input
                      type="tel"
                      value={formData.phone}
                      onChange={(e) => handleFormChange('phone', e.target.value)}
                      placeholder="(555) 555-5555"
                    />
                  </div>
                </div>
              </div>

              {/* Billing Address */}
              <div className="form-section">
                <h3>Billing Address</h3>
                <div className="form-group">
                  <label>Street Address</label>
                  <input
                    type="text"
                    value={formData.billing_address}
                    onChange={(e) => handleFormChange('billing_address', e.target.value)}
                    placeholder="Street address"
                  />
                </div>
                <div className="form-row three-col">
                  <div className="form-group">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.billing_city}
                      onChange={(e) => handleFormChange('billing_city', e.target.value)}
                      placeholder="City"
                    />
                  </div>
                  <div className="form-group">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.billing_state}
                      onChange={(e) => handleFormChange('billing_state', e.target.value)}
                      placeholder="State"
                    />
                  </div>
                  <div className="form-group">
                    <label>ZIP Code</label>
                    <input
                      type="text"
                      value={formData.billing_zip}
                      onChange={(e) => handleFormChange('billing_zip', e.target.value)}
                      placeholder="ZIP"
                    />
                  </div>
                </div>
              </div>

              {/* Shipping Address */}
              <div className="form-section">
                <div className="section-header">
                  <h3>Shipping Address</h3>
                  <button type="button" className="link-btn" onClick={copyBillingToShipping}>
                    <i className="fas fa-copy"></i> Same as Billing
                  </button>
                </div>
                <div className="form-group">
                  <label>Street Address</label>
                  <input
                    type="text"
                    value={formData.shipping_address}
                    onChange={(e) => handleFormChange('shipping_address', e.target.value)}
                    placeholder="Street address"
                  />
                </div>
                <div className="form-row three-col">
                  <div className="form-group">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.shipping_city}
                      onChange={(e) => handleFormChange('shipping_city', e.target.value)}
                      placeholder="City"
                    />
                  </div>
                  <div className="form-group">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.shipping_state}
                      onChange={(e) => handleFormChange('shipping_state', e.target.value)}
                      placeholder="State"
                    />
                  </div>
                  <div className="form-group">
                    <label>ZIP Code</label>
                    <input
                      type="text"
                      value={formData.shipping_zip}
                      onChange={(e) => handleFormChange('shipping_zip', e.target.value)}
                      placeholder="ZIP"
                    />
                  </div>
                </div>
              </div>

              {/* Payment Settings */}
              <div className="form-section">
                <h3>Payment Settings</h3>
                <div className="form-row three-col">
                  <div className="form-group">
                    <label>Payment Terms</label>
                    <select
                      value={formData.payment_terms}
                      onChange={(e) => handleFormChange('payment_terms', e.target.value)}
                    >
                      {paymentTermsOptions.map(term => (
                        <option key={term.value} value={term.value}>{term.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Credit Limit</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.credit_limit}
                      onChange={(e) => handleFormChange('credit_limit', e.target.value)}
                      placeholder="0.00"
                    />
                  </div>
                  <div className="form-group">
                    <label>Tax ID / EIN</label>
                    <input
                      type="text"
                      value={formData.tax_id}
                      onChange={(e) => handleFormChange('tax_id', e.target.value)}
                      placeholder="XX-XXXXXXX"
                    />
                  </div>
                </div>
              </div>

              {/* Notes */}
              <div className="form-section">
                <div className="form-group">
                  <label>Notes</label>
                  <textarea
                    value={formData.notes}
                    onChange={(e) => handleFormChange('notes', e.target.value)}
                    placeholder="Internal notes..."
                    rows={3}
                  />
                </div>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => handleFormChange('is_active', e.target.checked)}
                  />
                  Active Customer
                </label>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSave}
                disabled={saving || !formData.name}
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving...</>
                ) : (
                  <><i className="fas fa-check"></i> {modalMode === 'create' ? 'Create Customer' : 'Save Changes'}</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CustomerList;
