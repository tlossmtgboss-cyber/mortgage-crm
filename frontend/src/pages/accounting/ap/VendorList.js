import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function VendorList() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [vendors, setVendors] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 25, total: 0 });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [vendorTypeFilter, setVendorTypeFilter] = useState('all');

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState('create');
  const [selectedVendor, setSelectedVendor] = useState(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    company_name: '',
    email: '',
    phone: '',
    address: '',
    city: '',
    state: '',
    zip: '',
    vendor_type: 'supplier',
    payment_terms: 'net_30',
    tax_id: '',
    is_1099_vendor: false,
    default_expense_account_id: '',
    notes: '',
    is_active: true,
  });

  const vendorTypes = [
    { value: 'supplier', label: 'Supplier' },
    { value: 'contractor', label: 'Contractor' },
    { value: 'service_provider', label: 'Service Provider' },
    { value: 'utility', label: 'Utility' },
    { value: 'government', label: 'Government' },
    { value: 'other', label: 'Other' },
  ];

  const paymentTermsOptions = [
    { value: 'due_on_receipt', label: 'Due on Receipt' },
    { value: 'net_15', label: 'Net 15' },
    { value: 'net_30', label: 'Net 30' },
    { value: 'net_45', label: 'Net 45' },
    { value: 'net_60', label: 'Net 60' },
    { value: 'net_90', label: 'Net 90' },
  ];

  // Fetch vendors
  const fetchVendors = useCallback(async () => {
    try {
      const params = {
        page: pagination.page,
        limit: pagination.limit,
        is_active: statusFilter === 'active' ? true : statusFilter === 'inactive' ? false : undefined,
      };
      if (searchTerm) params.search = searchTerm;
      if (vendorTypeFilter !== 'all') params.vendor_type = vendorTypeFilter;

      const data = await accountingAPI.getAPVendors(params);
      setVendors(data?.vendors || []);
      setPagination(prev => ({ ...prev, total: data?.total || 0 }));
      setLoading(false);
    } catch (err) {
      console.error('Error fetching vendors:', err);
      setLoading(false);
    }
  }, [pagination.page, pagination.limit, statusFilter, searchTerm, vendorTypeFilter]);

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

  // Open create modal
  const openCreateModal = () => {
    setModalMode('create');
    setSelectedVendor(null);
    setFormData({
      name: '',
      company_name: '',
      email: '',
      phone: '',
      address: '',
      city: '',
      state: '',
      zip: '',
      vendor_type: 'supplier',
      payment_terms: 'net_30',
      tax_id: '',
      is_1099_vendor: false,
      default_expense_account_id: '',
      notes: '',
      is_active: true,
    });
    setShowModal(true);
  };

  // Open edit modal
  const openEditModal = (vendor) => {
    setModalMode('edit');
    setSelectedVendor(vendor);
    setFormData({
      name: vendor.name || '',
      company_name: vendor.company_name || '',
      email: vendor.email || '',
      phone: vendor.phone || '',
      address: vendor.address || '',
      city: vendor.city || '',
      state: vendor.state || '',
      zip: vendor.zip || '',
      vendor_type: vendor.vendor_type || 'supplier',
      payment_terms: vendor.payment_terms || 'net_30',
      tax_id: vendor.tax_id || '',
      is_1099_vendor: vendor.is_1099_vendor || false,
      default_expense_account_id: vendor.default_expense_account_id || '',
      notes: vendor.notes || '',
      is_active: vendor.is_active !== false,
    });
    setShowModal(true);
  };

  // Handle form change
  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Save vendor
  const handleSave = async () => {
    if (!formData.name) {
      toast.error('Please enter a vendor name.');
      return;
    }

    try {
      setSaving(true);

      if (modalMode === 'create') {
        await accountingAPI.createAPVendor(formData);
      } else {
        await accountingAPI.updateAPVendor(selectedVendor.id, formData);
      }

      setShowModal(false);
      fetchVendors();
    } catch (err) {
      console.error('Error saving vendor:', err);
      toast.error(err.response?.data?.detail || 'Failed to save vendor.');
    } finally {
      setSaving(false);
    }
  };

  const totalPages = Math.ceil(pagination.total / pagination.limit);

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Vendors...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Vendors.</p>
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
            <h1><i className="fas fa-truck"></i> Vendors</h1>
            <p className="subtitle">{pagination.total} vendors</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={openCreateModal}>
            <i className="fas fa-plus"></i> New Vendor
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
              placeholder="Search vendors..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className="clear-btn" onClick={() => setSearchTerm('')}>
                <i className="fas fa-times"></i>
              </button>
            )}
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>

          <select
            value={vendorTypeFilter}
            onChange={(e) => setVendorTypeFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Types</option>
            {vendorTypes.map(type => (
              <option key={type.value} value={type.value}>{type.label}</option>
            ))}
          </select>
        </div>

        <div className="toolbar-right">
          <button className="toolbar-btn" onClick={fetchVendors} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards four-col">
        <div className="summary-card">
          <div className="summary-icon blue">
            <i className="fas fa-truck"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">{vendors.length}</span>
            <span className="summary-label">Total Vendors</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon green">
            <i className="fas fa-file-invoice"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(vendors.reduce((sum, v) => sum + (v.total_billed || 0), 0))}
            </span>
            <span className="summary-label">Total Billed</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon orange">
            <i className="fas fa-clock"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(vendors.reduce((sum, v) => sum + (v.outstanding_balance || 0), 0))}
            </span>
            <span className="summary-label">Outstanding</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon purple">
            <i className="fas fa-file-alt"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {vendors.filter(v => v.is_1099_vendor).length}
            </span>
            <span className="summary-label">1099 Vendors</span>
          </div>
        </div>
      </div>

      {/* Vendors Table */}
      <div className="data-table">
        <div className="table-header" style={{ gridTemplateColumns: '1fr 150px 120px 120px 120px 100px 140px' }}>
          <div className="header-cell">Vendor</div>
          <div className="header-cell">Type</div>
          <div className="header-cell">Terms</div>
          <div className="header-cell amount">Total Billed</div>
          <div className="header-cell amount">Outstanding</div>
          <div className="header-cell">1099</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {vendors.length > 0 ? (
            vendors.map(vendor => (
              <div
                key={vendor.id}
                className={`table-row ${!vendor.is_active ? 'inactive' : ''}`}
                style={{ gridTemplateColumns: '1fr 150px 120px 120px 120px 100px 140px' }}
              >
                <div className="cell">
                  <div className="customer-info">
                    <span className="customer-name">{vendor.name}</span>
                    {vendor.company_name && (
                      <span className="company-name">{vendor.company_name}</span>
                    )}
                    {vendor.email && <span className="email">{vendor.email}</span>}
                  </div>
                </div>
                <div className="cell">
                  <span className="type-badge">
                    {vendorTypes.find(t => t.value === vendor.vendor_type)?.label || vendor.vendor_type}
                  </span>
                </div>
                <div className="cell">
                  <span className="terms-badge">
                    {paymentTermsOptions.find(t => t.value === vendor.payment_terms)?.label || vendor.payment_terms}
                  </span>
                </div>
                <div className="cell amount">{formatCurrency(vendor.total_billed)}</div>
                <div className="cell amount">{formatCurrency(vendor.outstanding_balance)}</div>
                <div className="cell">
                  {vendor.is_1099_vendor && (
                    <span className="badge-1099">
                      <i className="fas fa-check"></i> 1099
                    </span>
                  )}
                </div>
                <div className="cell actions">
                  <button
                    className="action-btn"
                    onClick={() => navigate(`/accounting/ap/vendors/${vendor.id}`)}
                    title="View"
                  >
                    <i className="fas fa-eye"></i>
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => openEditModal(vendor)}
                    title="Edit"
                  >
                    <i className="fas fa-edit"></i>
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => navigate(`/accounting/ap/bills/new?vendor=${vendor.id}`)}
                    title="Create Bill"
                  >
                    <i className="fas fa-file-invoice"></i>
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-truck"></i>
              <h3>No Vendors Found</h3>
              <p>Add vendors to track your payables.</p>
              <button className="btn-primary" onClick={openCreateModal}>
                <i className="fas fa-plus"></i> Add Vendor
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

      {/* Vendor Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <i className={`fas fa-${modalMode === 'create' ? 'plus' : 'edit'}`}></i>
                {modalMode === 'create' ? 'New Vendor' : 'Edit Vendor'}
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
                    <label>Vendor Name <span className="required">*</span></label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => handleFormChange('name', e.target.value)}
                      placeholder="Contact or display name"
                    />
                  </div>
                  <div className="form-group">
                    <label>Company Name</label>
                    <input
                      type="text"
                      value={formData.company_name}
                      onChange={(e) => handleFormChange('company_name', e.target.value)}
                      placeholder="Legal company name"
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
                      placeholder="vendor@example.com"
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

                <div className="form-row">
                  <div className="form-group">
                    <label>Vendor Type</label>
                    <select
                      value={formData.vendor_type}
                      onChange={(e) => handleFormChange('vendor_type', e.target.value)}
                    >
                      {vendorTypes.map(type => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                  </div>
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
                </div>
              </div>

              {/* Address */}
              <div className="form-section">
                <h3>Address</h3>
                <div className="form-group">
                  <label>Street Address</label>
                  <input
                    type="text"
                    value={formData.address}
                    onChange={(e) => handleFormChange('address', e.target.value)}
                    placeholder="Street address"
                  />
                </div>
                <div className="form-row three-col">
                  <div className="form-group">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.city}
                      onChange={(e) => handleFormChange('city', e.target.value)}
                      placeholder="City"
                    />
                  </div>
                  <div className="form-group">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.state}
                      onChange={(e) => handleFormChange('state', e.target.value)}
                      placeholder="State"
                    />
                  </div>
                  <div className="form-group">
                    <label>ZIP Code</label>
                    <input
                      type="text"
                      value={formData.zip}
                      onChange={(e) => handleFormChange('zip', e.target.value)}
                      placeholder="ZIP"
                    />
                  </div>
                </div>
              </div>

              {/* Tax Info */}
              <div className="form-section">
                <h3>Tax Information</h3>
                <div className="form-row">
                  <div className="form-group">
                    <label>Tax ID / EIN</label>
                    <input
                      type="text"
                      value={formData.tax_id}
                      onChange={(e) => handleFormChange('tax_id', e.target.value)}
                      placeholder="XX-XXXXXXX"
                    />
                  </div>
                  <div className="form-group checkbox-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={formData.is_1099_vendor}
                        onChange={(e) => handleFormChange('is_1099_vendor', e.target.checked)}
                      />
                      1099 Vendor (Track for tax reporting)
                    </label>
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
                  Active Vendor
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
                  <><i className="fas fa-check"></i> {modalMode === 'create' ? 'Create Vendor' : 'Save Changes'}</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default VendorList;
