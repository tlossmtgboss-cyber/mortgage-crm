/**
 * FileUploadInput - File upload with document parsing capability
 */

import React, { useState, useRef } from 'react';
import './FileUploadInput.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const FileUploadInput = ({
  value,
  onChange,
  error,
  helpText,
  disabled = false,
  required = false,
  acceptedTypes = '.pdf,.jpg,.jpeg,.png',
  documentType = 'document',
}) => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileSelect = async (e) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setUploadError(null);
    setUploading(true);
    setUploadProgress(0);

    try {
      // Create form data
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('document_type', documentType);

      // Upload to API
      const response = await fetch(`${API_BASE_URL}/api/v1/documents/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const result = await response.json();

      // Set progress to 100%
      setUploadProgress(100);

      // Store parsed data if available
      if (result.parsed_data) {
        setParsedData(result.parsed_data);
      }

      // Notify parent with file info
      onChange({
        file_id: result.file_id,
        file_name: selectedFile.name,
        file_type: selectedFile.type,
        file_size: selectedFile.size,
        parsed_data: result.parsed_data,
        upload_url: result.url,
      });

    } catch (err) {
      console.error('Upload error:', err);
      setUploadError('Failed to upload file. Please try again.');

      // Still store locally even if API fails
      onChange({
        file_name: selectedFile.name,
        file_type: selectedFile.type,
        file_size: selectedFile.size,
        local_file: selectedFile,
      });
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = () => {
    setFile(null);
    setParsedData(null);
    setUploadError(null);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    onChange(null);
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className={`file-upload-input ${error ? 'has-error' : ''}`}>
      {!file ? (
        <div
          className={`upload-dropzone ${disabled ? 'disabled' : ''}`}
          onClick={() => !disabled && fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={acceptedTypes}
            onChange={handleFileSelect}
            disabled={disabled}
            className="file-input-hidden"
          />
          <div className="dropzone-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
          <p className="dropzone-text">Click to upload your document</p>
          <p className="dropzone-hint">Accepted: PDF, JPG, PNG</p>
        </div>
      ) : (
        <div className="uploaded-file">
          <div className="file-info">
            <div className="file-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <div className="file-details">
              <p className="file-name">{file.name}</p>
              <p className="file-size">{formatFileSize(file.size)}</p>
            </div>
            <button
              type="button"
              className="remove-btn"
              onClick={handleRemove}
              disabled={uploading}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {uploading && (
            <div className="upload-progress">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <span className="progress-text">Uploading...</span>
            </div>
          )}

          {!uploading && uploadProgress === 100 && (
            <div className="upload-success">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>Uploaded successfully</span>
            </div>
          )}

          {parsedData && (
            <div className="parsed-data">
              <p className="parsed-label">Extracted Information:</p>
              <div className="parsed-items">
                {Object.entries(parsedData).map(([key, val]) => (
                  <div key={key} className="parsed-item">
                    <span className="parsed-key">{key.replace(/_/g, ' ')}:</span>
                    <span className="parsed-value">{val}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {uploadError && <p className="error-text">{uploadError}</p>}
      {helpText && !file && <p className="help-text">{helpText}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
};

export default FileUploadInput;
