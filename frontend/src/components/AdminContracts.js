/**
 * AdminContracts Component
 *
 * Platform Contracts dashboard shown to platform admins on the Smart Docs page.
 * Manages licensing agreements, contracts, and e-signed documents with CRM licensees.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { platformContractsAPI } from '../services/platformContractsApi';
import './AdminContracts.css';
import { toast } from '../utils/toast';

const CONTRACT_TYPES = {
  license_agreement: 'License Agreement',
  addendum: 'Addendum',
  nda: 'NDA',
  service_agreement: 'Service Agreement',
};

const STATUS_LABELS = {
  draft: 'Draft',
  sent: 'Sent',
  viewed: 'Viewed',
  signed: 'Signed',
  expired: 'Expired',
  voided: 'Voided',
};

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending Signature' },
  { key: 'signed', label: 'Signed' },
  { key: 'draft', label: 'Drafts' },
  { key: 'expired', label: 'Expired' },
];

function AdminContracts() {
  const [summary, setSummary] = useState(null);
  const [contracts, setContracts] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);

  // Create form state
  const [formData, setFormData] = useState({
    title: '',
    contract_type: 'license_agreement',
    organization_id: '',
    description: '',
    effective_date: '',
    expiration_date: '',
    auto_renew: false,
    contract_value: '',
    billing_frequency: '',
    signer_name: '',
    signer_email: '',
    signer_title: '',
  });

  const fetchSummary = useCallback(async () => {
    try {
      const data = await platformContractsAPI.getContractsSummary();
      setSummary(data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  }, []);

  const fetchContracts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let statusFilter = null;
      if (activeTab === 'pending') statusFilter = 'sent';
      else if (activeTab !== 'all') statusFilter = activeTab;

      const data = await platformContractsAPI.listContracts({
        status: statusFilter,
        search: searchQuery || undefined,
        page,
        limit: 50,
      });
      setContracts(data.contracts || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
    } catch (err) {
      setError(err.message);
      setContracts([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, searchQuery, page]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  useEffect(() => {
    fetchContracts();
  }, [fetchContracts]);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setPage(1);
  };

  const handleSearch = (e) => {
    setSearchQuery(e.target.value);
    setPage(1);
  };

  const handleViewPdf = async (contract) => {
    try {
      const data = await platformContractsAPI.getDownloadUrl(contract.id);
      window.open(data.download_url, '_blank');
    } catch (err) {
      toast.error('Failed to get download URL: ' + err.message);
    }
  };

  const handleSendForSignature = async (contract) => {
    if (!window.confirm(`Send "${contract.title}" to ${contract.signer_email} for signature?`)) return;
    try {
      await platformContractsAPI.sendForSignature(contract.id);
      fetchContracts();
      fetchSummary();
    } catch (err) {
      toast.error('Failed to send for signature: ' + err.message);
    }
  };

  const handleVoid = async (contract) => {
    const action = contract.status === 'signed' ? 'void' : 'delete';
    if (!window.confirm(`Are you sure you want to ${action} "${contract.title}"?`)) return;
    try {
      await platformContractsAPI.deleteContract(contract.id);
      fetchContracts();
      fetchSummary();
    } catch (err) {
      toast.error(`Failed to ${action} contract: ` + err.message);
    }
  };

  const handleUploadPdf = async (contract) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        await platformContractsAPI.uploadContractPdf(contract.id, file);
        fetchContracts();
      } catch (err) {
        toast.error('Failed to upload PDF: ' + err.message);
      }
    };
    input.click();
  };

  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    if (!formData.title || !formData.organization_id) return;

    setCreating(true);
    try {
      const payload = {
        ...formData,
        organization_id: parseInt(formData.organization_id, 10),
        contract_value: formData.contract_value ? parseFloat(formData.contract_value) : null,
        effective_date: formData.effective_date || null,
        expiration_date: formData.expiration_date || null,
        billing_frequency: formData.billing_frequency || null,
      };
      await platformContractsAPI.createContract(payload);
      setShowCreateModal(false);
      setFormData({
        title: '',
        contract_type: 'license_agreement',
        organization_id: '',
        description: '',
        effective_date: '',
        expiration_date: '',
        auto_renew: false,
        contract_value: '',
        billing_frequency: '',
        signer_name: '',
        signer_email: '',
        signer_title: '',
      });
      fetchContracts();
      fetchSummary();
    } catch (err) {
      toast.error('Failed to create contract: ' + err.message);
    } finally {
      setCreating(false);
    }
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return '-';
    return new Date(isoStr).toLocaleDateString();
  };

  const formatCurrency = (val) => {
    if (val == null) return '-';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  return (
    <div className="admin-contracts">
      <div className="admin-contracts-header">
        <h1>Platform Contracts</h1>
        <p className="subtitle">
          Licensing agreements, contracts, and e-signed documents with CRM licensees
        </p>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="contracts-summary-cards">
          <div className="summary-card">
            <span className="card-label">Total Contracts</span>
            <span className="card-value">{summary.total}</span>
          </div>
          <div className="summary-card signed">
            <span className="card-label">Signed</span>
            <span className="card-value">{summary.signed}</span>
          </div>
          <div className="summary-card pending">
            <span className="card-label">Pending Signature</span>
            <span className="card-value">{summary.pending_signature}</span>
          </div>
          <div className="summary-card expiring">
            <span className="card-label">Expiring Soon</span>
            <span className="card-value">{summary.expiring_soon}</span>
          </div>
          <div className="summary-card">
            <span className="card-label">Total Value (Signed)</span>
            <span className="card-value" style={{ fontSize: '1.25rem' }}>
              {formatCurrency(summary.total_contract_value)}
            </span>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="contracts-toolbar">
        <div className="toolbar-left">
          <input
            type="text"
            className="contracts-search"
            placeholder="Search contracts..."
            value={searchQuery}
            onChange={handleSearch}
          />
        </div>
        <button className="btn-create-contract" onClick={() => setShowCreateModal(true)}>
          + New Contract
        </button>
      </div>

      {/* Tabs */}
      <div className="contracts-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="contracts-error">
          <p>{error}</p>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="contracts-loading">Loading contracts...</div>
      ) : contracts.length === 0 ? (
        <div className="contracts-empty">
          <p>No contracts found</p>
          <p>Click "+ New Contract" to create your first contract.</p>
        </div>
      ) : (
        <>
          <div className="contracts-table-wrapper">
            <table className="contracts-table">
              <thead>
                <tr>
                  <th>Licensee</th>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Effective</th>
                  <th>Expiration</th>
                  <th>Value</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((c) => (
                  <tr key={c.id}>
                    <td>{c.organization_name || 'Unknown'}</td>
                    <td>{c.title}</td>
                    <td>
                      <span className="type-badge">
                        {CONTRACT_TYPES[c.contract_type] || c.contract_type}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${c.status}`}>
                        {STATUS_LABELS[c.status] || c.status}
                      </span>
                    </td>
                    <td>{formatDate(c.effective_date)}</td>
                    <td>{formatDate(c.expiration_date)}</td>
                    <td>{formatCurrency(c.contract_value)}</td>
                    <td>
                      {c.has_pdf && (
                        <button className="action-btn" onClick={() => handleViewPdf(c)}>
                          View PDF
                        </button>
                      )}
                      {!c.has_pdf && c.status === 'draft' && (
                        <button className="action-btn" onClick={() => handleUploadPdf(c)}>
                          Upload PDF
                        </button>
                      )}
                      {c.has_pdf && (c.status === 'draft' || c.status === 'sent') && c.signer_email && (
                        <button
                          className="action-btn primary"
                          onClick={() => handleSendForSignature(c)}
                        >
                          Send
                        </button>
                      )}
                      {c.status !== 'voided' && (
                        <button className="action-btn danger" onClick={() => handleVoid(c)}>
                          {c.status === 'signed' ? 'Void' : 'Delete'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {pages > 1 && (
            <div className="contracts-pagination">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span>
                Page {page} of {pages} ({total} total)
              </span>
              <button disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Create Contract</h2>
            <form onSubmit={handleCreateSubmit}>
              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g. CRM License Agreement - Acme Mortgage"
                  required
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Contract Type</label>
                  <select
                    value={formData.contract_type}
                    onChange={(e) => setFormData({ ...formData, contract_type: e.target.value })}
                  >
                    {Object.entries(CONTRACT_TYPES).map(([val, label]) => (
                      <option key={val} value={val}>{label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Organization ID *</label>
                  <input
                    type="number"
                    value={formData.organization_id}
                    onChange={(e) => setFormData({ ...formData, organization_id: e.target.value })}
                    placeholder="Organization ID"
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Optional description..."
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Effective Date</label>
                  <input
                    type="date"
                    value={formData.effective_date}
                    onChange={(e) => setFormData({ ...formData, effective_date: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Expiration Date</label>
                  <input
                    type="date"
                    value={formData.expiration_date}
                    onChange={(e) => setFormData({ ...formData, expiration_date: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Contract Value ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.contract_value}
                    onChange={(e) => setFormData({ ...formData, contract_value: e.target.value })}
                    placeholder="0.00"
                  />
                </div>
                <div className="form-group">
                  <label>Billing Frequency</label>
                  <select
                    value={formData.billing_frequency}
                    onChange={(e) => setFormData({ ...formData, billing_frequency: e.target.value })}
                  >
                    <option value="">Select...</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="annually">Annually</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.auto_renew}
                    onChange={(e) => setFormData({ ...formData, auto_renew: e.target.checked })}
                    style={{ marginRight: 8 }}
                  />
                  Auto-renew
                </label>
              </div>

              <h3 style={{ margin: '20px 0 12px', fontSize: '1rem', color: '#374151' }}>
                Signer Information
              </h3>

              <div className="form-row">
                <div className="form-group">
                  <label>Signer Name</label>
                  <input
                    type="text"
                    value={formData.signer_name}
                    onChange={(e) => setFormData({ ...formData, signer_name: e.target.value })}
                    placeholder="Full name"
                  />
                </div>
                <div className="form-group">
                  <label>Signer Email</label>
                  <input
                    type="email"
                    value={formData.signer_email}
                    onChange={(e) => setFormData({ ...formData, signer_email: e.target.value })}
                    placeholder="email@company.com"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Signer Title</label>
                <input
                  type="text"
                  value={formData.signer_title}
                  onChange={(e) => setFormData({ ...formData, signer_title: e.target.value })}
                  placeholder="e.g. CEO, Branch Manager"
                />
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-cancel" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-submit"
                  disabled={creating || !formData.title || !formData.organization_id}
                >
                  {creating ? 'Creating...' : 'Create Contract'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminContracts;
