/**
 * SmartDocumentUpload Component
 *
 * Drag-and-drop document upload with real-time processing feedback.
 * Shows screenshot detection and freshness validation results.
 * Opens DocumentReviewModal for AI extraction and data comparison.
 *
 * Supports multi-file upload with real XHR progress tracking and
 * concurrent upload queue (max 3 simultaneous uploads).
 */

import React, { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../../services/api';
import { getToken } from '../../utils/tokenStore';
import { smartDocsAPI } from '../../services/smartDocsApi';
import RejectionExplainer from './RejectionExplainer';
import FreshnessIndicator from './FreshnessIndicator';
import DocumentReviewModal from '../document-review/DocumentReviewModal';
import './SmartDocumentUpload.css';

const SMART_DOCS_API = `${API_BASE_URL}/api/v1/smart-docs`;
const MAX_CONCURRENT = 3;

/**
 * Upload a single file using XMLHttpRequest for real progress events.
 * Returns a promise that resolves with the parsed JSON response.
 */
function uploadFileWithProgress(file, loanId, borrowerId, requestId, docType, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('loan_id', loanId);
    formData.append('borrower_id', borrowerId);
    if (requestId) formData.append('request_id', requestId);
    if (docType) formData.append('doc_type', docType);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          const detail = data.detail;
          let message;
          if (Array.isArray(detail)) {
            message = detail.map(d => d.msg || JSON.stringify(d)).join('; ');
          } else if (typeof detail === 'object' && detail !== null) {
            message = detail.msg || JSON.stringify(detail);
          } else {
            message = detail || 'Upload failed';
          }
          reject(new Error(message));
        }
      } catch {
        reject(new Error('Upload failed: invalid response'));
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.onabort = () => reject(new Error('Upload cancelled'));

    xhr.open('POST', `${SMART_DOCS_API}/upload`);
    const token = getToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.send(formData);
  });
}

