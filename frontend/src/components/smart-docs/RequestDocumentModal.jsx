/**
 * RequestDocumentModal - Request multiple documents from borrowers
 *
 * Features:
 * - Queue multiple document requests in a single session
 * - Per-document type, title, instructions, e-sign toggle
 * - Shared priority, due date, and notification settings
 * - Batch submission with progress tracking
 * - LOE template support per document
 */

import React, { useState, useCallback } from 'react';
import { addCustomRequest } from '../../services/smartDocsApi';
import './RequestDocumentModal.css';

const DOCUMENT_TYPES = [
  { value: 'LOE', label: 'Letter of Explanation', requiresEsign: true, category: 'letters' },
  { value: 'GIFT_LETTER', label: 'Gift Letter', requiresEsign: true, category: 'letters' },
  { value: 'PAYSTUB', label: 'Pay Stubs', requiresEsign: false, category: 'income' },
  { value: 'BANK_STATEMENT', label: 'Bank Statements', requiresEsign: false, category: 'assets' },
  { value: 'TAX_RETURN', label: 'Tax Returns', requiresEsign: false, category: 'income' },
  { value: 'W2', label: 'W-2 Forms', requiresEsign: false, category: 'income' },
  { value: 'DRIVERS_LICENSE', label: "Driver's License", requiresEsign: false, category: 'identity' },
  { value: 'PURCHASE_CONTRACT', label: 'Purchase Contract', requiresEsign: false, category: 'property' },
  { value: 'PROFIT_LOSS', label: 'Profit & Loss Statement', requiresEsign: false, category: 'income' },
  { value: 'HOMEOWNERS_INSURANCE', label: 'Homeowners Insurance', requiresEsign: false, category: 'property' },
  { value: 'OTHER', label: 'Other Document', requiresEsign: false, category: 'other' },
];

const LOE_TEMPLATES = [
  { value: 'credit_inquiry', label: 'Credit Inquiry Explanation', prompt: 'Please explain the recent credit inquiry from {company} on {date}.' },
  { value: 'late_payment', label: 'Late Payment Explanation', prompt: 'Please explain the late payment on your {account_type} account in {date}.' },
  { value: 'employment_gap', label: 'Employment Gap Explanation', prompt: 'Please explain the gap in employment between {start_date} and {end_date}.' },
  { value: 'large_deposit', label: 'Large Deposit Explanation', prompt: 'Please explain the large deposit of {amount} on {date} in your {account} account.' },
  { value: 'address_discrepancy', label: 'Address Discrepancy Explanation', prompt: 'Please explain the discrepancy between your current address and the address on your {document}.' },
  { value: 'name_variation', label: 'Name Variation Explanation', prompt: 'Please explain the name variation between {name1} and {name2} on your documents.' },
  { value: 'custom', label: 'Custom Letter of Explanation', prompt: '' },
];

let _docIdCounter = 0;
function createEmptyDoc() {
  _docIdCounter += 1;
  return {
    id: `doc-${_docIdCounter}-${Date.now()}`,
    docType: '',
    title: '',
    instructions: '',
    requireEsign: false,
    loeTemplate: 'custom',
  };
}

