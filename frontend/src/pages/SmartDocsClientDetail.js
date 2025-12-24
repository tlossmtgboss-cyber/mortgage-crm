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
      'gift_letter': 'Gift Letter'
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
                  <span>{getDocTypeName(selectedDoc.doc_type)}</span>
                </div>
                <div className="info-group">
                  <label>Document Date</label>
                  <span>{formatDate(selectedDoc.doc_date)}</span>
                </div>
                <div className="info-group">
                  <label>Expiration</label>
                  <span className={isExpired(selectedDoc) ? 'expired-text' : ''}>
                    {formatDate(selectedDoc.expiration_date)}
                    {isExpired(selectedDoc) && ' (Expired)'}
                  </span>
                </div>
                <div className="info-group">
                  <label>Status</label>
                  <span className={`status-value ${getStatusClass(selectedDoc)}`}>
                    {selectedDoc.status?.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="doc-actions">
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
                </div>
              </div>

              {/* Document Preview */}
              <div className="document-preview">
                {selectedDoc.file_url || selectedDoc.s3_url ? (
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
    </div>
  );
}

export default SmartDocsClientDetail;