const SmartDocumentUpload = ({
  loanId,
  borrowerId,
  requestId = null,
  docType = null,
  onUploadComplete,
  onUploadError,
  onDocumentApproved,
  maxSizeMB = 20,
  acceptedTypes = '.pdf,.jpg,.jpeg,.png,.gif,.tiff',
  // Profile info for comparison
  profileType = 'loan', // 'lead' or 'loan'
  profileId = null,
  borrowerName = '',
  coBorrowerName = '',
  // Auto-open review modal
  autoOpenReview = true,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadState, setUploadState] = useState('idle'); // idle, uploading, processing, complete, error
  // Multi-file: array of { id, file, progress, status, result, error }
  const [fileQueue, setFileQueue] = useState([]);
  const [completedResults, setCompletedResults] = useState([]);
  const [error, setError] = useState(null);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewDocumentId, setReviewDocumentId] = useState(null);
  const [statusAnnouncement, setStatusAnnouncement] = useState('');
  const fileInputRef = useRef(null);
  const nextIdRef = useRef(0);

  const maxSizeBytes = maxSizeMB * 1024 * 1024;

  const validateFile = (file) => {
    if (file.size > maxSizeBytes) {
      return `File "${file.name}" is too large. Maximum size is ${maxSizeMB}MB.`;
    }
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    const acceptedList = acceptedTypes.split(',');
    if (!acceptedList.includes(extension)) {
      return `File "${file.name}" type not accepted. Please upload: ${acceptedTypes}`;
    }
    return null;
  };

  /**
   * Process the upload queue with max concurrency.
   */
  const processQueue = useCallback(async (items) => {
    setUploadState('uploading');
    setStatusAnnouncement(`Uploading ${items.length} file${items.length > 1 ? 's' : ''}...`);

    const results = [];
    let activeCount = 0;
    let index = 0;

    const uploadNext = () => {
      return new Promise((resolveAll) => {
        const checkDone = () => {
          if (results.length === items.length) resolveAll();
        };

        const startOne = async () => {
          if (index >= items.length) {
            checkDone();
            return;
          }
          const i = index++;
          const item = items[i];
          activeCount++;

          setFileQueue(prev => prev.map(f =>
            f.id === item.id ? { ...f, status: 'uploading' } : f
          ));

          try {
            const result = await uploadFileWithProgress(
              item.file, loanId, borrowerId, requestId, docType,
              (progress) => {
                setFileQueue(prev => prev.map(f =>
                  f.id === item.id ? { ...f, progress } : f
                ));
              }
            );

            setFileQueue(prev => prev.map(f =>
              f.id === item.id ? { ...f, status: 'complete', progress: 100, result } : f
            ));
            setStatusAnnouncement(`${item.file.name} uploaded successfully.`);
            results.push({ item, result, success: true });
          } catch (err) {
            setFileQueue(prev => prev.map(f =>
              f.id === item.id ? { ...f, status: 'error', error: err.message } : f
            ));
            setStatusAnnouncement(`${item.file.name} upload failed: ${err.message}`);
            results.push({ item, error: err, success: false });
          } finally {
            activeCount--;
            startOne();
            checkDone();
          }
        };

        // Kick off up to MAX_CONCURRENT
        const initialBatch = Math.min(MAX_CONCURRENT, items.length);
        for (let c = 0; c < initialBatch; c++) {
          startOne();
        }
      });
    };

    await uploadNext();

    const successResults = results.filter(r => r.success).map(r => r.result);
    const failedResults = results.filter(r => !r.success);

    setCompletedResults(successResults);

    if (failedResults.length === results.length) {
      setUploadState('error');
      setError(`All ${failedResults.length} upload(s) failed.`);
      setStatusAnnouncement(`All uploads failed.`);
    } else if (failedResults.length > 0) {
      setUploadState('complete');
      setStatusAnnouncement(`${successResults.length} uploaded, ${failedResults.length} failed.`);
    } else {
      setUploadState('complete');
      setStatusAnnouncement(`All ${successResults.length} file${successResults.length > 1 ? 's' : ''} uploaded successfully.`);
    }

    // Auto-open review for single successful upload
    if (autoOpenReview && successResults.length === 1 && successResults[0].document_id) {
      setReviewDocumentId(successResults[0].document_id);
      setShowReviewModal(true);
    }

    if (onUploadComplete && successResults.length > 0) {
      successResults.forEach(r => onUploadComplete(r));
    }
    if (onUploadError && failedResults.length > 0) {
      failedResults.forEach(r => onUploadError(r.error));
    }
  }, [loanId, borrowerId, requestId, docType, autoOpenReview, onUploadComplete, onUploadError]);

  const handleFilesSelected = useCallback((fileList) => {
    setError(null);

    const newItems = [];
    const validationErrors = [];
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const validationError = validateFile(file);
      if (validationError) {
        validationErrors.push(validationError);
        continue;
      }
      newItems.push({
        id: nextIdRef.current++,
        file,
        progress: 0,
        status: 'pending', // pending, uploading, complete, error
        result: null,
        error: null,
      });
    }

    if (validationErrors.length > 0 && newItems.length === 0) {
      setError(validationErrors.join(' '));
      setUploadState('error');
      return;
    }

    if (validationErrors.length > 0) {
      setError(validationErrors.join(' '));
    }

    if (newItems.length > 0) {
      setFileQueue(newItems);
      setCompletedResults([]);
      processQueue(newItems);
    }
  }, [processQueue]);

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
      handleFilesSelected(files);
    }
  };

  const handleFileSelect = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFilesSelected(files);
    }
    // Reset input so the same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDropzoneKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (uploadState === 'idle') fileInputRef.current?.click();
    }
  };

  const handleReset = () => {
    setUploadState('idle');
    setFileQueue([]);
    setCompletedResults([]);
    setError(null);
    setShowReviewModal(false);
    setReviewDocumentId(null);
    setStatusAnnouncement('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleCloseReviewModal = () => {
    setShowReviewModal(false);
    setReviewDocumentId(null);
  };

  const handleDocumentApproved = (approvalResult) => {
    setShowReviewModal(false);
    setReviewDocumentId(null);

    if (onDocumentApproved) {
      onDocumentApproved(approvalResult);
    }
  };

  const handleOpenReview = (documentId) => {
    if (documentId) {
      setReviewDocumentId(documentId);
      setShowReviewModal(true);
    }
  };

  const isUploading = uploadState === 'uploading';

  // Render based on state
  if (uploadState === 'complete' && completedResults.length > 0) {
    return (
      <>
        <div className="upload-result" aria-live="polite">
          {completedResults.map((result, idx) => (
            <div key={idx} className="upload-result-item">
              <UploadResultDisplay result={result} />
              <div className="upload-result-actions">
                {result.document_id && (
                  <button
                    className="review-document-btn"
                    onClick={() => handleOpenReview(result.document_id)}
                    aria-label={`Review and extract data from ${result.file_name || 'uploaded document'}`}
                  >
                    Review & Extract Data
                  </button>
                )}
              </div>
            </div>
          ))}
          {/* Show any files that failed */}
          {fileQueue.filter(f => f.status === 'error').map(f => (
            <div key={f.id} className="upload-result-item upload-result-item--error">
              <span className="error-icon">⚠️</span>
              <span>{f.file.name}: {f.error}</span>
            </div>
          ))}
          <div className="upload-result-actions">
            <button
              className="upload-another-btn"
              onClick={handleReset}
              aria-label="Upload more documents"
            >
              Upload More Documents
            </button>
          </div>
        </div>

        {/* Document Review Modal */}
        {showReviewModal && reviewDocumentId && (
          <DocumentReviewModal
            documentId={reviewDocumentId}
            loanId={loanId}
            borrowerName={borrowerName}
            coBorrowerName={coBorrowerName}
            profileType={profileType}
            profileId={profileId || loanId}
            onClose={handleCloseReviewModal}
            onApprove={handleDocumentApproved}
            initialFileName={completedResults[0]?.file_name}
          />
        )}
      </>
    );
  }

  return (
    <div className="smart-document-upload" aria-busy={isUploading}>
      {/* Live region for status announcements */}
      <div
        className="sr-only"
        aria-live="polite"
        aria-atomic="true"
        role="status"
      >
        {statusAnnouncement}
      </div>

      <div
        className={`drop-zone ${isDragging ? 'dragging' : ''} ${uploadState === 'error' ? 'error' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => uploadState === 'idle' && fileInputRef.current?.click()}
        onKeyDown={handleDropzoneKeyDown}
        role="button"
        tabIndex={0}
        aria-label="Upload documents. Drag and drop files here or click to browse."
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={acceptedTypes}
          multiple
          onChange={handleFileSelect}
          style={{ display: 'none' }}
          aria-hidden="true"
        />

        {uploadState === 'idle' && (
          <>
            <div className="drop-icon" aria-hidden="true">📄</div>
            <p className="drop-text">
              Drag & drop your documents here
            </p>
            <p className="drop-hint">
              or click to browse (multiple files supported)
            </p>
            <p className="file-types">
              Accepted: PDF, JPG, PNG (max {maxSizeMB}MB each)
            </p>
          </>
        )}

        {uploadState === 'uploading' && (
          <div className="upload-progress-list" role="group" aria-label="Upload progress">
            {fileQueue.map(item => (
              <div key={item.id} className="upload-file-progress">
                <div className="upload-file-info">
                  <span className="upload-file-name">{item.file.name}</span>
                  <span className="upload-file-status">
                    {item.status === 'pending' && 'Waiting...'}
                    {item.status === 'uploading' && `${item.progress}%`}
                    {item.status === 'complete' && 'Done'}
                    {item.status === 'error' && 'Failed'}
                  </span>
                </div>
                <div
                  className={`progress-bar-track ${item.status === 'error' ? 'progress-bar-track--error' : ''} ${item.status === 'complete' ? 'progress-bar-track--complete' : ''}`}
                  role="progressbar"
                  aria-valuenow={item.progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`Upload progress for ${item.file.name}: ${item.progress}%`}
                >
                  <div
                    className="progress-bar-fill"
                    style={{ width: `${item.progress}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {uploadState === 'processing' && (
          <div className="upload-progress">
            <div className="spinner" aria-hidden="true" />
            <p>Analyzing document...</p>
            <ul className="processing-steps" aria-label="Processing steps">
              <li className="complete">✓ Screenshot detection</li>
              <li className="active">○ Date extraction</li>
              <li>○ Freshness validation</li>
            </ul>
          </div>
        )}

        {uploadState === 'error' && (
          <div className="upload-error" role="alert">
            <span className="error-icon" aria-hidden="true">⚠️</span>
            <p>{error}</p>
            <button onClick={handleReset} aria-label="Dismiss error and try uploading again">
              Try Again
            </button>
          </div>
        )}
      </div>

      {/* Guidelines */}
      <div className="upload-guidelines" aria-label="Document upload guidelines">
        <h4>Document Guidelines</h4>
        <ul>
          <li>
            <span className="check" aria-hidden="true">✓</span>
            Upload the original PDF document (not a screenshot)
          </li>
          <li>
            <span className="check" aria-hidden="true">✓</span>
            Ensure all pages are included
          </li>
          <li>
            <span className="check" aria-hidden="true">✓</span>
            Document must be dated within the required freshness period
          </li>
          <li>
            <span className="warning" aria-hidden="true">⚠️</span>
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
