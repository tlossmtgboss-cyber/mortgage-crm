import React, { useState, useRef, useCallback } from 'react';
import './MortgageStatementUpload.css';

/**
 * MortgageStatementUpload - AI-powered mortgage statement parser
 *
 * Allows users to upload their mortgage statement (PDF or image) and
 * automatically extracts key information to pre-populate the refinance form.
 */
const MortgageStatementUpload = ({ onDataExtracted, apiUrl }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const fileInputRef = useRef(null);

  const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
  const maxFileSize = 10 * 1024 * 1024; // 10MB

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const validateFile = (file) => {
    if (!allowedTypes.includes(file.type)) {
      return 'Please upload a PDF or image file (PNG, JPG)';
    }
    if (file.size > maxFileSize) {
      return 'File is too large. Maximum size is 10MB.';
    }
    return null;
  };

  const uploadAndParse = async (file) => {
    setIsUploading(true);
    setUploadProgress(0);
    setError(null);
    setParsedData(null);

    try {
      // Simulate progress for better UX
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 10, 90));
      }, 200);

      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${apiUrl}/api/v1/borrower-auth/parse-mortgage-statement`, {
        method: 'POST',
        body: formData,
      });

      clearInterval(progressInterval);
      setUploadProgress(100);

      const result = await response.json();

      if (!response.ok || !result.success) {
        throw new Error(result.detail || result.error || 'Failed to parse mortgage statement');
      }

      setParsedData(result);
      setShowPreview(true);

    } catch (err) {
      setError(err.message || 'An error occurred while processing your document');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      uploadAndParse(file);
    }
  }, [apiUrl]);

  const handleFileSelect = (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      const file = files[0];
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      uploadAndParse(file);
    }
  };

  const handleUseData = () => {
    if (parsedData && parsedData.form_data) {
      onDataExtracted(parsedData.form_data);
      setShowPreview(false);
      setParsedData(null);
    }
  };

  const handleSkip = () => {
    setShowPreview(false);
    setParsedData(null);
  };

  const formatCurrency = (value) => {
    if (!value && value !== 0) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  // Preview component showing parsed data
  if (showPreview && parsedData) {
    const data = parsedData.form_data || {};
    const confidence = Math.round((parsedData.confidence || 0) * 100);

    return (
      <div className="mortgage-statement-preview">
        <div className="preview-header">
          <div className="preview-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <h3>Statement Parsed Successfully!</h3>
          <p className="confidence-badge">
            {confidence}% confidence
          </p>
        </div>

        {parsedData.warnings && parsedData.warnings.length > 0 && (
          <div className="preview-warnings">
            {parsedData.warnings.map((warning, idx) => (
              <p key={idx}>{warning}</p>
            ))}
          </div>
        )}

        <div className="preview-data">
          <h4>We found the following information:</h4>

          <div className="data-section">
            <h5>Property</h5>
            <p className="data-value">{data.address || 'Not found'}</p>
          </div>

          <div className="data-grid">
            <div className="data-item">
              <span className="data-label">Current Balance</span>
              <span className="data-value highlight">{formatCurrency(data.mortgageBalance)}</span>
            </div>
            <div className="data-item">
              <span className="data-label">Monthly Payment</span>
              <span className="data-value highlight">{formatCurrency(data.monthlyPayment)}</span>
            </div>
            <div className="data-item">
              <span className="data-label">Interest Rate</span>
              <span className="data-value highlight">{data.currentRate ? `${data.currentRate}%` : '-'}</span>
            </div>
            <div className="data-item">
              <span className="data-label">Loan Term</span>
              <span className="data-value">{data.currentTerm ? `${data.currentTerm} Year` : '-'}</span>
            </div>
          </div>

          {data.lenderName && (
            <div className="data-section">
              <h5>Lender</h5>
              <p className="data-value">{data.lenderName}</p>
            </div>
          )}
        </div>

        <div className="preview-actions">
          <button className="btn-use-data" onClick={handleUseData}>
            Use This Information
          </button>
          <button className="btn-skip" onClick={handleSkip}>
            Enter Manually Instead
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mortgage-statement-upload">
      <div className="upload-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="15" y2="15" />
          </svg>
        </div>
        <div className="header-text">
          <h3>Have your mortgage statement handy?</h3>
          <p>Upload it and we'll fill in the details for you automatically</p>
        </div>
      </div>

      <div
        className={`upload-zone ${isDragging ? 'dragging' : ''} ${isUploading ? 'uploading' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        {isUploading ? (
          <div className="upload-progress">
            <div className="progress-spinner" />
            <p>Analyzing your statement...</p>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
          </div>
        ) : (
          <>
            <div className="upload-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p className="upload-text">
              <span className="upload-link">Click to upload</span> or drag and drop
            </p>
            <p className="upload-hint">PDF or image (PNG, JPG) up to 10MB</p>
          </>
        )}
      </div>

      {error && (
        <div className="upload-error">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      <div className="upload-footer">
        <p>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          Your document is processed securely and not stored
        </p>
      </div>
    </div>
  );
};

export default MortgageStatementUpload;
