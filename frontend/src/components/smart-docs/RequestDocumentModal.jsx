/**
 * RequestDocumentModal - Request documents from borrowers
 *
 * Features:
 * - Select document type (including Letter of Explanation)
 * - Custom instructions for the borrower
 * - Option to require e-signature
 * - Email notification to borrower
 */

import React, { useState } from 'react';
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

function RequestDocumentModal({
  isOpen,
  onClose,
  loanId,
  borrowerId,
  borrowerName,
  borrowerEmail,
  onSuccess,
}) {
  const [docType, setDocType] = useState('LOE');
  const [loeTemplate, setLoeTemplate] = useState('custom');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [requireEsign, setRequireEsign] = useState(true);
  const [priority, setPriority] = useState('normal');
  const [dueDate, setDueDate] = useState('');
  const [sendNotification, setSendNotification] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  // Update form when doc type changes
  const handleDocTypeChange = (newType) => {
    setDocType(newType);
    const docInfo = DOCUMENT_TYPES.find(d => d.value === newType);
    setRequireEsign(docInfo?.requiresEsign || false);

    if (newType === 'LOE') {
      setTitle('Letter of Explanation');
    } else {
      setTitle(docInfo?.label || '');
    }
    setDescription('');
    setInstructions('');
  };

  // Update instructions when LOE template changes
  const handleLoeTemplateChange = (template) => {
    setLoeTemplate(template);
    const templateInfo = LOE_TEMPLATES.find(t => t.value === template);
    if (templateInfo && template !== 'custom') {
      setTitle(`Letter of Explanation - ${templateInfo.label.replace(' Explanation', '')}`);
      setInstructions(templateInfo.prompt);
    } else {
      setTitle('Letter of Explanation');
      setInstructions('');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!title.trim()) {
      setError('Please enter a document title');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const requestData = {
        title: title.trim(),
        description: description.trim() || `${docType} requested`,
        instructions: instructions.trim(),
        priority,
        due_date: dueDate || null,
        send_notification: sendNotification,
        borrower_email: borrowerEmail,
        borrower_name: borrowerName,
        doc_type: docType,
        requires_esign: requireEsign,
      };

      await addCustomRequest(loanId, borrowerId, requestData);

      setSuccess(true);

      if (onSuccess) {
        onSuccess();
      }

      // Reset form after short delay
      setTimeout(() => {
        handleClose();
      }, 2000);

    } catch (err) {
      console.error('Error requesting document:', err);
      setError(err.message || 'Failed to send document request');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setDocType('LOE');
    setLoeTemplate('custom');
    setTitle('');
    setDescription('');
    setInstructions('');
    setRequireEsign(true);
    setPriority('normal');
    setDueDate('');
    setError(null);
    setSuccess(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="request-doc-modal-overlay" onClick={handleClose}>
      <div className="request-doc-modal" onClick={(e) => e.stopPropagation()}>
        <div className="request-doc-header">
          <h2>Request Document</h2>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        {success ? (
          <div className="request-doc-success">
            <div className="success-icon">✓</div>
            <h3>Request Sent!</h3>
            <p>
              {sendNotification
                ? `${borrowerName || 'The borrower'} has been notified via email.`
                : 'The document request has been added to the needs list.'}
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="request-doc-form">
            {/* Document Type Selection */}
            <div className="form-section">
              <label>Document Type</label>
              <div className="doc-type-grid">
                {DOCUMENT_TYPES.map((doc) => (
                  <button
                    key={doc.value}
                    type="button"
                    className={`doc-type-btn ${docType === doc.value ? 'active' : ''}`}
                    onClick={() => handleDocTypeChange(doc.value)}
                  >
                    {doc.label}
                    {doc.requiresEsign && <span className="esign-badge">E-Sign</span>}
                  </button>
                ))}
              </div>
            </div>

            {/* LOE Template Selection */}
            {docType === 'LOE' && (
              <div className="form-section">
                <label>LOE Template</label>
                <select
                  value={loeTemplate}
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
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Document title"
                className="form-input"
                required
              />
            </div>

            {/* Instructions */}
            <div className="form-section">
              <label>Instructions for Borrower</label>
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="What should the borrower include in this document?"
                className="form-textarea"
                rows={4}
              />
            </div>

            {/* Options Row */}
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

            {/* E-Sign Toggle */}
            <div className="form-section">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={requireEsign}
                  onChange={(e) => setRequireEsign(e.target.checked)}
                />
                <span>Require E-Signature</span>
                <span className="checkbox-hint">
                  Borrower will sign the document electronically after completing it
                </span>
              </label>
            </div>

            {/* Send Notification Toggle */}
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

            {error && <div className="error-message">{error}</div>}

            {/* Actions */}
            <div className="form-actions">
              <button type="button" className="btn-cancel" onClick={handleClose}>
                Cancel
              </button>
              <button type="submit" className="btn-submit" disabled={loading}>
                {loading ? 'Sending...' : 'Send Request'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default RequestDocumentModal;