function RequestDocumentModal({
  isOpen,
  onClose,
  loanId,
  borrowerId,
  borrowerName,
  borrowerEmail,
  onSuccess,
}) {
  // Document queue state
  const [documents, setDocuments] = useState(() => [createEmptyDoc()]);
  const [activeIndex, setActiveIndex] = useState(0);

  // Shared settings
  const [priority, setPriority] = useState('normal');
  const [dueDate, setDueDate] = useState('');
  const [sendNotification, setSendNotification] = useState(true);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitProgress, setSubmitProgress] = useState({ done: 0, total: 0 });
  const [error, setError] = useState(null);
  const [submitResults, setSubmitResults] = useState(null); // null = not submitted, array = results

  const activeDoc = documents[activeIndex] || documents[0];

  // Update a field on the active document
  const updateActiveDoc = useCallback((field, value) => {
    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex ? { ...doc, [field]: value } : doc
    ));
  }, [activeIndex]);

  const handleDocTypeChange = useCallback((newType) => {
    const docInfo = DOCUMENT_TYPES.find(d => d.value === newType);
    const updates = {
      docType: newType,
      requireEsign: docInfo?.requiresEsign || false,
      title: newType === 'LOE' ? 'Letter of Explanation' : (docInfo?.label || ''),
      instructions: '',
      loeTemplate: 'custom',
    };
    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex ? { ...doc, ...updates } : doc
    ));
  }, [activeIndex]);

  const handleLoeTemplateChange = useCallback((template) => {
    const templateInfo = LOE_TEMPLATES.find(t => t.value === template);
    const updates = { loeTemplate: template };
    if (templateInfo && template !== 'custom') {
      updates.title = `Letter of Explanation - ${templateInfo.label.replace(' Explanation', '')}`;
      updates.instructions = templateInfo.prompt;
    } else {
      updates.title = 'Letter of Explanation';
      updates.instructions = '';
    }
    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex ? { ...doc, ...updates } : doc
    ));
  }, [activeIndex]);

  const addDocument = useCallback(() => {
    const newDoc = createEmptyDoc();
    setDocuments(prev => {
      const next = [...prev, newDoc];
      setActiveIndex(next.length - 1);
      return next;
    });
  }, []);

  const removeDocument = useCallback((index) => {
    if (documents.length <= 1) return;
    setDocuments(prev => prev.filter((_, i) => i !== index));
    setActiveIndex(prev => {
      if (prev >= index && prev > 0) return prev - 1;
      return prev;
    });
  }, [documents.length]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Validate all documents have types selected
    const invalidDocs = documents.filter(d => !d.docType || !d.title.trim());
    if (invalidDocs.length > 0) {
      setError('Please select a document type and title for all documents in the queue.');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSubmitProgress({ done: 0, total: documents.length });

    const requests = documents.map(doc => ({
      title: doc.title.trim(),
      description: `${doc.docType} requested`,
      instructions: doc.instructions.trim(),
      priority,
      due_date: dueDate || null,
      send_notification: sendNotification,
      borrower_email: borrowerEmail,
      borrower_name: borrowerName,
      doc_type: doc.docType,
      requires_esign: doc.requireEsign,
    }));

    // Submit one by one, tracking progress
    const results = [];
    for (let i = 0; i < requests.length; i++) {
      try {
        const result = await addCustomRequest(loanId, borrowerId, requests[i]);
        results.push({ success: true, title: requests[i].title, result });
      } catch (err) {
        results.push({ success: false, title: requests[i].title, error: err.message });
      }
      setSubmitProgress({ done: i + 1, total: requests.length });
    }

    setSubmitting(false);
    setSubmitResults(results);

    const successCount = results.filter(r => r.success).length;
    if (successCount > 0 && onSuccess) {
      onSuccess();
    }
  };

  const handleClose = () => {
    setDocuments([createEmptyDoc()]);
    setActiveIndex(0);
    setPriority('normal');
    setDueDate('');
    setSendNotification(true);
    setError(null);
    setSubmitResults(null);
    setSubmitting(false);
    setSubmitProgress({ done: 0, total: 0 });
    onClose();
  };

  if (!isOpen) return null;

  const successCount = submitResults ? submitResults.filter(r => r.success).length : 0;
  const failCount = submitResults ? submitResults.filter(r => !r.success).length : 0;

  // Get label for a doc in the queue sidebar
  const getDocLabel = (doc) => {
    if (doc.title) return doc.title;
    if (doc.docType) {
      const info = DOCUMENT_TYPES.find(d => d.value === doc.docType);
      return info?.label || doc.docType;
    }
    return 'New Document';
  };

  return (
    <div className="request-doc-modal-overlay" onClick={handleClose}>
      <div className="request-doc-modal multi" onClick={(e) => e.stopPropagation()}>
        <div className="request-doc-header">
          <h2>
            Request Documents
            {documents.length > 1 && <span className="doc-count-badge">{documents.length}</span>}
          </h2>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        {submitResults ? (
          <div className="request-doc-success">
            <div className="success-icon">{failCount === 0 ? '\u2713' : '!'}</div>
            <h3>
              {failCount === 0
                ? `${successCount} Request${successCount !== 1 ? 's' : ''} Sent!`
                : `${successCount} Sent, ${failCount} Failed`}
            </h3>
            <div className="submit-results-list">
              {submitResults.map((r, i) => (
                <div key={i} className={`submit-result-item ${r.success ? 'success' : 'failed'}`}>
                  <span className="result-indicator">{r.success ? '\u2713' : '\u2717'}</span>
                  <span>{r.title}</span>
                  {!r.success && <span className="result-error">{r.error}</span>}
                </div>
              ))}
            </div>
            <p className="success-subtitle">
              {sendNotification && successCount > 0
                ? `${borrowerName || 'The borrower'} has been notified via email.`
                : 'Document requests have been added to the needs list.'}
            </p>
            <button className="btn-submit" onClick={handleClose} style={{ marginTop: 16 }}>
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="request-doc-form">
            <div className="request-doc-body">
              {/* Document Queue Sidebar */}
              <div className="doc-queue-sidebar">
                <div className="queue-label">Documents to Request</div>
                <div className="doc-queue-list">
                  {documents.map((doc, index) => (
                    <div
                      key={doc.id}
                      className={`doc-queue-item ${index === activeIndex ? 'active' : ''} ${doc.docType ? 'has-type' : ''}`}
                      onClick={() => setActiveIndex(index)}
                    >
                      <span className="queue-item-num">{index + 1}</span>
                      <span className="queue-item-label">{getDocLabel(doc)}</span>
                      {documents.length > 1 && (
                        <button
                          type="button"
                          className="queue-item-remove"
                          onClick={(e) => { e.stopPropagation(); removeDocument(index); }}
                          title="Remove"
                        >
                          &times;
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button type="button" className="add-doc-btn" onClick={addDocument}>
                  + Add Document
                </button>
              </div>

              {/* Document Configuration Panel */}
              <div className="doc-config-panel">
                {/* Document Type Selection */}
                <div className="form-section">
                  <label>Document Type</label>
                  <div className="doc-type-grid">
                    {DOCUMENT_TYPES.map((doc) => (
                      <button
                        key={doc.value}
                        type="button"
                        className={`doc-type-btn ${activeDoc.docType === doc.value ? 'active' : ''}`}
                        onClick={() => handleDocTypeChange(doc.value)}
                      >
                        {doc.label}
                        {doc.requiresEsign && <span className="esign-badge">E-Sign</span>}
                      </button>
                    ))}
                  </div>
                </div>

                {/* LOE Template Selection */}
                {activeDoc.docType === 'LOE' && (
                  <div className="form-section">
                    <label>LOE Template</label>
                    <select
                      value={activeDoc.loeTemplate}
                      onChange={(e) => handleLoeTemplateChange(e.target.value)}
                      className="form-select"
                    >
                      {LOE_TEMPLATES.map((template) => (
                        <option key={template.value} value={template.value}>
                          {template.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Title */}
                <div className="form-section">
                  <label>Title *</label>
                  <input
                    type="text"
                    value={activeDoc.title}
                    onChange={(e) => updateActiveDoc('title', e.target.value)}
                    placeholder="Document title"
                    className="form-input"
                  />
                </div>

                {/* Instructions */}
                <div className="form-section">
                  <label>Instructions for Borrower</label>
                  <textarea
                    value={activeDoc.instructions}
                    onChange={(e) => updateActiveDoc('instructions', e.target.value)}
                    placeholder="What should the borrower include in this document?"
                    className="form-textarea"
                    rows={3}
                  />
                </div>

                {/* E-Sign Toggle */}
                <div className="form-section">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={activeDoc.requireEsign}
                      onChange={(e) => updateActiveDoc('requireEsign', e.target.checked)}
                    />
                    <span>Require E-Signature</span>
                  </label>
                </div>
              </div>
            </div>

            {/* Shared Settings Footer */}
            <div className="shared-settings">
              <div className="form-row">
                <div className="form-section half">
                  <label>Priority</label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    className="form-select"
                  >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>

                <div className="form-section half">
                  <label>Due Date</label>
                  <input
                    type="date"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                    className="form-input"
                    min={new Date().toISOString().split('T')[0]}
                  />
                </div>
              </div>

              <div className="form-section">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={sendNotification}
                    onChange={(e) => setSendNotification(e.target.checked)}
                  />
                  <span>Send Email Notification</span>
                  <span className="checkbox-hint">
                    {borrowerEmail
                      ? `Notify ${borrowerEmail}`
                      : 'No email on file - notification will not be sent'}
                  </span>
                </label>
              </div>
            </div>

            {error && <div className="error-message" style={{ margin: '0 24px 16px' }}>{error}</div>}

            {/* Progress Bar */}
            {submitting && (
              <div className="submit-progress">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${submitProgress.total > 0 ? (submitProgress.done / submitProgress.total) * 100 : 0}%` }}
                  />
                </div>
                <span className="progress-text">
                  Sending {submitProgress.done} of {submitProgress.total}...
                </span>
              </div>
            )}

            {/* Actions */}
            <div className="form-actions">
              <button type="button" className="btn-cancel" onClick={handleClose} disabled={submitting}>
                Cancel
              </button>
              <button type="submit" className="btn-submit" disabled={submitting}>
                {submitting
                  ? `Sending ${submitProgress.done}/${submitProgress.total}...`
                  : `Send ${documents.length} Request${documents.length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default RequestDocumentModal;
