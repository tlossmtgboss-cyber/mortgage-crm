import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../../services/api';
import './PortalDocumentRequirements.css';

/**
 * PortalDocumentRequirements - Borrower-facing document checklist
 *
 * Shows document requirements with status, allows uploads, and tracks progress.
 */
function PortalDocumentRequirements({ workspaceSlug, onProgressUpdate }) {
  const [requirements, setRequirements] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(null);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (workspaceSlug) {
      fetchRequirements();
      fetchSummary();
    }
  }, [workspaceSlug]);

  const fetchRequirements = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/portal/smart-docs/${workspaceSlug}/requirements`);
      if (response.ok) {
        const data = await response.json();
        setRequirements(data.requirements || []);
        if (onProgressUpdate) {
          onProgressUpdate({
            completed: data.completed_count,
            total: data.total_requirements,
            percentage: data.completion_percentage
          });
        }
      }
    } catch (err) {
      console.error('Error fetching requirements:', err);
      setError('Failed to load document requirements');
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/portal/smart-docs/${workspaceSlug}/summary`);
      if (response.ok) {
        const data = await response.json();
        setSummary(data);
      }
    } catch (err) {
      console.error('Error fetching summary:', err);
    }
  };

  const handleUpload = async (requestId, file) => {
    if (!file) return;

    try {
      setUploading(requestId);
      setError(null);

      const formData = new FormData();
      formData.append('file', file);
      formData.append('request_id', requestId);

      const response = await fetch(`${API_BASE_URL}/api/portal/smart-docs/${workspaceSlug}/upload`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        await fetchRequirements();
        await fetchSummary();
      } else {
        const data = await response.json();
        setError(data.detail || 'Upload failed');
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError('Failed to upload document');
    } finally {
      setUploading(null);
    }
  };

  const getStatusIcon = (status) => {
    switch (status.toUpperCase()) {
      case 'ACCEPTED':
      case 'WAIVED':
        return <span className="status-icon completed">✓</span>;
      case 'PENDING_REVIEW':
        return <span className="status-icon pending">⏳</span>;
      case 'REJECTED':
        return <span className="status-icon rejected">✗</span>;
      default:
        return <span className="status-icon open">○</span>;
    }
  };

  const getStatusLabel = (status) => {
    switch (status.toUpperCase()) {
      case 'ACCEPTED': return 'Approved';
      case 'WAIVED': return 'Waived';
      case 'PENDING_REVIEW': return 'Under Review';
      case 'REJECTED': return 'Needs Resubmission';
      default: return 'Needed';
    }
  };

  const getPriorityClass = (priority) => {
    switch (priority.toUpperCase()) {
      case 'CRITICAL': return 'priority-critical';
      case 'HIGH': return 'priority-high';
      case 'LOW': return 'priority-low';
      default: return 'priority-normal';
    }
  };

  if (loading) {
    return (
      <div className="portal-docs-loading">
        <div className="loading-spinner"></div>
        <p>Loading your document checklist...</p>
      </div>
    );
  }

  return (
    <div className="portal-document-requirements">
      {/* Progress Header */}
      {summary && (
        <div className="docs-progress-header">
          <div className="progress-info">
            <h2>Document Checklist</h2>
            <p className="progress-subtitle">
              {summary.completed} of {summary.total_requirements} documents completed
            </p>
          </div>
          <div className="progress-ring">
            <svg viewBox="0 0 36 36" className="circular-progress">
              <path
                className="progress-bg"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                className="progress-fill"
                strokeDasharray={`${summary.completion_percentage}, 100`}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <span className="progress-text">{summary.completion_percentage}%</span>
          </div>
        </div>
      )}

      {/* Overdue Alert */}
      {summary?.overdue_items?.length > 0 && (
        <div className="overdue-alert">
          <span className="alert-icon">⚠️</span>
          <div className="alert-content">
            <strong>{summary.overdue_items.length} document(s) overdue</strong>
            <p>Please submit these documents as soon as possible to avoid delays.</p>
          </div>
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Requirements List */}
      <div className="requirements-list">
        {requirements.length === 0 ? (
          <div className="no-requirements">
            <span className="empty-icon">📋</span>
            <h3>No document requirements yet</h3>
            <p>Your document checklist will appear here once your application is processed.</p>
          </div>
        ) : (
          requirements.map((req) => (
            <div
              key={req.id}
              className={`requirement-card ${req.status.toLowerCase()} ${req.is_overdue ? 'overdue' : ''} ${getPriorityClass(req.priority)}`}
            >
              <div
                className="requirement-header"
                onClick={() => setExpandedId(expandedId === req.id ? null : req.id)}
              >
                <div className="requirement-status">
                  {getStatusIcon(req.status)}
                </div>
                <div className="requirement-info">
                  <h3>{req.title}</h3>
                  <div className="requirement-meta">
                    <span className={`status-badge ${req.status.toLowerCase()}`}>
                      {getStatusLabel(req.status)}
                    </span>
                    {req.is_overdue && (
                      <span className="overdue-badge">Overdue</span>
                    )}
                    {req.due_date && !req.is_overdue && (
                      <span className="due-date">
                        Due: {new Date(req.due_date).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="requirement-expand">
                  <span className={`expand-icon ${expandedId === req.id ? 'expanded' : ''}`}>
                    ▼
                  </span>
                </div>
              </div>

              {expandedId === req.id && (
                <div className="requirement-details">
                  {req.description && (
                    <p className="requirement-description">{req.description}</p>
                  )}
                  {req.instructions && (
                    <div className="requirement-instructions">
                      <strong>Instructions:</strong>
                      <p>{req.instructions}</p>
                    </div>
                  )}

                  {/* Uploaded Documents */}
                  {req.documents?.length > 0 && (
                    <div className="uploaded-documents">
                      <h4>Uploaded Documents</h4>
                      {req.documents.map((doc) => {
                        const statusLower = (doc.status || '').toLowerCase();
                        return (
                          <div key={doc.id} className={`uploaded-doc ${statusLower}`}>
                            <span className="doc-icon">📄</span>
                            <span className="doc-name">{doc.filename}</span>
                            <span className={`doc-status ${statusLower}`}>
                              {statusLower === 'approved' ? '✓ Approved' :
                               statusLower === 'rejected' ? '✗ Rejected' :
                               statusLower === 'deleted' ? '🗑️ Removed' :
                               '⏳ Reviewing'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Upload Section */}
                  {req.status !== 'ACCEPTED' && req.status !== 'WAIVED' && (
                    <div className="upload-section">
                      <input
                        type="file"
                        ref={fileInputRef}
                        style={{ display: 'none' }}
                        accept=".pdf,.png,.jpg,.jpeg,.tiff"
                        onChange={(e) => {
                          if (e.target.files[0]) {
                            handleUpload(req.id, e.target.files[0]);
                            e.target.value = '';
                          }
                        }}
                      />
                      <button
                        className="upload-btn"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading === req.id}
                      >
                        {uploading === req.id ? (
                          <>
                            <span className="btn-spinner"></span>
                            Uploading...
                          </>
                        ) : (
                          <>
                            <span className="upload-icon">📤</span>
                            Upload Document
                          </>
                        )}
                      </button>
                      <p className="upload-hint">
                        Accepted formats: PDF, PNG, JPG, TIFF
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Help Section */}
      <div className="docs-help">
        <h4>Need help?</h4>
        <p>
          If you have questions about any document requirements, please contact your loan officer
          or use the message feature in your portal.
        </p>
      </div>
    </div>
  );
}

export default PortalDocumentRequirements;
