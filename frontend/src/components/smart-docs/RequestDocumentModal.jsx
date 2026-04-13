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

import React, { useState, useCallback, useRef } from 'react';
import { addCustomRequest, uploadDocument } from '../../services/smartDocsApi';
import { esignApi } from '../../services/esignApi';
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

const SIGNER_OPTIONS = [
  { value: 'borrower', label: 'Borrower' },
  { value: 'co_borrower', label: 'Co-Borrower' },
  { value: 'both', label: 'Both Borrower & Co-Borrower' },
];

const ESIGN_FIELD_DEFAULTS = {
  includeSignature: true,
  includeExplanation: true,
  includeDateStamp: true,
  explanationPrompt: '',
};

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
    // E-sign fields
    esignFile: null,
    esignFileName: '',
    esignSigner: 'borrower',
    esignFields: { ...ESIGN_FIELD_DEFAULTS },
  };
}

function RequestDocumentModal({
  isOpen,
  onClose,
  loanId,
  borrowerId,
  borrowerName,
  borrowerEmail,
  coBorrowerName,
  coBorrowerEmail,
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

  // E-sign file upload ref
  const fileInputRef = useRef(null);

  // [SEC-001] Validate PDF magic bytes + MIME + extension
  const validatePdfFile = useCallback((file) => {
    return new Promise((resolve, reject) => {
      if (!file) return reject('No file selected');
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
      if (!isPdf) return reject('Please upload a PDF document for e-signature.');
      if (file.size > 25 * 1024 * 1024) return reject('File size must be under 25 MB.');
      // Validate magic bytes (%PDF-)
      const reader = new FileReader();
      reader.onload = (event) => {
        const arr = new Uint8Array(event.target.result);
        const header = String.fromCharCode(arr[0], arr[1], arr[2], arr[3], arr[4]);
        if (header !== '%PDF-') {
          return reject('The file does not appear to be a valid PDF document.');
        }
        resolve(file);
      };
      reader.onerror = () => reject('Failed to read file.');
      reader.readAsArrayBuffer(file.slice(0, 5));
    });
  }, []);

  const handleEsignFileSelect = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await validatePdfFile(file);
      setDocuments(prev => prev.map((doc, i) =>
        i === activeIndex ? { ...doc, esignFile: file, esignFileName: file.name } : doc
      ));
      setError(null);
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [activeIndex, validatePdfFile]);

  const handleRemoveEsignFile = useCallback(() => {
    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex ? { ...doc, esignFile: null, esignFileName: '' } : doc
    ));
  }, [activeIndex]);

  const handleEsignFieldToggle = useCallback((field, value) => {
    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex
        ? { ...doc, esignFields: { ...doc.esignFields, [field]: value } }
        : doc
    ));
  }, [activeIndex]);

  const handleFileDrop = useCallback(async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    try {
      await validatePdfFile(file);
      setDocuments(prev => prev.map((doc, i) =>
        i === activeIndex ? { ...doc, esignFile: file, esignFileName: file.name } : doc
      ));
      setError(null);
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message);
    }
  }, [activeIndex, validatePdfFile]);

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

    // [FUNC-004] Fix: validate e-sign docs have files uploaded
    const esignWithoutFile = documents.filter(d => d.requireEsign && !d.esignFile);
    if (esignWithoutFile.length > 0) {
      setError('Please upload a PDF for all documents requiring e-signature.');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSubmitProgress({ done: 0, total: documents.length });

    const results = [];
    for (let i = 0; i < documents.length; i++) {
      const doc = documents[i];
      let stepName = 'creating request';
      try {
        // Step 1: Create the document request
        const requestPayload = {
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
          esign_initiated: doc.requireEsign && !!doc.esignFile,
        };
        const result = await addCustomRequest(loanId, borrowerId, requestPayload);
        const requestId = result?.id || result?.data?.id;

        // Step 2: If e-sign with uploaded file, create envelope + fields
        if (doc.requireEsign && doc.esignFile) {
          // 2a: Upload the document
          stepName = 'uploading document';
          const uploadResult = await uploadDocument(
            doc.esignFile, loanId, borrowerId, requestId, doc.docType
          );
          // [FUNC-007] Extract S3 storage key (not URL)
          const storageKey = uploadResult?.storage_key
            || uploadResult?.data?.storage_key
            || uploadResult?.s3_key
            || uploadResult?.data?.s3_key;
          const originalFilename = uploadResult?.filename
            || uploadResult?.data?.filename
            || doc.esignFileName;

          if (!storageKey) {
            throw new Error('Document upload did not return a storage key');
          }

          // 2b: Build recipients list
          stepName = 'creating e-sign envelope';
          const recipientsPayload = [];
          if (doc.esignSigner === 'borrower' || doc.esignSigner === 'both') {
            recipientsPayload.push({
              name: borrowerName || 'Borrower',
              email: borrowerEmail || '',
              type: 'signer',
              signing_order: 1,
              auth_method: 'email_link',
            });
          }
          if (doc.esignSigner === 'co_borrower' || doc.esignSigner === 'both') {
            recipientsPayload.push({
              name: coBorrowerName || 'Co-Borrower',
              email: coBorrowerEmail || '',
              type: 'signer',
              signing_order: doc.esignSigner === 'both' ? 2 : 1,
              auth_method: 'email_link',
            });
          }

          // 2c: Build fields list using backend field names
          // [FUNC-001/003] Use type/page/x/y/w/h/recipient_index (not field_type/page_number/x_position/signer_email)
          const fieldsPayload = [];
          const baseY = 500; // PDF points from bottom

          // [SEC-003] Sanitize explanation prompt
          const sanitizedPrompt = (doc.esignFields.explanationPrompt || 'Please provide your explanation')
            .replace(/[<>"'&]/g, '')
            .slice(0, 500);

          for (let s = 0; s < recipientsPayload.length; s++) {
            const yOffset = s * 160;

            if (doc.esignFields.includeExplanation) {
              fieldsPayload.push({
                type: 'text',
                page: 1,
                x: 72,
                y: baseY - yOffset + 100,
                w: 400,
                h: 60,
                recipient_index: s,
                required: true,
                placeholder: sanitizedPrompt,
              });
            }
            if (doc.esignFields.includeSignature) {
              fieldsPayload.push({
                type: 'signature',
                page: 1,
                x: 72,
                y: baseY - yOffset,
                w: 200,
                h: 50,
                recipient_index: s,
                required: true,
              });
            }
            if (doc.esignFields.includeDateStamp) {
              fieldsPayload.push({
                type: 'date_signed',
                page: 1,
                x: 300,
                y: baseY - yOffset,
                w: 120,
                h: 30,
                recipient_index: s,
                required: true,
              });
            }
          }

          // [PERF-001] Single createEnvelope call with recipients + fields (batch)
          const envelopeData = {
            title: `${doc.title.trim()} - E-Signature`,
            document_storage_key: storageKey,
            original_filename: originalFilename,
            loan_id: parseInt(loanId),
            recipients: recipientsPayload,
            fields: fieldsPayload.length > 0 ? fieldsPayload : undefined,
          };
          const envelopeResult = await esignApi.createEnvelope(envelopeData);
          const envelope = envelopeResult.data || envelopeResult;

          // [FUNC-002] Use envelope_uuid for send (not integer id)
          stepName = 'sending for signature';
          const envelopeUuid = envelope.envelope_uuid || envelope.id;
          await esignApi.sendEnvelope(envelopeUuid);

          results.push({ success: true, title: doc.title, esign: true });
        } else {
          results.push({ success: true, title: doc.title, esign: false });
        }
      } catch (err) {
        // [OBS-001] Step-specific error messages
        console.error(`Request submission error at step "${stepName}":`, err);
        const isPartial = stepName !== 'creating request';
        results.push({
          success: false,
          title: doc.title,
          error: isPartial
            ? `Failed at ${stepName}: ${err.message}`
            : err.message,
          // [DATA-001] Flag partial creation so user knows request exists but e-sign failed
          warning: isPartial ? 'Document request was created but e-signature setup failed.' : undefined,
        });
      }
      setSubmitProgress({ done: i + 1, total: documents.length });
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
                  {r.esign && <span className="esign-sent-badge">E-Sign Sent</span>}
                  {!r.success && <span className="result-error">{r.error}</span>}
                  {r.warning && <span className="result-warning">{r.warning}</span>}
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

                {/* E-Sign Configuration (shown when e-sign is checked) */}
                {activeDoc.requireEsign && (
                  <div className="esign-config-section">
                    <div className="esign-config-header">E-Signature Setup</div>

                    {/* Upload Document */}
                    <div className="form-section">
                      <label>Upload Document for Signing</label>
                      {activeDoc.esignFile ? (
                        <div className="esign-file-attached">
                          <span className="file-icon">&#128196;</span>
                          <div className="file-info">
                            <span className="file-name">{activeDoc.esignFileName}</span>
                            <span className="file-size">
                              {(activeDoc.esignFile.size / 1024).toFixed(0)} KB
                            </span>
                          </div>
                          <button
                            type="button"
                            className="file-remove-btn"
                            onClick={handleRemoveEsignFile}
                            title="Remove file"
                          >
                            &times;
                          </button>
                        </div>
                      ) : (
                        <div
                          className="esign-dropzone"
                          onClick={() => fileInputRef.current?.click()}
                          onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('dragover'); }}
                          onDragLeave={(e) => e.currentTarget.classList.remove('dragover')}
                          onDrop={(e) => { e.currentTarget.classList.remove('dragover'); handleFileDrop(e); }}
                        >
                          <span className="dropzone-icon">&#8593;</span>
                          <span className="dropzone-text">
                            Drag & drop a PDF here, or <strong>click to browse</strong>
                          </span>
                          <span className="dropzone-hint">PDF only, max 25 MB</span>
                        </div>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,application/pdf"
                        style={{ display: 'none' }}
                        onChange={handleEsignFileSelect}
                      />
                    </div>

                    {/* Signer Selection */}
                    <div className="form-section">
                      <label>Who Needs to Sign?</label>
                      <select
                        value={activeDoc.esignSigner}
                        onChange={(e) => updateActiveDoc('esignSigner', e.target.value)}
                        className="form-select"
                      >
                        {SIGNER_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                            {opt.value === 'borrower' && borrowerName ? ` (${borrowerName})` : ''}
                            {opt.value === 'co_borrower' && coBorrowerName ? ` (${coBorrowerName})` : ''}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Field Placement Options */}
                    <div className="form-section">
                      <label>Fields to Place on Document</label>
                      <div className="esign-fields-config">
                        <label className="esign-field-toggle">
                          <input
                            type="checkbox"
                            checked={activeDoc.esignFields.includeSignature}
                            onChange={(e) => handleEsignFieldToggle('includeSignature', e.target.checked)}
                          />
                          <span className="field-toggle-label">
                            <span className="field-toggle-icon" style={{ color: '#1a73e8' }}>&#9997;</span>
                            Signature
                          </span>
                        </label>

                        <label className="esign-field-toggle">
                          <input
                            type="checkbox"
                            checked={activeDoc.esignFields.includeExplanation}
                            onChange={(e) => handleEsignFieldToggle('includeExplanation', e.target.checked)}
                          />
                          <span className="field-toggle-label">
                            <span className="field-toggle-icon" style={{ color: '#6d4c41' }}>&#9998;</span>
                            Explanation Text Area
                          </span>
                        </label>

                        <label className="esign-field-toggle">
                          <input
                            type="checkbox"
                            checked={activeDoc.esignFields.includeDateStamp}
                            onChange={(e) => handleEsignFieldToggle('includeDateStamp', e.target.checked)}
                          />
                          <span className="field-toggle-label">
                            <span className="field-toggle-icon" style={{ color: '#00897b' }}>&#128197;</span>
                            Date Stamp
                          </span>
                        </label>
                      </div>
                    </div>

                    {/* Explanation Prompt (when explanation is toggled on) */}
                    {activeDoc.esignFields.includeExplanation && (
                      <div className="form-section">
                        <label>Explanation Prompt for Borrower</label>
                        <input
                          type="text"
                          value={activeDoc.esignFields.explanationPrompt}
                          onChange={(e) => handleEsignFieldToggle('explanationPrompt', e.target.value)}
                          placeholder="e.g., Please explain the recent credit inquiry from (company) on (date)"
                          className="form-input"
                        />
                      </div>
                    )}
                  </div>
                )}
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
