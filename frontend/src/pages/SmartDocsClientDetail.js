/**
 * SmartDocsClientDetail - Client Document Portal
 *
 * Layout:
 * - Left sidebar: List of documents requested
 * - Main area: Document viewer (shows selected document)
 * - Above document: Parsed info (date, expiration, reminder toggle)
 * - Actions: Merge/download, merge/email, individual download/email
 *
 * Features:
 * - Click document in sidebar to view
 * - Toggle reminders per loan
 * - Bulk select for merge operations
 * - Expired documents highlighted
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import IncomeCalculatorModal from '../components/income/IncomeCalculatorModal';
import './SmartDocsClientDetail.css';

function SmartDocsClientDetail() {
  const { loanId } = useParams();
  const navigate = useNavigate();

  // State
  const [loading, setLoading] = useState(true);
  const [client, setClient] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [selectedDocs, setSelectedDocs] = useState(new Set());
  const [remindersEnabled, setRemindersEnabled] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showIncomeModal, setShowIncomeModal] = useState(false);
  const [editingDocType, setEditingDocType] = useState(false);
  const [editingDocDate, setEditingDocDate] = useState(false);
  const [editingExpiration, setEditingExpiration] = useState(false);
  const [extracting, setExtracting] = useState(false);

  // Document types available for selection
  const DOC_TYPES = [
    { value: 'DRIVERS_LICENSE', label: "Driver's License" },
    { value: 'PAYSTUB', label: 'Pay Stubs' },
    { value: 'W2', label: 'W-2 Forms' },
    { value: 'TAX_RETURN', label: 'Tax Returns' },
    { value: 'BUSINESS_TAX_RETURN', label: 'Business Tax Returns' },
    { value: 'PROFIT_LOSS', label: 'Profit & Loss' },
    { value: 'BALANCE_SHEET', label: 'Balance Sheet' },
    { value: 'BANK_STATEMENT', label: 'Bank Statements' },
    { value: 'INVESTMENT_STATEMENT', label: 'Investment Statements' },
    { value: 'GIFT_LETTER', label: 'Gift Letter' },
    { value: 'LOE', label: 'Letter of Explanation' },
    { value: 'LEASE_AGREEMENT', label: 'Lease Agreement' },
    { value: 'FHA_CERT', label: 'FHA Certificate' },
    { value: 'VA_COE', label: 'VA COE' },
    { value: 'DD214', label: 'DD-214' },
    { value: 'BANKRUPTCY_DISCHARGE', label: 'Bankruptcy Discharge' },
    { value: 'PURCHASE_CONTRACT', label: 'Purchase Contract' },
    { value: 'APPRAISAL', label: 'Appraisal' },
    { value: 'TITLE_REPORT', label: 'Title Report' },
    { value: 'HOMEOWNERS_INSURANCE', label: "Homeowner's Insurance" },
    { value: 'OTHER', label: 'Other' },
  ];

  // Fetch client documents
  const fetchClientData = useCallback(async () => {
    setLoading(true);
    let clientInfoFound = false;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      // Fetch document requests from needs list - this uses PURL loan IDs
      const needsListRes = await fetch(`${API_BASE_URL}/api/v1/smart-docs/needs-list/${loanId}`, { headers });
      if (needsListRes.ok) {
        const needsListData = await needsListRes.json();
        // Backend returns all_requests array and loan info
        const requests = needsListData.all_requests || [];
        setDocuments(requests);
        // Get client info from needs list response
        if (needsListData.borrower_name || needsListData.loan_number) {
          setClient({
            name: needsListData.borrower_name || 'Unknown',
            email: needsListData.borrower_email,
            loanNumber: needsListData.loan_number,
            stage: needsListData.stage
          });
          clientInfoFound = true;
        }
        // Auto-select first document if available
        if (requests.length > 0) {
          setSelectedDoc(requests[0]);
        }
      } else {
        // Fallback: try queue detail endpoint
        const queueRes = await fetch(`${API_BASE_URL}/api/v1/smart-docs/queue/${loanId}`, { headers });
        if (queueRes.ok) {
          const queueData = await queueRes.json();
          // Queue returns requests array and client info
          const requests = queueData.requests || queueData.all_requests || [];
          setDocuments(requests);
          // Get client info from queue response
          if (queueData.borrower_name || queueData.loan_number) {
            setClient({
              name: queueData.borrower_name || 'Unknown',
              email: queueData.borrower_email,
              loanNumber: queueData.loan_number,
              stage: queueData.stage
            });
            clientInfoFound = true;
          }
          if (requests.length > 0) {
            setSelectedDoc(requests[0]);
          }
        }
      }

      // If client info not found, set fallback
      if (!clientInfoFound) {
        setClient({
          name: `Loan ${loanId}`,
          email: null,
          loanNumber: null,
          stage: null
        });
      }

      // Fetch reminder settings
      const reminderRes = await fetch(`${API_BASE_URL}/api/v1/smart-docs/reminders/${loanId}`, { headers });
      if (reminderRes.ok) {
        const reminderData = await reminderRes.json();
        setRemindersEnabled(reminderData.reminders_enabled ?? true);
      }

    } catch (err) {
      console.error('Error fetching client data:', err);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchClientData();
  }, [fetchClientData]);

  // Toggle document selection for bulk actions
  const toggleDocSelection = (docId) => {
    const newSelected = new Set(selectedDocs);
    if (newSelected.has(docId)) {
      newSelected.delete(docId);
    } else {
      newSelected.add(docId);
    }
    setSelectedDocs(newSelected);
  };

  // Select all documents
  const selectAllDocs = () => {
    if (selectedDocs.size === documents.length) {
      setSelectedDocs(new Set());
    } else {
      setSelectedDocs(new Set(documents.map(d => d.id)));
    }
  };

  // Toggle reminders
  const handleToggleReminders = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      const response = await fetch(`${API_BASE_URL}/api/v1/smart-docs/reminders/${loanId}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ reminders_enabled: !remindersEnabled })
      });

      if (response.ok) {
        setRemindersEnabled(!remindersEnabled);
      }
    } catch (err) {
      console.error('Error toggling reminders:', err);
    }
  };

  // Merge and download selected documents
  const handleMergeDownload = async () => {
    if (selectedDocs.size === 0) return;
    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/smart-docs/merge`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          loan_id: loanId,
          document_ids: Array.from(selectedDocs)
        })
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${client?.name || 'documents'}_merged.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Error merging documents:', err);
    } finally {
      setActionLoading(false);
    }
  };

  // Merge and email selected documents
  const handleMergeEmail = async () => {
    if (selectedDocs.size === 0) return;
    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/smart-docs/merge-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          loan_id: loanId,
          document_ids: Array.from(selectedDocs)
        })
      });
      alert('Documents merged and email sent!');
    } catch (err) {
      console.error('Error merging and emailing:', err);
    } finally {
      setActionLoading(false);
    }
  };

  // Download individual document
  const handleDownloadSingle = async (doc) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/smart-docs/documents/${doc.id}/download`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.filename || `${doc.doc_type}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Error downloading document:', err);
    }
  };

  // Email individual document
  const handleEmailSingle = async (doc) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/smart-docs/documents/${doc.id}/email`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      alert('Document emailed!');
    } catch (err) {
      console.error('Error emailing document:', err);
    }
  };

  // Approve document
  const handleApprove = async (doc) => {
    if (!window.confirm(`Approve this ${getDocTypeName(doc.doc_type)}?`)) return;
    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      const reviewer = user.email || user.name || 'Unknown';

      // Get document ID from document object
      const documentId = doc.document_id || doc.id;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}/approve?reviewer=${encodeURIComponent(reviewer)}`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        alert('Document approved!');
        fetchClientData(); // Refresh data
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to approve document'}`);
      }
    } catch (err) {
      console.error('Error approving document:', err);
      alert('Error approving document');
    } finally {
      setActionLoading(false);
    }
  };

  // Reject document
  const handleReject = async (doc) => {
    const reason = window.prompt('Enter rejection reason:');
    if (!reason) return;

    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      const reviewer = user.email || user.name || 'Unknown';

      const documentId = doc.document_id || doc.id;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}/reject`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            reviewer,
            reason,
            rejection_category: 'OTHER'
          })
        }
      );

      if (response.ok) {
        alert('Document rejected');
        fetchClientData();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to reject document'}`);
      }
    } catch (err) {
      console.error('Error rejecting document:', err);
      alert('Error rejecting document');
    } finally {
      setActionLoading(false);
    }
  };

  // Delete document
  const handleDelete = async (doc) => {
    if (!window.confirm(`Delete this ${getDocTypeName(doc.doc_type)}? This will allow the borrower to re-upload.`)) return;

    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      const reviewer = user.email || user.name || 'Unknown';

      const documentId = doc.document_id || doc.id;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}?reviewer=${encodeURIComponent(reviewer)}`,
        {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );

      if (response.ok) {
        alert('Document deleted');
        fetchClientData();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to delete document'}`);
      }
    } catch (err) {
      console.error('Error deleting document:', err);
      alert('Error deleting document');
    } finally {
      setActionLoading(false);
    }
  };

  // Re-request document
  const handleReRequest = async (doc) => {
    if (!window.confirm(`Re-request this ${getDocTypeName(doc.doc_type)}? The borrower will be notified to upload again.`)) return;

    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      const reviewer = user.email || user.name || 'Unknown';

      // Re-request uses the request_id, not document_id
      const requestId = doc.id; // Document request ID

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/request/${requestId}/re-request`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            reviewer,
            notes: 'Re-requested via Smart Docs portal'
          })
        }
      );

      if (response.ok) {
        alert('Document re-requested! Borrower will be notified.');
        fetchClientData();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to re-request document'}`);
      }
    } catch (err) {
      console.error('Error re-requesting document:', err);
      alert('Error re-requesting document');
    } finally {
      setActionLoading(false);
    }
  };

  // Update document type
  const handleUpdateDocType = async (doc, newDocType) => {
    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const documentId = doc.document_id || doc.id;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}/type`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ doc_type: newDocType })
        }
      );

      if (response.ok) {
        setEditingDocType(false);
        fetchClientData();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to update document type'}`);
      }
    } catch (err) {
      console.error('Error updating document type:', err);
      alert('Error updating document type');
    } finally {
      setActionLoading(false);
    }
  };

  // Update document dates
  const handleUpdateDates = async (doc, docDate, expirationDate) => {
    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const documentId = doc.document_id || doc.id;

      const body = {};
      if (docDate !== undefined) body.doc_date = docDate || '';
      if (expirationDate !== undefined) body.expiration_date = expirationDate || '';

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}/dates`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(body)
        }
      );

      if (response.ok) {
        setEditingDocDate(false);
        setEditingExpiration(false);
        fetchClientData();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || 'Failed to update dates'}`);
      }
    } catch (err) {
      console.error('Error updating dates:', err);
      alert('Error updating dates');
    } finally {
      setActionLoading(false);
    }
  };

  // AI Extract document data
  const handleAIExtract = async (doc) => {
    setExtracting(true);
    try {
      const token = localStorage.getItem('token');
      const documentId = doc.document_id || doc.id;

      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}/extract`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const result = await response.json();
        alert(`AI Extraction Complete!\n\nDetected Type: ${result.detected_doc_type || 'Unknown'}\nConfidence: ${Math.round((result.overall_confidence || 0) * 100)}%`);
        fetchClientData();
      } else {
        const error = await response.json();
        alert(`Extraction failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Error extracting document:', err);
      alert('Error running AI extraction');
    } finally {
      setExtracting(false);
    }
  };

  // Format date for input field (YYYY-MM-DD)
  const formatDateForInput = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toISOString().split('T')[0];
  };

  // Check if document has an uploaded file
  const hasUploadedDocument = (doc) => {
    return doc.document_id || doc.file_url || doc.s3_url || doc.filename || doc.status === 'PENDING_REVIEW';
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Check if document is expired
  const isExpired = (doc) => {
    if (!doc.expiration_date) return false;
    return new Date(doc.expiration_date) < new Date();
  };

  // Get status badge class
  const getStatusClass = (doc) => {
    if (isExpired(doc)) return 'expired';
    if (doc.status === 'ACCEPTED' || doc.status === 'approved') return 'accepted';
    if (doc.status === 'PENDING_REVIEW' || doc.status === 'pending') return 'pending';
    if (doc.status === 'REJECTED' || doc.status === 'rejected') return 'rejected';
    return 'open';
  };

  // Get document type display name
  const getDocTypeName = (docType) => {
    const names = {
      'paystubs': 'Pay Stubs',
      'bank_statements': 'Bank Statements',
      'tax_returns': 'Tax Returns',
      'w2': 'W-2 Forms',
      '1099': '1099 Forms',
      'drivers_license': "Driver's License",
      'purchase_contract': 'Purchase Contract',
      'hoa_docs': 'HOA Documents',
      'gift_letter': 'Gift Letter',
      // Uppercase enum values from backend
      'DRIVERS_LICENSE': "Driver's License",
      'PAYSTUB': 'Pay Stubs',
      'W2': 'W-2 Forms',
      'TAX_RETURN': 'Tax Returns',
      'BUSINESS_TAX_RETURN': 'Business Tax Returns',
      'PROFIT_LOSS': 'Profit & Loss',
      'BALANCE_SHEET': 'Balance Sheet',
      'BANK_STATEMENT': 'Bank Statements',
      'INVESTMENT_STATEMENT': 'Investment Statements',
      'GIFT_LETTER': 'Gift Letter',
      'LOE': 'Letter of Explanation',
      'LEASE_AGREEMENT': 'Lease Agreement',
      'FHA_CERT': 'FHA Certificate',
      'VA_COE': 'VA COE',
      'DD214': 'DD-214',
      'BANKRUPTCY_DISCHARGE': 'Bankruptcy Discharge',
      'PURCHASE_CONTRACT': 'Purchase Contract',
      'APPRAISAL': 'Appraisal',
      'TITLE_REPORT': 'Title Report',
      'HOMEOWNERS_INSURANCE': "Homeowner's Insurance",
      'OTHER': 'Other'
    };
    return names[docType] || docType?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Document';
  };

  if (loading) {
    return (
      <div className="client-detail-page">
        <div className="loading-container">
          <div className="spinner" />
          <p>Loading client documents...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="client-detail-page">
      {/* Header */}
      <header className="client-header">
        <button className="back-btn" onClick={() => navigate('/smart-docs')}>
          ← Back to Queue
        </button>
        <div className="client-info-header">
          <h1>{client?.name || 'Client'}</h1>
          {client?.email && <span className="client-email">{client.email}</span>}
        </div>
        <div className="header-actions">
          <button
            className="income-calc-btn"
            onClick={() => setShowIncomeModal(true)}
            title="Income Calculator"
          >
            📊 Income
          </button>
          <label className="reminder-toggle">
            <input
              type="checkbox"
              checked={remindersEnabled}
              onChange={handleToggleReminders}
            />
            <span className="toggle-label">Reminders {remindersEnabled ? 'On' : 'Off'}</span>
          </label>
        </div>
      </header>

      <div className="client-content">
        {/* Left Sidebar - Document List */}
        <aside className="document-sidebar">
          <div className="sidebar-header">
            <h2>Documents</h2>
            <label className="select-all">
              <input
                type="checkbox"
                checked={selectedDocs.size === documents.length && documents.length > 0}
                onChange={selectAllDocs}
              />
              <span>Select All</span>
            </label>
          </div>

          <div className="document-list">
            {documents.length === 0 ? (
              <div className="no-documents">
                <span className="empty-icon">📄</span>
                <p>No documents requested</p>
              </div>
            ) : (
              documents.map((doc) => (
                <div
                  key={doc.id}
                  className={`document-item ${selectedDoc?.id === doc.id ? 'active' : ''} ${isExpired(doc) ? 'expired' : ''}`}
                  onClick={() => setSelectedDoc(doc)}
                >
                  <input
                    type="checkbox"
                    checked={selectedDocs.has(doc.id)}
                    onChange={(e) => {
                      e.stopPropagation();
                      toggleDocSelection(doc.id);
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="doc-item-content">
                    <span className="doc-title">{getDocTypeName(doc.doc_type)}</span>
                    <span className={`doc-status ${getStatusClass(doc)}`}>
                      {isExpired(doc) ? 'Expired' : doc.status?.replace(/_/g, ' ')}
                    </span>
                  </div>
                  {isExpired(doc) && <span className="expired-badge">!</span>}
                </div>
              ))
            )}
          </div>

          {/* Bulk Actions */}
          {selectedDocs.size > 0 && (
            <div className="bulk-actions">
              <span className="selected-count">{selectedDocs.size} selected</span>
              <button
                className="action-btn primary"
                onClick={handleMergeDownload}
                disabled={actionLoading}
              >
                Merge & Download
              </button>
              <button
                className="action-btn secondary"
                onClick={handleMergeEmail}
                disabled={actionLoading}
              >
                Merge & Email
              </button>
            </div>
          )}

        </aside>

        {/* Main Content - Document Viewer */}
        <main className="document-viewer">
          {selectedDoc ? (
            <>
              {/* Parsed Info Container */}
              <div className="document-info-bar">
                <div className="info-group">
                  <label>Document Type</label>
                  {editingDocType ? (
                    <div className="doc-type-edit">
                      <select
                        value={selectedDoc.doc_type?.toUpperCase() || 'OTHER'}
                        onChange={(e) => handleUpdateDocType(selectedDoc, e.target.value)}
                        disabled={actionLoading}
                        autoFocus
                      >
                        {DOC_TYPES.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                      <button
                        className="cancel-edit-btn"
                        onClick={() => setEditingDocType(false)}
                        title="Cancel"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <span className="doc-type-display">
                      {getDocTypeName(selectedDoc.doc_type)}
                      <button
                        className="edit-btn"
                        onClick={() => setEditingDocType(true)}
                        title="Edit document type"
                      >
                        Edit
                      </button>
                    </span>
                  )}
                </div>
                <div className="info-group">
                  <label>Document Date</label>
                  {editingDocDate ? (
                    <div className="date-edit">
                      <input
                        type="date"
                        defaultValue={formatDateForInput(selectedDoc.doc_date)}
                        onChange={(e) => handleUpdateDates(selectedDoc, e.target.value, undefined)}
                        disabled={actionLoading}
                        autoFocus
                      />
                      <button
                        className="cancel-edit-btn"
                        onClick={() => setEditingDocDate(false)}
                        title="Cancel"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <span className="editable-value">
                      {formatDate(selectedDoc.doc_date)}
                      <button
                        className="edit-btn"
                        onClick={() => setEditingDocDate(true)}
                        title="Edit document date"
                      >
                        Edit
                      </button>
                    </span>
                  )}
                </div>
                <div className="info-group">
                  <label>Expiration</label>
                  {editingExpiration ? (
                    <div className="date-edit">
                      <input
                        type="date"
                        defaultValue={formatDateForInput(selectedDoc.expiration_date || selectedDoc.doc_expires_at)}
                        onChange={(e) => handleUpdateDates(selectedDoc, undefined, e.target.value)}
                        disabled={actionLoading}
                        autoFocus
                      />
                      <button
                        className="cancel-edit-btn"
                        onClick={() => setEditingExpiration(false)}
                        title="Cancel"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <span className={`editable-value ${isExpired(selectedDoc) ? 'expired-text' : ''}`}>
                      {formatDate(selectedDoc.expiration_date || selectedDoc.doc_expires_at)}
                      {isExpired(selectedDoc) && ' (Expired)'}
                      <button
                        className="edit-btn"
                        onClick={() => setEditingExpiration(true)}
                        title="Edit expiration date"
                      >
                        Edit
                      </button>
                    </span>
                  )}
                </div>
                <div className="info-group">
                  <label>Status</label>
                  <span className={`status-value ${getStatusClass(selectedDoc)}`}>
                    {selectedDoc.status?.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="doc-actions">
                  {/* AI Extraction button */}
                  {hasUploadedDocument(selectedDoc) && (
                    <button
                      className="ai-extract-btn"
                      onClick={() => handleAIExtract(selectedDoc)}
                      disabled={extracting || actionLoading}
                      title="AI auto-detect document type and extract dates"
                    >
                      {extracting ? '...' : '🤖 AI Extract'}
                    </button>
                  )}
                  {/* File actions - only show if document has been uploaded */}
                  {hasUploadedDocument(selectedDoc) && (
                    <>
                      <button
                        className="icon-btn"
                        onClick={() => handleDownloadSingle(selectedDoc)}
                        title="Download"
                      >
                        ⬇️
                      </button>
                      <button
                        className="icon-btn"
                        onClick={() => handleEmailSingle(selectedDoc)}
                        title="Email"
                      >
                        ✉️
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Review Actions Bar - shown for documents pending review */}
              {hasUploadedDocument(selectedDoc) && selectedDoc.status !== 'APPROVED' && selectedDoc.status !== 'ACCEPTED' && (
                <div className="review-actions-bar">
                  <span className="review-label">Review Actions:</span>
                  <div className="review-buttons">
                    <button
                      className="action-btn approve-btn"
                      onClick={() => handleApprove(selectedDoc)}
                      disabled={actionLoading}
                      title="Approve this document"
                    >
                      ✓ Approve
                    </button>
                    <button
                      className="action-btn reject-btn"
                      onClick={() => handleReject(selectedDoc)}
                      disabled={actionLoading}
                      title="Reject this document"
                    >
                      ✗ Reject
                    </button>
                    <button
                      className="action-btn delete-btn"
                      onClick={() => handleDelete(selectedDoc)}
                      disabled={actionLoading}
                      title="Delete this document"
                    >
                      🗑️ Delete
                    </button>
                    <button
                      className="action-btn rerequest-btn"
                      onClick={() => handleReRequest(selectedDoc)}
                      disabled={actionLoading}
                      title="Request a new upload"
                    >
                      🔄 Re-request
                    </button>
                  </div>
                </div>
              )}

              {/* Show re-request for documents awaiting upload */}
              {!hasUploadedDocument(selectedDoc) && selectedDoc.status === 'OPEN' && (
                <div className="review-actions-bar">
                  <span className="review-label">Actions:</span>
                  <div className="review-buttons">
                    <button
                      className="action-btn rerequest-btn"
                      onClick={() => handleReRequest(selectedDoc)}
                      disabled={actionLoading}
                      title="Send reminder to borrower"
                    >
                      🔄 Send Reminder
                    </button>
                  </div>
                </div>
              )}

              {/* Document Preview */}
              <div className="document-preview">
                {selectedDoc.storage_error ? (
                  <div className="no-preview storage-error">
                    <span className="preview-icon">⚠️</span>
                    <h3>Document Not Available</h3>
                    <p>{selectedDoc.storage_error_message || 'The document file could not be found in storage.'}</p>
                    <p className="help-text">Please ask the borrower to re-upload this document.</p>
                  </div>
                ) : selectedDoc.file_url || selectedDoc.s3_url ? (
                  <iframe
                    src={selectedDoc.file_url || selectedDoc.s3_url}
                    title={getDocTypeName(selectedDoc.doc_type)}
                    className="pdf-viewer"
                  />
                ) : selectedDoc.status === 'OPEN' || !selectedDoc.filename ? (
                  <div className="no-preview">
                    <span className="preview-icon">📤</span>
                    <h3>Awaiting Upload</h3>
                    <p>This document has been requested but not yet received.</p>
                    {selectedDoc.due_date && (
                      <p className="due-date">Due: {formatDate(selectedDoc.due_date)}</p>
                    )}
                  </div>
                ) : (
                  <div className="no-preview">
                    <span className="preview-icon">📄</span>
                    <h3>Preview Not Available</h3>
                    <p>Click download to view this document.</p>
                    <button
                      className="download-btn"
                      onClick={() => handleDownloadSingle(selectedDoc)}
                    >
                      Download {selectedDoc.filename}
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="no-selection">
              <span className="selection-icon">👈</span>
              <h3>Select a Document</h3>
              <p>Click a document in the sidebar to view details</p>
            </div>
          )}
        </main>
      </div>

      {/* Income Calculator Modal */}
      <IncomeCalculatorModal
        isOpen={showIncomeModal}
        onClose={() => setShowIncomeModal(false)}
        loanId={parseInt(loanId)}
        borrowerId={1}
        borrowerName={client?.name}
        onSave={(income) => {
          console.log('Income saved:', income);
        }}
      />
    </div>
  );
}

export default SmartDocsClientDetail;
