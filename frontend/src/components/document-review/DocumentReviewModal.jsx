/**
 * DocumentReviewModal
 *
 * Split-screen document review interface that appears after document upload.
 * Left side: Document viewer (PDF/images)
 * Right side: Parsed data with comparison to application data
 */

import React, { useState, useEffect, useCallback } from 'react';
import DocumentViewer from './DocumentViewer';
import ParsedDataPanel from './ParsedDataPanel';
import OwnerSelector from './OwnerSelector';
import {
  extractDocumentData,
  getFieldComparison,
  updateDocumentName,
  approveDocument,
  getDocumentDownloadUrl,
} from '../../services/documentReviewApi';
import { getAuthSync } from '../../utils/auth';
import './DocumentReviewModal.css';

const DocumentReviewModal = ({
  documentId,
  loanId,
  borrowerName = '',
  coBorrowerName = '',
  profileType = 'lead',
  profileId,
  onClose,
  onApprove,
  initialDocumentUrl = null,
  initialFileName = '',
}) => {
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState(null);

  const [documentUrl, setDocumentUrl] = useState(initialDocumentUrl);
  const [documentName, setDocumentName] = useState(initialFileName);
  const [mimeType, setMimeType] = useState('application/pdf');

  const [extraction, setExtraction] = useState(null);
  const [comparison, setComparison] = useState(null);

  const [selectedOwner, setSelectedOwner] = useState(null);
  const [fieldSelections, setFieldSelections] = useState({});

  const [saving, setSaving] = useState(false);

  // Load document and trigger extraction
  useEffect(() => {
    loadDocumentAndExtract();
  }, [documentId]);

  const loadDocumentAndExtract = async () => {
    setLoading(true);
    setError(null);

    try {
      // Get document URL if not provided
      if (!documentUrl) {
        const urlResult = await getDocumentDownloadUrl(documentId);
        setDocumentUrl(urlResult.download_url);
        setDocumentName(urlResult.file_name || initialFileName);
        setMimeType(urlResult.content_type || 'application/pdf');
      }

      // Trigger extraction
      setExtracting(true);
      const extractResult = await extractDocumentData(documentId);
      setExtraction(extractResult);

      // Set suggested owner
      if (extractResult.detected_owner && extractResult.detected_owner !== 'UNKNOWN') {
        setSelectedOwner(extractResult.detected_owner);
      }

      // Get comparison data
      const comparisonResult = await getFieldComparison(
        documentId,
        profileType,
        profileId || loanId
      );
      setComparison(comparisonResult);

      setExtracting(false);
    } catch (err) {
      console.error('Failed to load document:', err);
      setError(err.message);
      setExtracting(false);
    } finally {
      setLoading(false);
    }
  };

  // Handle field action selection
  const handleFieldAction = useCallback((fieldName, action) => {
    setFieldSelections(prev => ({
      ...prev,
      [fieldName]: action,
    }));
  }, []);

  // Handle document name change
  const handleNameChange = async (newName) => {
    setDocumentName(newName);
    try {
      await updateDocumentName(documentId, newName);
    } catch (err) {
      console.error('Failed to update name:', err);
    }
  };

  // Handle approve
  const handleApprove = async (applySelectedFields = false) => {
    setSaving(true);
    setError(null);

    try {
      // Get current user from auth context
      const { user } = getAuthSync();
      const reviewerName = user?.name || user?.email?.split('@')[0] || 'user';

      const options = {
        reviewer: reviewerName,
        assignedOwner: selectedOwner,
      };

      if (applySelectedFields && Object.keys(fieldSelections).length > 0) {
        const fieldsToApply = Object.entries(fieldSelections)
          .filter(([_, action]) => action !== 'ignore' && action !== 'keep')
          .map(([fieldName, action]) => ({
            field_name: fieldName,
            action: action === 'replace' || action === 'add' ? action : 'add',
            value: extraction?.extracted_fields?.[fieldName],
          }));

        if (fieldsToApply.length > 0) {
          options.applyFields = {
            profile_type: profileType,
            profile_id: profileId || loanId,
            fields_to_apply: fieldsToApply,
          };
        }
      }

      await approveDocument(documentId, options);

      if (onApprove) {
        onApprove({ documentId, appliedFields: options.applyFields });
      }

      onClose();
    } catch (err) {
      console.error('Failed to approve:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Handle reject
  const handleReject = () => {
    // For now, just close. Could add rejection flow later.
    onClose();
  };

  // Count selected fields
  const selectedFieldCount = Object.values(fieldSelections).filter(
    action => action === 'add' || action === 'replace'
  ).length;

  return (
    <div className="document-review-overlay" onClick={onClose}>
      <div className="document-review-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <header className="review-header">
          <div className="header-left">
            <input
              type="text"
              className="document-name-input"
              value={documentName}
              onChange={e => handleNameChange(e.target.value)}
              placeholder="Document name..."
            />
          </div>

          <div className="header-center">
            <OwnerSelector
              borrowerName={borrowerName}
              coBorrowerName={coBorrowerName}
              selectedOwner={selectedOwner}
              suggestedOwner={extraction?.detected_owner}
              ownerConfidence={extraction?.owner_confidence}
              onChange={setSelectedOwner}
            />
          </div>

          <div className="header-right">
            <button className="close-btn" onClick={onClose} title="Close">
              &times;
            </button>
          </div>
        </header>

        {/* Error display */}
        {error && (
          <div className="review-error">
            <span className="error-icon">!</span>
            <span>{error}</span>
            <button onClick={() => setError(null)}>&times;</button>
          </div>
        )}

        {/* Main content */}
        <div className="review-content">
          {/* Left: Document Viewer */}
          <div className="document-pane">
            {loading && !documentUrl ? (
              <div className="loading-placeholder">
                <div className="spinner" />
                <p>Loading document...</p>
              </div>
            ) : (
              <DocumentViewer
                documentUrl={documentUrl}
                mimeType={mimeType}
                fileName={documentName}
              />
            )}
          </div>

          {/* Divider */}
          <div className="pane-divider" />

          {/* Right: Parsed Data */}
          <div className="data-pane">
            {extracting ? (
              <div className="extracting-placeholder">
                <div className="spinner" />
                <p>Analyzing document...</p>
                <p className="extracting-hint">
                  Extracting data and detecting owner
                </p>
              </div>
            ) : extraction ? (
              <ParsedDataPanel
                extraction={extraction}
                comparison={comparison}
                fieldSelections={fieldSelections}
                onFieldAction={handleFieldAction}
              />
            ) : (
              <div className="no-extraction">
                <p>No data extracted</p>
                <button onClick={loadDocumentAndExtract}>
                  Retry Extraction
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Footer / Action Bar */}
        <footer className="review-footer">
          <div className="footer-left">
            {extraction && (
              <span className="confidence-badge">
                Confidence: {extraction.overall_confidence || 0}%
              </span>
            )}
          </div>

          <div className="footer-actions">
            <button
              className="btn btn-secondary"
              onClick={handleReject}
              disabled={saving}
            >
              Reject
            </button>

            <button
              className="btn btn-primary"
              onClick={() => handleApprove(false)}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Approve'}
            </button>

            {selectedFieldCount > 0 && (
              <button
                className="btn btn-success"
                onClick={() => handleApprove(true)}
                disabled={saving}
              >
                {saving ? 'Saving...' : `Approve & Apply (${selectedFieldCount})`}
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
};

export default DocumentReviewModal;
