/**
 * AdminDocumentReviewQueue Page
 *
 * Queue for reviewing and approving/rejecting borrower-uploaded documents.
 * Supports filtering, bulk actions, and detailed document preview.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { usePermissions } from '../contexts/PermissionContext';
import './AdminDocumentReviewQueue.css';

const AdminDocumentReviewQueue = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require document review access
  const canAccessDocReview = isAdmin || hasAnyPermission(['admin.manage', 'documents.review', 'documents.manage', 'system.admin']) || userRole === 'admin' || userRole === 'management';

  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [previewDoc, setPreviewDoc] = useState(null);
  const [filters, setFilters] = useState({
    status: 'pending',
    document_type: '',
    search: '',
  });
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
  });
  const [rejectionReason, setRejectionReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [processingAction, setProcessingAction] = useState(null);

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getDocumentReviewQueue({
        page: pagination.page,
        limit: pagination.limit,
        status: filters.status || undefined,
        documentType: filters.document_type || undefined,
        search: filters.search || undefined,
      });

      setDocuments(data.documents || []);
      setPagination((prev) => ({ ...prev, total: data.total || 0 }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [pagination.page, pagination.limit, filters]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Handle filter changes
  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  // Handle selection
  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedDocs(documents.map((d) => d.id));
    } else {
      setSelectedDocs([]);
    }
  };

  const handleSelectDoc = (docId) => {
    setSelectedDocs((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    );
  };

  // Approve document(s)
  const handleApprove = async (docIds) => {
    try {
      setProcessingAction('approve');
      const ids = Array.isArray(docIds) ? docIds : [docIds];
      await api.bulkApproveDocuments(ids);
      setSelectedDocs([]);
      await fetchDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setProcessingAction(null);
    }
  };

  // Reject document(s)
  const handleReject = async () => {
    try {
      setProcessingAction('reject');
      await api.bulkRejectDocuments(selectedDocs, rejectionReason);
      setSelectedDocs([]);
      setShowRejectModal(false);
      setRejectionReason('');
      await fetchDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setProcessingAction(null);
    }
  };

  // Request additional info
  const handleRequestInfo = async (docId, message) => {
    try {
      await api.requestDocumentInfo(docId, message);
      await fetchDocuments();
    } catch (err) {
      setError(err.message);
    }
  };

  // Format document type
  const formatDocumentType = (type) => {
    return type
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Format date
  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Get status badge class
  const getStatusClass = (status) => {
    switch (status) {
      case 'approved':
        return 'approved';
      case 'rejected':
        return 'rejected';
      case 'pending':
        return 'pending';
      case 'needs_info':
        return 'needs-info';
      default:
        return '';
    }
  };

  const documentTypes = [
    'paystubs',
    'w2',
    'tax_returns',
    'bank_statements',
    'drivers_license',
    'purchase_contract',
    'appraisal',
  ];

  // Access denied if user doesn't have document review permissions
  if (!canAccessDocReview) {
    return (
      <div className="admin-document-review-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to review documents.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-document-review-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Document Review Queue</h1>
          <p>Review and process borrower-submitted documents</p>
        </div>
        <div className="header-stats">
          <div className="stat-item">
            <span className="stat-value">{pagination.total}</span>
            <span className="stat-label">Pending Review</span>
          </div>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* Filters */}
      <div className="filters-bar">
        <div className="filter-group">
          <select
            value={filters.status}
            onChange={(e) => handleFilterChange('status', e.target.value)}
          >
            <option value="pending">Pending Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="needs_info">Needs Info</option>
            <option value="">All Statuses</option>
          </select>
        </div>

        <div className="filter-group">
          <select
            value={filters.document_type}
            onChange={(e) => handleFilterChange('document_type', e.target.value)}
          >
            <option value="">All Document Types</option>
            {documentTypes.map((type) => (
              <option key={type} value={type}>
                {formatDocumentType(type)}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search by borrower or loan..."
            value={filters.search}
            onChange={(e) => handleFilterChange('search', e.target.value)}
          />
        </div>
      </div>

      {/* Bulk Actions */}
      {selectedDocs.length > 0 && (
        <div className="bulk-actions-bar">
          <span className="selection-count">
            {selectedDocs.length} document{selectedDocs.length > 1 ? 's' : ''} selected
          </span>
          <div className="bulk-buttons">
            <button
              className="btn-approve"
              onClick={() => handleApprove(selectedDocs)}
              disabled={processingAction}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Approve Selected
            </button>
            <button
              className="btn-reject"
              onClick={() => setShowRejectModal(true)}
              disabled={processingAction}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Reject Selected
            </button>
          </div>
        </div>
      )}

      {/* Documents Table */}
      <div className="documents-table-container">
        {loading ? (
          <div className="loading-state">
            <div className="spinner" />
            <p>Loading documents...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <polyline points="16 13 12 17 8 13" />
              <line x1="12" y1="12" x2="12" y2="17" />
            </svg>
            <h3>No Documents</h3>
            <p>No documents match your current filters.</p>
          </div>
        ) : (
          <table className="documents-table">
            <thead>
              <tr>
                <th className="checkbox-col">
                  <input
                    type="checkbox"
                    checked={selectedDocs.length === documents.length}
                    onChange={handleSelectAll}
                  />
                </th>
                <th>Document</th>
                <th>Borrower</th>
                <th>Loan</th>
                <th>Uploaded</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className={selectedDocs.includes(doc.id) ? 'selected' : ''}>
                  <td className="checkbox-col">
                    <input
                      type="checkbox"
                      checked={selectedDocs.includes(doc.id)}
                      onChange={() => handleSelectDoc(doc.id)}
                    />
                  </td>
                  <td>
                    <div className="document-info">
                      <span className="document-type">
                        {formatDocumentType(doc.document_type)}
                      </span>
                      <span className="document-name">{doc.file_name}</span>
                    </div>
                  </td>
                  <td>
                    <div className="borrower-info">
                      <span className="borrower-name">{doc.borrower_name}</span>
                      <span className="borrower-email">{doc.borrower_email}</span>
                    </div>
                  </td>
                  <td>
                    <span className="loan-number">{doc.loan_number}</span>
                  </td>
                  <td>
                    <span className="upload-date">{formatDate(doc.uploaded_at)}</span>
                  </td>
                  <td>
                    <span className={`status-badge ${getStatusClass(doc.status)}`}>
                      {doc.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td>
                    <div className="action-buttons">
                      <button
                        className="btn-icon preview"
                        onClick={() => setPreviewDoc(doc)}
                        title="Preview"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      </button>
                      {doc.status === 'pending' && (
                        <>
                          <button
                            className="btn-icon approve"
                            onClick={() => handleApprove(doc.id)}
                            disabled={processingAction}
                            title="Approve"
                          >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          </button>
                          <button
                            className="btn-icon reject"
                            onClick={() => {
                              setSelectedDocs([doc.id]);
                              setShowRejectModal(true);
                            }}
                            disabled={processingAction}
                            title="Reject"
                          >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {pagination.total > pagination.limit && (
        <div className="pagination">
          <button
            disabled={pagination.page === 1}
            onClick={() => setPagination((prev) => ({ ...prev, page: prev.page - 1 }))}
          >
            Previous
          </button>
          <span>
            Page {pagination.page} of {Math.ceil(pagination.total / pagination.limit)}
          </span>
          <button
            disabled={pagination.page >= Math.ceil(pagination.total / pagination.limit)}
            onClick={() => setPagination((prev) => ({ ...prev, page: prev.page + 1 }))}
          >
            Next
          </button>
        </div>
      )}

      {/* Document Preview Modal */}
      {previewDoc && (
        <div className="modal-overlay" onClick={() => setPreviewDoc(null)}>
          <div className="preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>{formatDocumentType(previewDoc.document_type)}</h2>
                <p>{previewDoc.file_name}</p>
              </div>
              <button className="modal-close" onClick={() => setPreviewDoc(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body preview-content">
              {previewDoc.file_url ? (
                previewDoc.file_type?.includes('pdf') ? (
                  <iframe
                    src={previewDoc.file_url}
                    title="Document Preview"
                    className="pdf-preview"
                  />
                ) : (
                  <img
                    src={previewDoc.file_url}
                    alt="Document Preview"
                    className="image-preview"
                  />
                )
              ) : (
                <div className="no-preview">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  <p>Preview not available</p>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <div className="preview-meta">
                <span>Uploaded by {previewDoc.borrower_name}</span>
                <span>{formatDate(previewDoc.uploaded_at)}</span>
              </div>
              {previewDoc.status === 'pending' && (
                <div className="preview-actions">
                  <button
                    className="btn-secondary"
                    onClick={() => {
                      setSelectedDocs([previewDoc.id]);
                      setShowRejectModal(true);
                      setPreviewDoc(null);
                    }}
                  >
                    Reject
                  </button>
                  <button
                    className="btn-primary"
                    onClick={() => {
                      handleApprove(previewDoc.id);
                      setPreviewDoc(null);
                    }}
                  >
                    Approve
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Rejection Modal */}
      {showRejectModal && (
        <div className="modal-overlay" onClick={() => setShowRejectModal(false)}>
          <div className="modal-content reject-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Reject Document{selectedDocs.length > 1 ? 's' : ''}</h2>
              <button className="modal-close" onClick={() => setShowRejectModal(false)}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <p className="reject-message">
                Please provide a reason for rejection. The borrower will be notified.
              </p>
              <div className="form-group">
                <label>Rejection Reason</label>
                <textarea
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder="e.g., Document is illegible, wrong document type, expired..."
                  rows={4}
                />
              </div>
              <div className="quick-reasons">
                <span>Quick select:</span>
                {[
                  'Document is illegible',
                  'Incorrect document type',
                  'Document is expired',
                  'Missing required pages',
                  'Name mismatch',
                ].map((reason) => (
                  <button
                    key={reason}
                    type="button"
                    onClick={() => setRejectionReason(reason)}
                    className={rejectionReason === reason ? 'active' : ''}
                  >
                    {reason}
                  </button>
                ))}
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="btn-secondary"
                onClick={() => setShowRejectModal(false)}
              >
                Cancel
              </button>
              <button
                className="btn-danger"
                onClick={handleReject}
                disabled={!rejectionReason || processingAction}
              >
                {processingAction === 'reject'
                  ? 'Rejecting...'
                  : `Reject ${selectedDocs.length} Document${selectedDocs.length > 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDocumentReviewQueue;
