import React, { useState, useEffect } from 'react';
import { documentDropAPI, leadsAPI, loansAPI } from '../services/api';
import './DocumentDropModal.css';
import { toast } from '../utils/toast';

/**
 * DocumentDropModal - Modal for handling dropped document files
 * Allows user to classify document and assign to borrower/loan
 */
function DocumentDropModal({ file, onClose, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [classification, setClassification] = useState(null);
  const [selectedDocType, setSelectedDocType] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState({ leads: [], loans: [] });
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [step, setStep] = useState('classify'); // 'classify', 'assign', 'confirm'

  // Document types
  const documentTypes = [
    { value: 'PAY_STUB', label: 'Pay Stub', category: 'Income' },
    { value: 'W2', label: 'W-2', category: 'Income' },
    { value: 'TAX_RETURN', label: 'Tax Return', category: 'Income' },
    { value: 'BANK_STATEMENT', label: 'Bank Statement', category: 'Assets' },
    { value: 'INVESTMENT_STATEMENT', label: 'Investment Statement', category: 'Assets' },
    { value: 'DRIVERS_LICENSE', label: "Driver's License", category: 'Identity' },
    { value: 'PASSPORT', label: 'Passport', category: 'Identity' },
    { value: 'PURCHASE_CONTRACT', label: 'Purchase Contract', category: 'Property' },
    { value: 'APPRAISAL', label: 'Appraisal', category: 'Property' },
    { value: 'TITLE_REPORT', label: 'Title Report', category: 'Property' },
    { value: 'INSURANCE_DECLARATION', label: 'Insurance Declaration', category: 'Property' },
    { value: 'CREDIT_REPORT', label: 'Credit Report', category: 'Credit' },
    { value: 'LOAN_ESTIMATE', label: 'Loan Estimate', category: 'Disclosures' },
    { value: 'CLOSING_DISCLOSURE', label: 'Closing Disclosure', category: 'Disclosures' },
    { value: 'OTHER', label: 'Other Document', category: 'Other' },
  ];

  // Try to classify document with AI on mount
  useEffect(() => {
    classifyDocument();
  }, [file]);

  const classifyDocument = async () => {
    setLoading(true);
    try {
      const result = await documentDropAPI.classify(file);
      setClassification(result);
      if (result.suggested_type) {
        setSelectedDocType(result.suggested_type);
      }
    } catch (error) {
      console.warn('Auto-classification failed:', error);
      // Default to OTHER if classification fails
      setSelectedDocType('OTHER');
    }
    setLoading(false);
  };

  const handleSearch = async () => {
    if (!searchTerm.trim()) return;

    setLoading(true);
    try {
      const [leadsResponse, loansResponse] = await Promise.all([
        leadsAPI.search(searchTerm).catch(() => []),
        loansAPI.getAll().catch(() => [])
      ]);

      const leads = Array.isArray(leadsResponse) ? leadsResponse : (leadsResponse?.data || []);
      const loans = Array.isArray(loansResponse) ? loansResponse : (loansResponse?.data || []);

      // Filter loans by search term
      const filteredLoans = loans.filter(loan =>
        loan.borrower_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        loan.loan_number?.toLowerCase().includes(searchTerm.toLowerCase())
      );

      setSearchResults({
        leads: leads.slice(0, 5),
        loans: filteredLoans.slice(0, 5)
      });
    } catch (error) {
      console.error('Search failed:', error);
    }
    setLoading(false);
  };

  const handleUpload = async () => {
    if (!selectedDocType) {
      toast.error('Please select a document type');
      return;
    }

    setUploading(true);
    try {
      const borrowerId = selectedEntity?.type === 'lead' ? selectedEntity.id : null;
      const loanId = selectedEntity?.type === 'loan' ? selectedEntity.id : null;

      const result = await documentDropAPI.upload(file, borrowerId, loanId, selectedDocType);
      onComplete(result);
    } catch (error) {
      console.error('Upload failed:', error);
      toast.error('Failed to upload document. Please try again.');
    }
    setUploading(false);
  };

  const getFileIcon = () => {
    const ext = file.name.split('.').pop().toLowerCase();
    switch (ext) {
      case 'pdf': return '📄';
      case 'doc':
      case 'docx': return '📝';
      case 'xls':
      case 'xlsx': return '📊';
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif': return '🖼️';
      default: return '📁';
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="document-drop-modal-overlay" onClick={onClose}>
      <div className="document-drop-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <h2>Upload Document</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {/* File Preview */}
        <div className="file-preview">
          <div className="file-icon">{getFileIcon()}</div>
          <div className="file-info">
            <div className="file-name">{file.name}</div>
            <div className="file-size">{formatFileSize(file.size)}</div>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Analyzing document...</p>
          </div>
        )}

        {/* Classification Result */}
        {classification && !loading && (
          <div className="classification-result">
            {classification.suggested_type && (
              <div className="ai-suggestion">
                <span className="ai-badge">AI Classification</span>
                <span className="suggestion-text">
                  Detected: {documentTypes.find(d => d.value === classification.suggested_type)?.label || classification.suggested_type}
                </span>
                {classification.confidence && (
                  <span className="confidence">({Math.round(classification.confidence * 100)}% confident)</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Document Type Selection */}
        <div className="form-section">
          <label>Document Type</label>
          <select
            value={selectedDocType}
            onChange={(e) => setSelectedDocType(e.target.value)}
            className="doc-type-select"
          >
            <option value="">Select document type...</option>
            {Object.entries(
              documentTypes.reduce((acc, doc) => {
                if (!acc[doc.category]) acc[doc.category] = [];
                acc[doc.category].push(doc);
                return acc;
              }, {})
            ).map(([category, docs]) => (
              <optgroup key={category} label={category}>
                {docs.map(doc => (
                  <option key={doc.value} value={doc.value}>{doc.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        {/* Entity Assignment */}
        <div className="form-section">
          <label>Assign to (Optional)</label>
          <div className="search-box">
            <input
              type="text"
              placeholder="Search by name, email, or loan number..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button onClick={handleSearch} disabled={loading}>Search</button>
          </div>

          {/* Search Results */}
          {(searchResults.leads.length > 0 || searchResults.loans.length > 0) && (
            <div className="search-results">
              {searchResults.leads.map(lead => (
                <div
                  key={`lead-${lead.id}`}
                  className={`result-item ${selectedEntity?.id === lead.id && selectedEntity?.type === 'lead' ? 'selected' : ''}`}
                  onClick={() => setSelectedEntity({ type: 'lead', id: lead.id, name: `${lead.first_name} ${lead.last_name}` })}
                >
                  <span className="result-type lead">Lead</span>
                  <span className="result-name">{lead.first_name} {lead.last_name}</span>
                  <span className="result-email">{lead.email}</span>
                </div>
              ))}
              {searchResults.loans.map(loan => (
                <div
                  key={`loan-${loan.id}`}
                  className={`result-item ${selectedEntity?.id === loan.id && selectedEntity?.type === 'loan' ? 'selected' : ''}`}
                  onClick={() => setSelectedEntity({ type: 'loan', id: loan.id, name: loan.borrower_name })}
                >
                  <span className="result-type loan">Loan</span>
                  <span className="result-name">{loan.borrower_name}</span>
                  <span className="result-number">{loan.loan_number}</span>
                </div>
              ))}
            </div>
          )}

          {/* Selected Entity */}
          {selectedEntity && (
            <div className="selected-entity">
              <span>Assigning to: {selectedEntity.name}</span>
              <button className="clear-btn" onClick={() => setSelectedEntity(null)}>×</button>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="modal-actions">
          <button className="btn-cancel" onClick={onClose} disabled={uploading}>
            Cancel
          </button>
          <button
            className="btn-upload"
            onClick={handleUpload}
            disabled={uploading || !selectedDocType}
          >
            {uploading ? 'Uploading...' : 'Upload Document'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default DocumentDropModal;
