/**
 * AdminTemplatePackManagement Page
 *
 * Allows admins to manage document template packs for the Perennia Docs system.
 * Template packs define which documents are required for different loan types.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import './AdminTemplatePackManagement.css';
import { getToken } from '../utils/tokenStore';

const AdminTemplatePackManagement = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require admin access
  const canAccessTemplates = isAdmin || hasAnyPermission(['admin.manage', 'templates.manage', 'system.admin']) || userRole === 'admin';

  const [templatePacks, setTemplatePacks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedPack, setSelectedPack] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state for create/edit
  const [formData, setFormData] = useState({
    name: '',
    loan_type: '',
    description: '',
    documents: [],
    is_active: true,
  });

  // Available document types
  const documentTypes = [
    { id: 'paystubs', name: 'Pay Stubs', category: 'income' },
    { id: 'w2', name: 'W-2 Forms', category: 'income' },
    { id: 'tax_returns', name: 'Tax Returns', category: 'income' },
    { id: '1099', name: '1099 Forms', category: 'income' },
    { id: 'profit_loss', name: 'Profit & Loss Statement', category: 'income' },
    { id: 'bank_statements', name: 'Bank Statements', category: 'assets' },
    { id: 'investment_statements', name: 'Investment Statements', category: 'assets' },
    { id: 'gift_letter', name: 'Gift Letter', category: 'assets' },
    { id: 'purchase_contract', name: 'Purchase Contract', category: 'property' },
    { id: 'appraisal', name: 'Appraisal', category: 'property' },
    { id: 'title', name: 'Title Report', category: 'property' },
    { id: 'insurance', name: 'Homeowner Insurance', category: 'property' },
    { id: 'hoa', name: 'HOA Documents', category: 'property' },
    { id: 'drivers_license', name: 'Driver\'s License', category: 'identity' },
    { id: 'ssn_card', name: 'Social Security Card', category: 'identity' },
    { id: 'passport', name: 'Passport', category: 'identity' },
    { id: 'credit_report', name: 'Credit Report', category: 'credit' },
    { id: 'credit_explanation', name: 'Credit Explanation Letter', category: 'credit' },
    { id: 'bankruptcy_docs', name: 'Bankruptcy Documents', category: 'credit' },
    { id: 'va_coe', name: 'VA Certificate of Eligibility', category: 'va' },
    { id: 'dd214', name: 'DD-214', category: 'va' },
  ];

  const loanTypes = [
    { id: 'conventional', name: 'Conventional' },
    { id: 'fha', name: 'FHA' },
    { id: 'va', name: 'VA' },
    { id: 'usda', name: 'USDA' },
    { id: 'jumbo', name: 'Jumbo' },
    { id: 'non_qm', name: 'Non-QM' },
  ];

  // Fetch template packs
  const fetchTemplatePacks = useCallback(async () => {
    try {
      setLoading(true);
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/perennia-docs/template-packs`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch template packs');
      }

      const data = await response.json();
      setTemplatePacks(data.template_packs || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplatePacks();
  }, [fetchTemplatePacks]);

  // Handle form input changes
  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  // Handle document selection
  const handleDocumentToggle = (docId, isRequired = true) => {
    setFormData((prev) => {
      const existing = prev.documents.find((d) => d.document_type === docId);
      if (existing) {
        // Remove if exists
        return {
          ...prev,
          documents: prev.documents.filter((d) => d.document_type !== docId),
        };
      } else {
        // Add new
        return {
          ...prev,
          documents: [...prev.documents, { document_type: docId, is_required: isRequired }],
        };
      }
    });
  };

  // Update document required status
  const handleDocumentRequiredChange = (docId, isRequired) => {
    setFormData((prev) => ({
      ...prev,
      documents: prev.documents.map((d) =>
        d.document_type === docId ? { ...d, is_required: isRequired } : d
      ),
    }));
  };

  // Open create modal
  const handleCreate = () => {
    setFormData({
      name: '',
      loan_type: '',
      description: '',
      documents: [],
      is_active: true,
    });
    setIsEditing(false);
    setShowCreateModal(true);
  };

  // Open edit modal
  const handleEdit = (pack) => {
    setFormData({
      name: pack.name,
      loan_type: pack.loan_type,
      description: pack.description || '',
      documents: pack.documents || [],
      is_active: pack.is_active,
    });
    setSelectedPack(pack);
    setIsEditing(true);
    setShowCreateModal(true);
  };

  // Save template pack
  const handleSave = async () => {
    try {
      setSaving(true);
      const token = getToken();
      const url = isEditing
        ? `${API_BASE_URL}/api/v1/perennia-docs/template-packs/${selectedPack.id}`
        : `${API_BASE_URL}/api/v1/perennia-docs/template-packs`;

      const response = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to save template pack');
      }

      await fetchTemplatePacks();
      setShowCreateModal(false);
      setSelectedPack(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Delete template pack
  const handleDelete = async (packId) => {
    if (!window.confirm('Are you sure you want to delete this template pack?')) {
      return;
    }

    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE_URL}/api/v1/perennia-docs/template-packs/${packId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to delete template pack');
      }

      await fetchTemplatePacks();
    } catch (err) {
      setError(err.message);
    }
  };

  // Duplicate template pack
  const handleDuplicate = async (pack) => {
    setFormData({
      name: `${pack.name} (Copy)`,
      loan_type: pack.loan_type,
      description: pack.description || '',
      documents: pack.documents || [],
      is_active: true,
    });
    setIsEditing(false);
    setShowCreateModal(true);
  };

  // Group documents by category
  const documentsByCategory = documentTypes.reduce((acc, doc) => {
    if (!acc[doc.category]) {
      acc[doc.category] = [];
    }
    acc[doc.category].push(doc);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="admin-template-pack-page">
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading template packs...</p>
        </div>
      </div>
    );
  }

  // Access denied if user doesn't have admin permissions
  if (!canAccessTemplates) {
    return (
      <div className="admin-template-pack-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to manage template packs.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-template-pack-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Document Template Packs</h1>
          <p>Manage document requirements for different loan types</p>
        </div>
        <button className="btn-primary" onClick={handleCreate}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Create Template Pack
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      <div className="template-packs-grid">
        {templatePacks.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <h3>No Template Packs</h3>
            <p>Create your first document template pack to get started.</p>
            <button className="btn-primary" onClick={handleCreate}>
              Create Template Pack
            </button>
          </div>
        ) : (
          templatePacks.map((pack) => (
            <div key={pack.id} className={`template-pack-card ${!pack.is_active ? 'inactive' : ''}`}>
              <div className="pack-header">
                <div className="pack-info">
                  <h3>{pack.name}</h3>
                  <span className={`loan-type-badge ${pack.loan_type}`}>
                    {loanTypes.find((t) => t.id === pack.loan_type)?.name || pack.loan_type}
                  </span>
                </div>
                <div className="pack-status">
                  {pack.is_active ? (
                    <span className="status-badge active">Active</span>
                  ) : (
                    <span className="status-badge inactive">Inactive</span>
                  )}
                </div>
              </div>

              {pack.description && (
                <p className="pack-description">{pack.description}</p>
              )}

              <div className="pack-stats">
                <div className="stat">
                  <span className="stat-value">{pack.documents?.length || 0}</span>
                  <span className="stat-label">Documents</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {pack.documents?.filter((d) => d.is_required).length || 0}
                  </span>
                  <span className="stat-label">Required</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {pack.documents?.filter((d) => !d.is_required).length || 0}
                  </span>
                  <span className="stat-label">Optional</span>
                </div>
              </div>

              <div className="pack-actions">
                <button className="btn-icon" onClick={() => handleEdit(pack)} title="Edit">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                <button className="btn-icon" onClick={() => handleDuplicate(pack)} title="Duplicate">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                </button>
                <button className="btn-icon danger" onClick={() => handleDelete(pack.id)} title="Delete">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create/Edit Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{isEditing ? 'Edit Template Pack' : 'Create Template Pack'}</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                &times;
              </button>
            </div>

            <div className="modal-body">
              <div className="form-group">
                <label htmlFor="name">Pack Name</label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  placeholder="e.g., Standard Conventional"
                />
              </div>

              <div className="form-group">
                <label htmlFor="loan_type">Loan Type</label>
                <select
                  id="loan_type"
                  name="loan_type"
                  value={formData.loan_type}
                  onChange={handleInputChange}
                >
                  <option value="">Select loan type...</option>
                  {loanTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="description">Description</label>
                <textarea
                  id="description"
                  name="description"
                  value={formData.description}
                  onChange={handleInputChange}
                  placeholder="Optional description..."
                  rows={3}
                />
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    name="is_active"
                    checked={formData.is_active}
                    onChange={handleInputChange}
                  />
                  <span>Active</span>
                </label>
              </div>

              <div className="documents-section">
                <h3>Required Documents</h3>
                <p className="section-hint">
                  Select documents to include in this template pack
                </p>

                {Object.entries(documentsByCategory).map(([category, docs]) => (
                  <div key={category} className="document-category">
                    <h4 className="category-title">
                      {category.charAt(0).toUpperCase() + category.slice(1)}
                    </h4>
                    <div className="document-list">
                      {docs.map((doc) => {
                        const selected = formData.documents.find(
                          (d) => d.document_type === doc.id
                        );
                        return (
                          <div key={doc.id} className="document-item">
                            <label className="document-checkbox">
                              <input
                                type="checkbox"
                                checked={!!selected}
                                onChange={() => handleDocumentToggle(doc.id)}
                              />
                              <span>{doc.name}</span>
                            </label>
                            {selected && (
                              <label className="required-toggle">
                                <input
                                  type="checkbox"
                                  checked={selected.is_required}
                                  onChange={(e) =>
                                    handleDocumentRequiredChange(doc.id, e.target.checked)
                                  }
                                />
                                <span>Required</span>
                              </label>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="btn-secondary"
                onClick={() => setShowCreateModal(false)}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSave}
                disabled={saving || !formData.name || !formData.loan_type}
              >
                {saving ? 'Saving...' : isEditing ? 'Update Pack' : 'Create Pack'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminTemplatePackManagement;
