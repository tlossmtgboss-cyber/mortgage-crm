/**
 * SmartDocumentUpload Component
 *
 * Drag-and-drop document upload with real-time processing feedback.
 * Shows screenshot detection and freshness validation results.
 */

import React, { useState, useCallback, useRef } from 'react';
import { smartDocsAPI } from '../../services/smartDocsApi';
import RejectionExplainer from './RejectionExplainer';
import FreshnessIndicator from './FreshnessIndicator';
import './SmartDocumentUpload.css';

const SmartDocumentUpload = ({
  loanId,
  borrowerId,
  requestId = null,
  docType = null,
  onUploadComplete,
  onUploadError,
  maxSizeMB = 20,
  acceptedTypes = '.pdf,.jpg,.jpeg,.png,.gif,.tiff',
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadState, setUploadState] = useState('idle'); // idle, uploading, processing, complete, error
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  const maxSizeBytes = maxSizeMB * 1024 * 1024;

  const validateFile = (file) => {
    // Check size
    if (file.size > maxSizeBytes) {
      return `File is too large. Maximum size is ${maxSizeMB}MB.`;
    }

    // Check type
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    const acceptedList = acceptedTypes.split(',');
    if (!acceptedList.includes(extension)) {
      return `File type not accepted. Please upload: ${acceptedTypes}`;
    }

    return null;
  };

  const handleUpload = useCallback(async (file) => {
    setSelectedFile(file);
    setError(null);
    setUploadResult(null);

    // Validate
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setUploadState('error');
      return;
    }

    try {
      setUploadState('uploading');

      // Upload and process
      const result = await smartDocsAPI.uploadDocument(
        file,
        loanId,
        borrowerId,
        requestId,
        docType
      );

      setUploadState('complete');
      setUploadResult(result);

      if (onUploadComplete) {
        onUploadComplete(result);
      }
    } catch (err) {
      setUploadState('error');
      setError(err.message || 'Upload failed');
      if (onUploadError) {
        onUploadError(err);
      }
    }
  }, [loanId, borrowerId, requestId, docType, maxSizeBytes, onUploadComplete, onUploadError]);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleUpload(files[0]);
    }
  };

  const handleFileSelect = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleUpload(files[0]);
    }
  };

  const handleReset = () => {
    setUploadState('idle');
    setUploadResult(null);
    setError(null);
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Render based on state
  if (uploadState === 'complete' && uploadResult) {
    return (
      <div className="upload-result">
        <UploadResultDisplay result={uploadResult} />
        <button className="upload-another-btn" onClick={handleReset}>
          Upload Another Document
        </button>
      </div>
    );
  }

  return (
    <div className="smart-document-upload">
      <div
        className={`drop-zone ${isDragging ? 'dragging' : ''} ${uploadState === 'error' ? 'error' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => uploadState === 'idle' && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={acceptedTypes}
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        {uploadState === 'idle' && (
          <>
            <div className="drop-icon">📄</div>
            <p className="drop-text">
              Drag & drop your document here
            </p>
            <p className="drop-hint">
              or click to browse
            </p>
            <p className="file-types">
              Accepted: PDF, JPG, PNG (max {maxSizeMB}MB)
            </p>
          </>
        )}

        {uploadState === 'uploading' && (
          <div className="upload-progress">
            <div className="spinner" />
            <p>Uploading {selectedFile?.name}...</p>
          </div>
        )}

        {uploadState === 'processing' && (
          <div className="upload-progress">
            <div className="spinner" />
            <p>Analyzing document...</p>
            <ul className="processing-steps">
              <li className="complete">✓ Screenshot detection</li>
              <li className="active">○ Date extraction</li>
              <li>○ Freshness validation</li>
            </ul>
          </div>
        )}

        {uploadState === 'error' && (
          <div className="upload-error">
            <span className="error-icon">⚠️</span>
            <p>{error}</p>
            <button onClick={handleReset}>Try Again</button>
          </div>
        )}
      </div>

      {/* Guidelines */}
      <div className="upload-guidelines">
        <h4>Document Guidelines</h4>
        <ul>
          <li>
            <span className="check">✓</span>
            Upload the original PDF document (not a screenshot)
          </li>
          <li>
            <span className="check">✓</span>
            Ensure all pages are included
          </li>
          <li>
            <span className="check">✓</span>
            Document must be dated within the required freshness period
          </li>
          <li>
            <span className="warning">⚠️</span>
            Screenshots will be automatically rejected
          </li>
        </ul>
      </div>
    </div>
  );
};

/**
 * Display upload result with decision details
 */
const UploadResultDisplay = ({ result }) => {
  const isAccepted = result.status === 'APPROVED';
  const isRejected = result.status === 'REJECTED';
  const needsReview = result.status === 'NEEDS_REVIEW';

  return (
    <div className={`result-container ${result.status?.toLowerCase()}`}>
      {/* Status Header */}
      <div className="result-header">
        {isAccepted && (
          <>
            <span className="status-icon success">✓</span>
            <h3>Document Accepted</h3>
          </>
        )}
        {isRejected && (
          <>
            <span className="status-icon error">✗</span>
            <h3>Document Rejected</h3>
          </>
        )}
        {needsReview && (
          <>
            <span className="status-icon warning">!</span>
            <h3>Review Required</h3>
          </>
        )}
      </div>

      {/* Rejection Details */}
      {isRejected && result.rejection_reason && (
        <RejectionExplainer
          category={result.rejection_category}
          reason={result.rejection_reason}
          fixInstructions={result.fix_instructions}
        />
      )}

      {/* Analysis Details */}
      <div className="analysis-details">
        {/* Screenshot Detection */}
        {result.analysis?.screenshot && (
          <div className="analysis-item">
            <h4>Screenshot Detection</h4>
            <div className={`detection-result ${result.analysis.screenshot.is_screenshot ? 'detected' : 'clear'}`}>
              {result.analysis.screenshot.is_screenshot ? (
                <span>⚠️ Screenshot detected ({Math.round(result.analysis.screenshot.confidence * 100)}% confidence)</span>
              ) : (
                <span>✓ Original document</span>
              )}
            </div>
          </div>
        )}

        {/* Date Extraction */}
        {result.analysis?.dates && (
          <div className="analysis-item">
            <h4>Date Information</h4>
            {result.analysis.dates.primary_date ? (
              <div className="date-info">
                <span className="date-label">Document Date:</span>
                <span className="date-value">{formatDate(result.analysis.dates.primary_date)}</span>
              </div>
            ) : (
              <span className="no-date">No date detected</span>
            )}
          </div>
        )}

        {/* Freshness */}
        {result.analysis?.freshness && (
          <div className="analysis-item">
            <h4>Freshness</h4>
            <FreshnessIndicator
              status={result.analysis.freshness.status}
              daysUntilExpiration={result.analysis.freshness.days_until_expiration}
              expiresAt={result.analysis.freshness.expires_at}
            />
          </div>
        )}
      </div>
    </div>
  );
};

function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

export default SmartDocumentUpload;
