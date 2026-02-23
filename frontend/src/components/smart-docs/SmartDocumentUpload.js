import React, { useState, useRef } from 'react';
import { smartDocsAPI } from '../../services/smartDocsApi';
import './SmartDocumentUpload.css';

function SmartDocumentUpload({ loanId, borrowerId, onUploadComplete }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [documentCategory, setDocumentCategory] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
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
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
      setError(null);
      setUploadResult(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) {
      setSelectedFile(file);
      setError(null);
      setUploadResult(null);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file to upload');
      return;
    }
    if (!documentCategory) {
      setError('Please select a document category');
      return;
    }

    try {
      setUploading(true);
      setError(null);

      const result = await smartDocsAPI.uploadDocument(
        selectedFile,
        loanId,
        borrowerId,
        null, // requestId
        documentCategory
      );

      setUploadResult(result);
      setSelectedFile(null);
      setDocumentCategory('');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }

      if (onUploadComplete) {
        onUploadComplete(result);
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
    <div className="smart-document-upload">
      <h3>Upload Document</h3>

      <div
        className={`drop-zone ${selectedFile ? 'has-file' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileSelect}
          accept=".pdf,.png,.jpg,.jpeg,.gif,.tiff"
          style={{ display: 'none' }}
        />

        {selectedFile ? (
          <div className="selected-file">
            <span className="file-icon">📄</span>
            <div className="file-info">
              <span className="file-name">{selectedFile.name}</span>
              <span className="file-size">{formatFileSize(selectedFile.size)}</span>
            </div>
            <button
              className="remove-file"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}
            >
              ×
            </button>
          </div>
        ) : (
          <div className="drop-zone-content">
            <span className="upload-icon">📁</span>
            <p>Drag and drop a file here, or click to browse</p>
            <p className="file-types">Supported: PDF, PNG, JPG, TIFF</p>
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

      {error && <div className="upload-error">{error}</div>}

      {uploadResult && (
        <div className="upload-success">
          <strong>Document uploaded successfully!</strong>
          <div className="result-details">
            <p>Document ID: {uploadResult.document?.id}</p>
            <p>Status: {uploadResult.document?.status}</p>
            {uploadResult.validation && (
              <>
                <p>Screenshot Detection: {uploadResult.validation.is_screenshot ? 'Yes (flagged)' : 'No'}</p>
                <p>Freshness: {uploadResult.validation.freshness_status}</p>
              </>
            )}
          </div>
        </div>
      )}

      <button
        className="upload-btn"
        onClick={handleUpload}
        disabled={uploading || !selectedFile || !documentCategory}
      >
        {uploading ? 'Uploading...' : 'Upload Document'}
      </button>
    </div>
  );
}

export default SmartDocumentUpload;
