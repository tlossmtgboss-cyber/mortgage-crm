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
import { resendPortalLink } from '../services/docDeliveryApi';
import IncomeCalculatorModal from '../components/income/IncomeCalculatorModal';
import ESignModal from '../components/esign/ESignModal';
import RequestDocumentModal from '../components/smart-docs/RequestDocumentModal';
import SendNeedsListModal from '../components/smart-docs/SendNeedsListModal';
import SendReminderModal from '../components/smart-docs/SendReminderModal';
import './SmartDocsClientDetail.css';
import { toast } from '../utils/toast';

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
  const [editDocTypeValue, setEditDocTypeValue] = useState('');
  const [esignModalOpen, setEsignModalOpen] = useState(false);
  const [selectedDocForEsign, setSelectedDocForEsign] = useState(null);
  const [requestDocModalOpen, setRequestDocModalOpen] = useState(false);
  const [needsListModalOpen, setNeedsListModalOpen] = useState(false);
  const [reminderModalOpen, setReminderModalOpen] = useState(false);
  const [portalLinkDropdownOpen, setPortalLinkDropdownOpen] = useState(false);
  const [portalLinkSending, setPortalLinkSending] = useState(false);

  // Close portal link dropdown on outside click
  useEffect(() => {
    if (!portalLinkDropdownOpen) return;
    const handleClickOutside = (e) => {
      if (!e.target.closest('.portal-link-dropdown-container')) {
        setPortalLinkDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [portalLinkDropdownOpen]);

  // Available document types for dropdown (must match backend DocType enum)
  const DOCUMENT_TYPES = [
    { value: 'PAYSTUB', label: 'Pay Stubs' },
    { value: 'BANK_STATEMENT', label: 'Bank Statements' },
    { value: 'TAX_RETURN', label: 'Tax Returns' },
    { value: 'BUSINESS_TAX_RETURN', label: 'Business Tax Returns' },
    { value: 'W2', label: 'W-2 Forms' },
    { value: 'DRIVERS_LICENSE', label: "Driver's License" },
    { value: 'PURCHASE_CONTRACT', label: 'Purchase Contract' },
    { value: 'GIFT_LETTER', label: 'Gift Letter' },
    { value: 'PROFIT_LOSS', label: 'Profit & Loss Statement' },
    { value: 'BALANCE_SHEET', label: 'Balance Sheet' },
    { value: 'INVESTMENT_STATEMENT', label: 'Investment Statement' },
    { value: 'LOE', label: 'Letter of Explanation' },
    { value: 'LEASE_AGREEMENT', label: 'Lease Agreement' },
    { value: 'FHA_CERT', label: 'FHA Certificate' },
    { value: 'VA_COE', label: 'VA Certificate of Eligibility' },
    { value: 'DD214', label: 'DD-214' },
    { value: 'BANKRUPTCY_DISCHARGE', label: 'Bankruptcy Discharge' },
    { value: 'APPRAISAL', label: 'Appraisal' },
    { value: 'TITLE_REPORT', label: 'Title Report' },
    { value: 'HOMEOWNERS_INSURANCE', label: 'Homeowners Insurance' },
    { value: 'OTHER', label: 'Other' }
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
            stage: needsListData.stage,
            borrowerId: needsListData.borrower_id || null
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
              stage: queueData.stage,
              borrowerId: queueData.borrower_id || (requests[0]?.borrower_id) || null
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
      // Map selected request IDs to actual document IDs
      const documentIds = documents
        .filter(doc => selectedDocs.has(doc.id))
        .map(doc => doc.document_id)
        .filter(Boolean);
      if (documentIds.length === 0) {
        toast.error('No uploaded documents found for the selected items');
        setActionLoading(false);
        return;
      }
      const response = await fetch(`${API_BASE_URL}/api/v1/smart-docs/merge`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          loan_id: loanId,
          document_ids: documentIds
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
      // Map selected request IDs to actual document IDs
      const documentIds = documents
        .filter(doc => selectedDocs.has(doc.id))
        .map(doc => doc.document_id)
        .filter(Boolean);
      if (documentIds.length === 0) {
        toast.error('No uploaded documents found for the selected items');
        setActionLoading(false);
        return;
      }
      await fetch(`${API_BASE_URL}/api/v1/smart-docs/merge-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          loan_id: loanId,
          document_ids: documentIds
        })
      });
      toast.success('Documents merged and email sent!');
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
      toast.success('Document emailed!');
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
        toast.success('Document approved!');
        fetchClientData(); // Refresh data
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to approve document'}`);
      }
    } catch (err) {
      console.error('Error approving document:', err);
      toast.error('Error approving document');
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
        toast.success('Document rejected');
        fetchClientData();
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to reject document'}`);
      }
    } catch (err) {
      console.error('Error rejecting document:', err);
      toast.error('Error rejecting document');
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
        toast.success('Document deleted');
        fetchClientData();
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to delete document'}`);
      }
    } catch (err) {
      console.error('Error deleting document:', err);
      toast.error('Error deleting document');
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
        toast.success('Document re-requested! Borrower will be notified.');
        fetchClientData();
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to re-request document'}`);
      }
    } catch (err) {
      console.error('Error re-requesting document:', err);
      toast.error('Error re-requesting document');
    } finally {
      setActionLoading(false);
    }
  };

  // Update document type
  const handleUpdateDocType = async () => {
    if (!selectedDoc || !editDocTypeValue) return;

    // Need the document_id, not the request id
    const documentId = selectedDoc.document_id;
    if (!documentId) {
      toast.error('Cannot change type: document has not been uploaded yet');
      setEditingDocType(false);
      return;
    }

    setActionLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/document/${documentId}/type`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ doc_type: editDocTypeValue })
        }
      );

      if (response.ok) {
        // Update local state
        setDocuments(prev => prev.map(doc =>
          doc.id === selectedDoc.id
            ? { ...doc, doc_type: editDocTypeValue }
            : doc
        ));
        setSelectedDoc(prev => ({ ...prev, doc_type: editDocTypeValue }));
        setEditingDocType(false);
        toast.success('Document type updated successfully!');
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || 'Failed to update document type'}`);
      }
    } catch (err) {
      console.error('Error updating document type:', err);
      toast.error('Error updating document type');
    } finally {
      setActionLoading(false);
    }
  };

  // Start editing document type
  const startEditDocType = () => {
    setEditDocTypeValue(selectedDoc?.doc_type || '');
    setEditingDocType(true);
  };

  // Cancel editing document type
  const cancelEditDocType = () => {
    setEditingDocType(false);
    setEditDocTypeValue('');
  };

  // Check if document has an uploaded file
  const hasUploadedDocument = (doc) => {
    return doc.document_id || doc.file_url || doc.s3_url || doc.filename || doc.status === 'PENDING_REVIEW';
  };

  // Check if document can be sent for e-sign
  const canSendForEsign = (doc) => {
    const hasFile = doc.file_url || doc.s3_url;
    return hasFile;
  };

  // Handle opening e-sign modal
  const handleOpenEsign = (doc) => {
    setSelectedDocForEsign(doc);
    setEsignModalOpen(true);
  };

  // Handle e-sign success
  const handleEsignSuccess = (envelope) => {
    console.log('E-sign envelope created:', envelope);
    setEsignModalOpen(false);
    setSelectedDocForEsign(null);
    // Refresh to show updated status
    fetchClientData();
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

  // Get document type display name (handles both uppercase and lowercase formats)
  const getDocTypeName = (docType) => {
    if (!docType) return 'Document';

    // Normalize to uppercase for lookup
    const normalizedType = docType.toUpperCase();

    const names = {
      // Uppercase format (new/backend standard)
      'PAYSTUB': 'Pay Stubs',
      'BANK_STATEMENT': 'Bank Statements',
      'TAX_RETURN': 'Tax Returns',
      'BUSINESS_TAX_RETURN': 'Business Tax Returns',
      'W2': 'W-2 Forms',
      'DRIVERS_LICENSE': "Driver's License",
      'PURCHASE_CONTRACT': 'Purchase Contract',
      'GIFT_LETTER': 'Gift Letter',
      'PROFIT_LOSS': 'Profit & Loss Statement',
      'BALANCE_SHEET': 'Balance Sheet',
      'INVESTMENT_STATEMENT': 'Investment Statement',
      'LOE': 'Letter of Explanation',
      'LEASE_AGREEMENT': 'Lease Agreement',
      'FHA_CERT': 'FHA Certificate',
      'VA_COE': 'VA Certificate of Eligibility',
      'DD214': 'DD-214',
      'BANKRUPTCY_DISCHARGE': 'Bankruptcy Discharge',
      'APPRAISAL': 'Appraisal',
      'TITLE_REPORT': 'Title Report',
      'HOMEOWNERS_INSURANCE': 'Homeowners Insurance',
      'HOA': 'HOA Documents',
      'OTHER': 'Other',
      // Legacy lowercase formats
      'PAYSTUBS': 'Pay Stubs',
      'BANK_STATEMENTS': 'Bank Statements',
      'TAX_RETURNS': 'Tax Returns',
      '1099': '1099 Forms',
      'HOA_DOCS': 'HOA Documents'
    };

    return names[normalizedType] || docType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  // Count open documents for delivery actions
  const openDocumentCount = documents.filter((doc) => {
    const status = (doc.status || '').toUpperCase();
    return status === 'OPEN' || status === 'REQUESTED' || status === 'OVERDUE' || status === 'PENDING';
  }).length;

  // Handle resend portal link
  const handleResendPortalLink = async (channel) => {
    setPortalLinkDropdownOpen(false);
    setPortalLinkSending(true);
    try {
      await resendPortalLink(loanId, channel);
      toast.success(`Portal link sent via ${channel}`);
    } catch (err) {
      toast.error(err.message || `Failed to send portal link via ${channel}`);
    } finally {
      setPortalLinkSending(false);
    }
  };

  if (loading) {
    return (
      <div className="client-detail-page">
        <div className="loading-container" role="alert" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p>Loading client documents...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="client-detail-page">
      {/* Header */}
      <header className="client-header">
        <button className="back-btn" onClick={() => navigate('/smart-docs')} aria-label="Back to Smart Docs queue">
          ← Back to Queue
        </button>
        <div className="client-info-header">
          <h1>{client?.name || 'Client'}</h1>
          {client?.email && <span className="client-email">{client.email}</span>}
        </div>
        <div className="header-actions">
          <button
            className="request-doc-btn"
            onClick={() => setRequestDocModalOpen(true)}
            title="Request Document from Borrower"
            aria-label="Request a document from the borrower"
            aria-haspopup="dialog"
          >
            📝 Request Document
          </button>
          {openDocumentCount > 0 && (
            <>
              <button
                className="send-needs-btn"
                onClick={() => setNeedsListModalOpen(true)}
                aria-haspopup="dialog"
                title="Send needs list to borrower"
                aria-label="Send Needs List to borrower"
              >
                📨 Send Needs List
              </button>
              <button
                className="send-reminder-btn"
                onClick={() => setReminderModalOpen(true)}
                title="Send reminder for outstanding documents"
                aria-label="Send Reminder for outstanding documents"
                aria-haspopup="dialog"
              >
                🔔 Send Reminder
              </button>
            </>
          )}
          <div className="portal-link-dropdown-container">
            <button
              className="portal-link-btn"
              onClick={() => setPortalLinkDropdownOpen(!portalLinkDropdownOpen)}
              disabled={portalLinkSending}
              title="Resend borrower portal link"
              aria-label="Portal Link — resend borrower portal link"
              aria-expanded={portalLinkDropdownOpen}
              aria-haspopup="menu"
            >
              {portalLinkSending ? '...' : '🔗 Portal Link'}
            </button>
            {portalLinkDropdownOpen && (
              <div className="portal-link-dropdown">
                <button
                  className="portal-link-option"
                  onClick={() => handleResendPortalLink('email')}
                >
                  ✉️ Send via Email
                </button>
                <button
                  className="portal-link-option"
                  onClick={() => handleResendPortalLink('sms')}
                >
                  📱 Send via SMS
                </button>
              </div>
            )}
          </div>
          <button
            className="income-calc-btn"
            onClick={() => setShowIncomeModal(true)}
            title="Income Calculator"
            aria-label="Open Income Calculator"
            aria-haspopup="dialog"
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

      <div className="client-content" aria-busy={actionLoading}>
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
              <span className="selected-count" aria-live="polite">{selectedDocs.size} selected</span>
              <button
                className="action-btn primary"
                onClick={handleMergeDownload}
                disabled={actionLoading}
                aria-label={`Merge and download ${selectedDocs.size} selected document${selectedDocs.size !== 1 ? 's' : ''}`}
              >
                Merge & Download
              </button>
              <button
                className="action-btn secondary"
                onClick={handleMergeEmail}
                disabled={actionLoading}
                aria-label={`Merge and email ${selectedDocs.size} selected document${selectedDocs.size !== 1 ? 's' : ''}`}
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
                <div className="info-group doc-type-group">
                  <label>Document Type</label>
                  {editingDocType ? (
                    <div className="doc-type-edit">
                      <select
                        value={editDocTypeValue}
                        onChange={(e) => setEditDocTypeValue(e.target.value)}
                        className="doc-type-select"
                      >
                        {DOCUMENT_TYPES.map(type => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                      <button
                        className="edit-btn save-btn"
                        onClick={handleUpdateDocType}
                        disabled={actionLoading}
                        title="Save"
                        aria-label="Save document type change"
                      >
                        ✓
                      </button>
                      <button
                        className="edit-btn cancel-btn"
                        onClick={cancelEditDocType}
                        disabled={actionLoading}
                        title="Cancel"
                        aria-label="Cancel document type edit"
                      >
                        ✗
                      </button>
                    </div>
                  ) : (
                    <div className="doc-type-display">
                      <span>{getDocTypeName(selectedDoc.doc_type)}</span>
                      {hasUploadedDocument(selectedDoc) && (
                        <button
                          className="edit-type-btn"
                          onClick={startEditDocType}
                          title="Change document type"
                          aria-label="Change document type"
                        >
                          ✏️
                        </button>
                      )}
                    </div>
                  )}
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
                  <span
                    className={`status-value ${getStatusClass(selectedDoc)}`}
                    aria-live="polite"
                  >
                    {selectedDoc.status?.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="doc-actions">
                  {/* File actions - only show if document has been uploaded */}
                  {hasUploadedDocument(selectedDoc) && (
                    <>
                      <button
                        className="icon-btn"
                        onClick={() => handleDownloadSingle(selectedDoc)}
                        title="Download"
                        aria-label={`Download ${getDocTypeName(selectedDoc.doc_type)}`}
                      >
                        ⬇️
                      </button>
                      <button
                        className="icon-btn"
                        onClick={() => handleEmailSingle(selectedDoc)}
                        title="Email"
                        aria-label={`Email ${getDocTypeName(selectedDoc.doc_type)}`}
                      >
                        ✉️
                      </button>
                      {canSendForEsign(selectedDoc) && (
                        <button
                          className="esign-btn"
                          onClick={() => handleOpenEsign(selectedDoc)}
                          title="Send for E-Signature"
                          aria-label={`Send ${getDocTypeName(selectedDoc.doc_type)} for E-Signature`}
                          aria-haspopup="dialog"
                        >
                          ✍️ E-Sign
                        </button>
                      )}
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
                      aria-label={`Approve ${getDocTypeName(selectedDoc.doc_type)}`}
                    >
                      ✓ Approve
                    </button>
                    <button
                      className="action-btn reject-btn"
                      onClick={() => handleReject(selectedDoc)}
                      disabled={actionLoading}
                      title="Reject this document"
                      aria-label={`Reject ${getDocTypeName(selectedDoc.doc_type)}`}
                    >
                      ✗ Reject
                    </button>
                    <button
                      className="action-btn delete-btn"
                      onClick={() => handleDelete(selectedDoc)}
                      disabled={actionLoading}
                      title="Delete this document"
                      aria-label={`Delete ${getDocTypeName(selectedDoc.doc_type)}`}
                    >
                      🗑️ Delete
                    </button>
                    <button
                      className="action-btn rerequest-btn"
                      onClick={() => handleReRequest(selectedDoc)}
                      disabled={actionLoading}
                      title="Request a new upload"
                      aria-label={`Re-request ${getDocTypeName(selectedDoc.doc_type)}`}
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
                      aria-label={`Send Reminder to borrower for ${getDocTypeName(selectedDoc.doc_type)}`}
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
                      aria-label={`Download ${selectedDoc.filename || getDocTypeName(selectedDoc.doc_type)}`}
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
        borrowerId={client?.borrowerId}
        borrowerName={client?.name}
        onSave={(income) => {
          console.log('Income saved:', income);
        }}
      />

      {/* E-Sign Modal */}
      <ESignModal
        isOpen={esignModalOpen}
        onClose={() => {
          setEsignModalOpen(false);
          setSelectedDocForEsign(null);
        }}
        document={selectedDocForEsign}
        loanId={loanId}
        borrowerName={client?.name}
        borrowerEmail={client?.email}
        onSuccess={handleEsignSuccess}
      />

      {/* Request Document Modal */}
      <RequestDocumentModal
        isOpen={requestDocModalOpen}
        onClose={() => setRequestDocModalOpen(false)}
        loanId={parseInt(loanId)}
        borrowerId={client?.borrowerId}
        borrowerName={client?.name}
        borrowerEmail={client?.email}
        onSuccess={() => {
          setRequestDocModalOpen(false);
          fetchClientData();
        }}
      />

      {/* Send Needs List Modal */}
      <SendNeedsListModal
        isOpen={needsListModalOpen}
        onClose={() => setNeedsListModalOpen(false)}
        loanId={parseInt(loanId)}
        borrowerName={client?.name}
        loanNumber={client?.loanNumber}
        documentCount={openDocumentCount}
      />

      {/* Send Reminder Modal */}
      <SendReminderModal
        isOpen={reminderModalOpen}
        onClose={() => setReminderModalOpen(false)}
        loanId={parseInt(loanId)}
        borrowerName={client?.name}
        documents={documents}
      />
    </div>
  );
}

export default SmartDocsClientDetail;
