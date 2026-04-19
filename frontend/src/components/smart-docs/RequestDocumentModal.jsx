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

import React, { useState, useCallback, useRef, useEffect } from 'react';
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

const ESIGN_FIELD_CONFIG = {
  signature: { label: 'Signature', color: '#1a73e8', w: 144, h: 36, icon: '\u270D' },
  date_signed: { label: 'Date', color: '#00897b', w: 86, h: 22, icon: '\uD83D\uDCC5' },
  text: { label: 'Text', color: '#6d4c41', w: 144, h: 22, icon: '\u270E' },
  initial: { label: 'Initial', color: '#7c4dff', w: 58, h: 29, icon: 'AB' },
  checkbox: { label: 'Checkbox', color: '#f4511e', w: 17, h: 17, icon: '\u2611' },
};

const PDF_PAGE_WIDTH = 612;
const PDF_PAGE_HEIGHT = 792;

let _docIdCounter = 0;
let _fieldIdCounter = 0;
function createEmptyDoc() {
  _docIdCounter += 1;
  return {
    id: `doc-${_docIdCounter}-${Date.now()}`,
    docType: '',
    title: '',
    instructions: '',
    requireEsign: false,
    loeTemplate: 'custom',
    esignFile: null,
    esignFileName: '',
    esignSigner: 'borrower',
    esignPlacedFields: [],
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

  // E-sign state
  const [activeFieldTool, setActiveFieldTool] = useState(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState(null);
  const [draggingFieldId, setDraggingFieldId] = useState(null);

  const fileInputRef = useRef(null);
  const pdfContainerRef = useRef(null);

  // Create/revoke blob URL when esignFile changes
  useEffect(() => {
    if (activeDoc?.esignFile) {
      const url = URL.createObjectURL(activeDoc.esignFile);
      setPdfBlobUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    setPdfBlobUrl(null);
  }, [activeDoc?.esignFile]);

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
      i === activeIndex ? { ...doc, esignFile: null, esignFileName: '', esignPlacedFields: [] } : doc
    ));
    setActiveFieldTool(null);
  }, [activeIndex]);

  // Place a new field on the PDF at click position
  const handlePlaceField = useCallback((e) => {
    if (!activeFieldTool) return;
    const container = pdfContainerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const xPct = (e.clientX - rect.left) / rect.width;
    const yPct = (e.clientY - rect.top) / rect.height;

    const config = ESIGN_FIELD_CONFIG[activeFieldTool];
    const x = Math.max(0, Math.min(PDF_PAGE_WIDTH - config.w, xPct * PDF_PAGE_WIDTH - config.w / 2));
    const y = Math.max(0, Math.min(PDF_PAGE_HEIGHT - config.h, PDF_PAGE_HEIGHT - yPct * PDF_PAGE_HEIGHT - config.h / 2));

    _fieldIdCounter += 1;
    const newField = {
      id: `field-${_fieldIdCounter}-${Date.now()}`,
      type: activeFieldTool,
      page: 1,
      x, y,
      w: config.w,
      h: config.h,
      recipientIndex: 0,
    };

    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex
        ? { ...doc, esignPlacedFields: [...doc.esignPlacedFields, newField] }
        : doc
    ));
  }, [activeFieldTool, activeIndex]);

  const handleRemoveField = useCallback((fieldId) => {
    setDocuments(prev => prev.map((doc, i) =>
      i === activeIndex
        ? { ...doc, esignPlacedFields: doc.esignPlacedFields.filter(f => f.id !== fieldId) }
        : doc
    ));
  }, [activeIndex]);

  const handleFieldMouseDown = useCallback((e, fieldId) => {
    e.stopPropagation();
    e.preventDefault();
    setDraggingFieldId(fieldId);

    const container = pdfContainerRef.current;
    if (!container) return;

    const startX = e.clientX;
    const startY = e.clientY;
    const rect = container.getBoundingClientRect();

    const handleMouseMove = (moveE) => {
      const dx = (moveE.clientX - startX) / rect.width * PDF_PAGE_WIDTH;
      const dy = (moveE.clientY - startY) / rect.height * PDF_PAGE_HEIGHT;

      setDocuments(prev => prev.map((doc, i) => {
        if (i !== activeIndex) return doc;
        const field = doc.esignPlacedFields.find(f => f.id === fieldId);
        if (!field) return doc;
        return {
          ...doc,
          esignPlacedFields: doc.esignPlacedFields.map(f =>
            f.id === fieldId
              ? {
                  ...f,
                  x: Math.max(0, Math.min(PDF_PAGE_WIDTH - f.w, field.x + dx)),
                  y: Math.max(0, Math.min(PDF_PAGE_HEIGHT - f.h, field.y - dy)),
                }
              : f
          ),
        };
      }));
    };

    const handleMouseUp = () => {
      setDraggingFieldId(null);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
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

    const esignWithoutFile = documents.filter(d => d.requireEsign && !d.esignFile);
    if (esignWithoutFile.length > 0) {
      setError('Please upload a PDF for all documents requiring e-signature.');
      return;
    }

    const esignWithoutFields = documents.filter(d => d.requireEsign && d.esignFile && d.esignPlacedFields.length === 0);
    if (esignWithoutFields.length > 0) {
      setError('Please place at least one field (signature, date, etc.) on each e-sign document.');
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
          const storageKey = uploadResult?.storage_key;
          const originalFilename = uploadResult?.filename || doc.esignFileName;

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

          // Build fields from user-placed positions
          const fieldsPayload = doc.esignPlacedFields.map(f => ({
            type: f.type,
            page: f.page,
            x: Math.round(f.x),
            y: Math.round(f.y),
            w: Math.round(f.w),
            h: Math.round(f.h),
            recipient_index: f.recipientIndex || 0,
            required: true,
          }));
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
    setActiveFieldTool(null);
    setPdfBlobUrl(null);
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
                  {r.warning && r.error?.includes('e-sign') && (
                    <span className="result-hint">Use the E-Sign button on the client page to retry.</span>
                  )}
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
                    {!activeDoc.esignFile ? (
                      <div className="form-section">
                        <label>Upload Document for Signing</label>
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
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".pdf,application/pdf"
                          style={{ display: 'none' }}
                          onChange={handleEsignFileSelect}
                        />
                      </div>
                    ) : (
                      <>
                        {/* File info bar */}
                        <div className="esign-file-bar">
                          <span className="file-icon">&#128196;</span>
                          <span className="file-name">{activeDoc.esignFileName}</span>
                          <span className="file-size">
                            {(activeDoc.esignFile.size / 1024).toFixed(0)} KB
                          </span>
                          <button
                            type="button"
                            className="file-remove-btn"
                            onClick={handleRemoveEsignFile}
                            title="Remove file"
                          >
                            &times;
                          </button>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf,application/pdf"
                            style={{ display: 'none' }}
                            onChange={handleEsignFileSelect}
                          />
                        </div>

                        {/* Signer Selection */}
                        <div className="form-section" style={{ marginBottom: 8 }}>
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

                        {/* Field Placement Toolbar */}
                        <div className="placement-toolbar">
                          <span className="toolbar-label">
                            {activeFieldTool
                              ? `Click on the document to place a ${ESIGN_FIELD_CONFIG[activeFieldTool].label} field`
                              : 'Select a field type, then click on the document to place it'}
                          </span>
                          <div className="toolbar-buttons">
                            {Object.entries(ESIGN_FIELD_CONFIG).map(([type, config]) => (
                              <button
                                key={type}
                                type="button"
                                className={`field-tool-btn ${activeFieldTool === type ? 'active' : ''}`}
                                style={{
                                  borderColor: activeFieldTool === type ? config.color : '#ccc',
                                  color: activeFieldTool === type ? config.color : '#555',
                                  backgroundColor: activeFieldTool === type ? `${config.color}10` : '#fff',
                                }}
                                onClick={() => setActiveFieldTool(activeFieldTool === type ? null : type)}
                              >
                                <span className="field-tool-icon">{config.icon}</span>
                                {config.label}
                              </button>
                            ))}
                          </div>
                          {activeDoc.esignPlacedFields.length > 0 && (
                            <span className="field-count">
                              {activeDoc.esignPlacedFields.length} field{activeDoc.esignPlacedFields.length !== 1 ? 's' : ''} placed
                            </span>
                          )}
                        </div>

                        {/* PDF Viewer + Field Placement */}
                        <div className="pdf-placement-wrapper">
                          <div
                            ref={pdfContainerRef}
                            className={`pdf-placement-container ${activeFieldTool ? 'placing' : ''}`}
                            onClick={handlePlaceField}
                          >
                            {pdfBlobUrl && (
                              <iframe
                                src={`${pdfBlobUrl}#toolbar=0&navpanes=0`}
                                className="pdf-background-frame"
                                title="Document Preview"
                              />
                            )}
                            <div className="pdf-field-overlay">
                              {activeDoc.esignPlacedFields.map((field) => {
                                const config = ESIGN_FIELD_CONFIG[field.type] || ESIGN_FIELD_CONFIG.text;
                                const leftPct = (field.x / PDF_PAGE_WIDTH) * 100;
                                const topPct = ((PDF_PAGE_HEIGHT - field.y - field.h) / PDF_PAGE_HEIGHT) * 100;
                                const widthPct = (field.w / PDF_PAGE_WIDTH) * 100;
                                const heightPct = (field.h / PDF_PAGE_HEIGHT) * 100;

                                return (
                                  <div
                                    key={field.id}
                                    className={`placed-field ${draggingFieldId === field.id ? 'dragging' : ''}`}
                                    style={{
                                      left: `${leftPct}%`,
                                      top: `${topPct}%`,
                                      width: `${widthPct}%`,
                                      height: `${heightPct}%`,
                                      borderColor: config.color,
                                      backgroundColor: `${config.color}20`,
                                    }}
                                    onMouseDown={(e) => handleFieldMouseDown(e, field.id)}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <span className="placed-field-label" style={{ color: config.color }}>
                                      {config.icon} {config.label}
                                    </span>
                                    <button
                                      type="button"
                                      className="placed-field-delete"
                                      onClick={(e) => { e.stopPropagation(); handleRemoveField(field.id); }}
                                    >
                                      &times;
                                    </button>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      </>
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
