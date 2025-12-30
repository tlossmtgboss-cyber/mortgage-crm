/**
 * LoanSmartDocsTab - Combined document list and upload for loan details page
 *
 * Displays documents from the needs-list API and allows uploading new documents.
 * Links to the full Smart Docs client detail page for advanced features.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { API_BASE_URL } from '../../services/api';
import SmartDocumentUpload from './SmartDocumentUpload';
import './LoanSmartDocsTab.css';

const STATUS_COLORS = {
  ACCEPTED: { bg: '#e6f4ea', color: '#1e7e34', label: 'Accepted' },
  PENDING_REVIEW: { bg: '#fff3cd', color: '#856404', label: 'Pending Review' },
  REJECTED: { bg: '#f8d7da', color: '#721c24', label: 'Rejected' },
  OPEN: { bg: '#e2e3e5', color: '#383d41', label: 'Open' },
  WAIVED: { bg: '#d1ecf1', color: '#0c5460', label: 'Waived' },
};

function LoanSmartDocsTab({ loanId, borrowerId, borrowerName, coBorrowerName }) {
  const [loading, setLoading] = useState(true);
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState(null);

  const fetchDocuments = useCallback(async () => {
    if (!loanId) return;

    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      // Try needs-list endpoint first
      const response = await fetch(
        `${API_BASE_URL}/api/v1/smart-docs/needs-list/${loanId}`,
        { headers }
      );

      if (response.ok) {
        const data = await response.json();
        setDocuments(data.all_requests || []);
      } else {
        // Fallback to queue endpoint
        const queueResponse = await fetch(
          `${API_BASE_URL}/api/v1/smart-docs/queue/${loanId}`,
          { headers }
        );

        if (queueResponse.ok) {
          const queueData = await queueResponse.json();
          setDocuments(queueData.requests || queueData.all_requests || []);
        } else {
          setError('Unable to load documents');
        }
      }
    } catch (err) {
      console.error('Error fetching smart docs:', err);
      setError('Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUploadComplete = (result) => {
    console.log('Document uploaded:', result);
    // Refresh document list
    fetchDocuments();
  };

  const getStatusStyle = (status) => {
    return STATUS_COLORS[status] || STATUS_COLORS.OPEN;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString();
  };

  const getDocumentUrl = (doc) => {
    return doc.file_url || doc.s3_url || doc.document_url;
  };

  if (loading) {
    return (
      <div className="loan-smart-docs-tab">
        <div className="smart-docs-loading">Loading documents...</div>
      </div>
    );
  }

  return (
    <div className="loan-smart-docs-tab">
      {/* Header with link to full Smart Docs page */}
      <div className="smart-docs-header">
        <div className="header-left">
          <h3>Smart Documents</h3>
          <p className="description">
            Upload and manage loan documents. AI-powered extraction automatically parses document data.
          </p>
        </div>
        <Link
          to={`/smart-docs/client/${loanId}`}
          className="btn-view-all"
        >
          Open Full View →
        </Link>
      </div>

      {error && (
        <div className="smart-docs-error">
          {error}
          <button onClick={fetchDocuments}>Retry</button>
        </div>
      )}

      {/* Document List */}
      {documents.length > 0 ? (
        <div className="smart-docs-list">
          <div className="docs-list-header">
            <span className="col-type">Document Type</span>
            <span className="col-date">Date</span>
            <span className="col-expiry">Expiration</span>
            <span className="col-status">Status</span>
            <span className="col-actions">Actions</span>
          </div>

          {documents.map((doc) => {
            const statusStyle = getStatusStyle(doc.status);
            const docUrl = getDocumentUrl(doc);

            return (
              <div key={doc.id} className="docs-list-row">
                <span className="col-type">
                  <strong>{doc.doc_type || doc.document_type || 'Document'}</strong>
                  {doc.file_name && (
                    <span className="file-name">{doc.file_name}</span>
                  )}
                </span>
                <span className="col-date">
                  {formatDate(doc.doc_date || doc.uploaded_at)}
                </span>
                <span className="col-expiry">
                  {doc.expiration_date ? formatDate(doc.expiration_date) : 'N/A'}
                </span>
                <span className="col-status">
                  <span
                    className="status-badge"
                    style={{
                      backgroundColor: statusStyle.bg,
                      color: statusStyle.color
                    }}
                  >
                    {statusStyle.label}
                  </span>
                </span>
                <span className="col-actions">
                  {docUrl && (
                    <a
                      href={docUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-view-doc"
                    >
                      View
                    </a>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="smart-docs-empty">
          <p>No documents uploaded yet.</p>
        </div>
      )}

      {/* Upload Section */}
      <div className="smart-docs-upload-section">
        <h4>Upload Document</h4>
        <SmartDocumentUpload
          loanId={parseInt(loanId)}
          borrowerId={borrowerId}
          profileType="loan"
          profileId={parseInt(loanId)}
          borrowerName={borrowerName || ''}
          coBorrowerName={coBorrowerName || ''}
          autoOpenReview={true}
          onUploadComplete={handleUploadComplete}
        />
      </div>
    </div>
  );
}

export default LoanSmartDocsTab;
