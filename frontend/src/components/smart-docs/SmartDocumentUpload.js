import React, { useState, useRef } from 'react';
import { API_BASE_URL } from '../../services/api';
import { getToken } from '../../utils/tokenStore';
import { smartDocsAPI } from '../../services/smartDocsApi';
import './SmartDocumentUpload.css';

const SMART_DOCS_API = `${API_BASE_URL}/api/v1/smart-docs`;

/**
 * Upload a single file with real XHR progress tracking.
 */
function uploadWithProgress(file, loanId, borrowerId, docType, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('loan_id', loanId);
    formData.append('borrower_id', borrowerId);
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
          if (typeof detail === 'string') message = detail;
          else if (Array.isArray(detail)) message = detail.map(d => d.msg || JSON.stringify(d)).join('; ');
          else message = detail?.msg || 'Upload failed';
          reject(new Error(message));
        }
      } catch {
        reject(new Error('Upload failed: invalid response'));
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));

    xhr.open('POST', `${SMART_DOCS_API}/upload`);
    const token = getToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.send(formData);
  });
}

function SmartDocumentUpload({ loanId, borrowerId, onUploadComplete }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [documentCategory, setDocumentCategory] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({}); // { [fileName]: percent }
  const [error, setError] = useState(null);
  const [uploadResults, setUploadResults] = useState([]);
  const [statusAnnouncement, setStatusAnnouncement] = useState('');
  const fileInputRef = useRef(null);

  const documentCategories = [
    { value: 'PAYSTUB', label: 'Paystub' },
    { value: 'W2', label: 'W-2' },
    { value: 'TAX_RETURN', label: 'Tax Return' },
    { value: 'BANK_STATEMENT', label: 'Bank Statement' },
    { value: 'DRIVERS_LICENSE', label: "Driver's License" },
    { value: 'PURCHASE_CONTRACT', label: 'Purchase Contract' },
    { value: 'APPRAISAL', label: 'Appraisal' },
    { value: 'TITLE_REPORT', label: 'Title Document' },
    { value: 'HOMEOWNERS_INSURANCE', label: 'Insurance' },
    { value: 'OTHER', label: 'Other' },
  ];

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setSelectedFiles(files);
      setError(null);
      setUploadResults([]);
      setUploadProgress({});
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length > 0) {
      setSelectedFiles(files);
      setError(null);
      setUploadResults([]);
      setUploadProgress({});
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDropzoneKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const removeFile = (index) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      setError('Please select at least one file to upload');
      return;
    }
    if (!documentCategory) {
      setError('Please select a document category');
      return;
    }

    try {
      setUploading(true);
      setError(null);
      setStatusAnnouncement(`Uploading ${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''}...`);

      const results = [];
      for (const file of selectedFiles) {
        try {
          const result = await uploadWithProgress(
            file, loanId, borrowerId, documentCategory,
            (pct) => {
              setUploadProgress(prev => ({ ...prev, [file.name]: pct }));
            }
          );
          results.push({ file: file.name, success: true, data: result });
          setStatusAnnouncement(`${file.name} uploaded successfully.`);
        } catch (err) {
          results.push({ file: file.name, success: false, error: err.message });
          setStatusAnnouncement(`${file.name} upload failed.`);
        }
      }

      setUploadResults(results);
      setSelectedFiles([]);
      setDocumentCategory('');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }

      const successCount = results.filter(r => r.success).length;
      setStatusAnnouncement(`Upload complete: ${successCount} of ${results.length} succeeded.`);

      if (onUploadComplete) {
        results.filter(r => r.success).forEach(r => onUploadComplete(r.data));
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError(err.message || 'Failed to upload document');
    } finally {
      setUploading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="smart-document-upload" aria-busy={uploading}>
      <h3>Upload Document</h3>

      {/* Live region for status announcements */}
      <div className="sr-only" aria-live="polite" aria-atomic="true" role="status">
        {statusAnnouncement}
      </div>

      <div
        className={`drop-zone ${selectedFiles.length > 0 ? 'has-file' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={handleDropzoneKeyDown}
        role="button"
        tabIndex={0}
        aria-label="Upload documents. Drag and drop files here or click to browse."
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          accept=".pdf,.png,.jpg,.jpeg,.gif,.tiff"
          style={{ display: 'none' }}
          aria-hidden="true"
        />

        {selectedFiles.length > 0 ? (
          <div className="selected-files-list">
            {selectedFiles.map((file, idx) => (
              <div key={idx} className="selected-file">
                <span className="file-icon" aria-hidden="true">📄</span>
                <div className="file-info">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{formatFileSize(file.size)}</span>
                </div>
                {uploading && uploadProgress[file.name] != null && (
                  <div
                    className="progress-bar-track"
                    role="progressbar"
                    aria-valuenow={uploadProgress[file.name]}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Upload progress for ${file.name}: ${uploadProgress[file.name]}%`}
                  >
                    <div className="progress-bar-fill" style={{ width: `${uploadProgress[file.name]}%` }} />
                  </div>
                )}
                {!uploading && (
                  <button
                    className="remove-file"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(idx);
                    }}
                    aria-label={`Remove ${file.name}`}
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="drop-zone-content">
            <span className="upload-icon" aria-hidden="true">📁</span>
            <p>Drag and drop files here, or click to browse</p>
            <p className="file-types">Supported: PDF, PNG, JPG, TIFF (multiple files supported)</p>
          </div>
        )}
      </div>

      <div className="form-group">
        <label htmlFor="doc-category">Document Category</label>
        <select
          id="doc-category"
          value={documentCategory}
          onChange={(e) => setDocumentCategory(e.target.value)}
        >
          <option value="">-- Select Category --</option>
          {documentCategories.map((cat) => (
            <option key={cat.value} value={cat.value}>
              {cat.label}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="upload-error" role="alert">{error}</div>}

      {uploadResults.length > 0 && (
        <div className="upload-success" aria-live="polite">
          <strong>{uploadResults.filter(r => r.success).length} of {uploadResults.length} uploaded successfully!</strong>
          <div className="result-details">
            {uploadResults.map((r, idx) => (
              <p key={idx}>
                {r.file}: {r.success ? (
                  <>ID: {r.data?.document?.id} — Status: {r.data?.document?.status}</>
                ) : (
                  <span style={{ color: '#dc2626' }}>Failed — {r.error}</span>
                )}
              </p>
            ))}
          </div>
        </div>
      )}

      <button
        className="upload-btn"
        onClick={handleUpload}
        disabled={uploading || selectedFiles.length === 0 || !documentCategory}
        aria-label={uploading ? 'Upload in progress' : `Upload ${selectedFiles.length} document${selectedFiles.length !== 1 ? 's' : ''}`}
      >
        {uploading ? 'Uploading...' : `Upload Document${selectedFiles.length > 1 ? 's' : ''}`}
      </button>
    </div>
  );
}

export default SmartDocumentUpload;
