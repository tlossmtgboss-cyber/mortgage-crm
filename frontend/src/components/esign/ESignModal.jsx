/**
 * ESignModal - E-Signature creation modal for Smart Docs
 *
 * Allows users to:
 * - Select a document to send for e-signature
 * - Add signers (borrower, co-borrower, etc.)
 * - Send the envelope for signing
 */

import React, { useState, useEffect } from 'react';
import { esignApi } from '../../services/esignApi';
import './ESignModal.css';

const SIGNER_ROLES = [
  { value: 'borrower', label: 'Borrower' },
  { value: 'co_borrower', label: 'Co-Borrower' },
  { value: 'seller', label: 'Seller' },
  { value: 'agent', label: 'Agent' },
  { value: 'other', label: 'Other' },
];

function ESignModal({
  isOpen,
  onClose,
  document,
  loanId,
  borrowerName,
  borrowerEmail,
  coBorrowerName,
  coBorrowerEmail,
  onSuccess
}) {
  const [step, setStep] = useState('signers'); // signers, sending, success
  const [signers, setSigners] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [_envelope, setEnvelope] = useState(null); // eslint-disable-line no-unused-vars

  // Initialize signers with borrower info
  useEffect(() => {
    if (isOpen) {
      const initialSigners = [];

      if (borrowerName || borrowerEmail) {
        initialSigners.push({
          id: Date.now(),
          name: borrowerName || '',
          email: borrowerEmail || '',
          role: 'borrower',
          order: 1,
        });
      }

      if (coBorrowerName || coBorrowerEmail) {
        initialSigners.push({
          id: Date.now() + 1,
          name: coBorrowerName || '',
          email: coBorrowerEmail || '',
          role: 'co_borrower',
          order: 2,
        });
      }

      // If no signers, add empty one
      if (initialSigners.length === 0) {
        initialSigners.push({
          id: Date.now(),
          name: '',
          email: '',
          role: 'borrower',
          order: 1,
        });
      }

      setSigners(initialSigners);
      setStep('signers');
      setError(null);
      setEnvelope(null);
    }
  }, [isOpen, borrowerName, borrowerEmail, coBorrowerName, coBorrowerEmail]);

  const addSigner = () => {
    setSigners([
      ...signers,
      {
        id: Date.now(),
        name: '',
        email: '',
        role: 'other',
        order: signers.length + 1,
      },
    ]);
  };

  const removeSigner = (id) => {
    if (signers.length <= 1) return;
    setSigners(signers.filter((s) => s.id !== id));
  };

  const updateSigner = (id, field, value) => {
    setSigners(
      signers.map((s) => (s.id === id ? { ...s, [field]: value } : s))
    );
  };

  const validateSigners = () => {
    for (const signer of signers) {
      if (!signer.name.trim()) {
        setError('All signers must have a name');
        return false;
      }
      if (!signer.email.trim() || !signer.email.includes('@')) {
        setError('All signers must have a valid email');
        return false;
      }
    }
    return true;
  };

  const handleSendForSignature = async () => {
    if (!validateSigners()) return;

    setLoading(true);
    setError(null);
    setStep('sending');

    try {
      // Get the document storage key (S3 key, not URL)
      const storageKey = document.storage_key || document.s3_key
        || document.file_url || document.s3_url;
      if (!storageKey) {
        throw new Error('Document storage key not available');
      }

      // Build recipients array matching backend EnvelopeRecipientInput schema
      const recipients = signers.map((signer) => ({
        name: signer.name,
        email: signer.email,
        type: signer.role === 'borrower' || signer.role === 'co_borrower' ? 'signer' : signer.role,
        signing_order: signer.order,
        auth_method: 'email_link',
      }));

      // Build fields array matching backend EnvelopeFieldInput schema
      // (type/page/x/y/w/h/recipient_index — NOT field_type/page_number/x_position/signer_email)
      const fields = [];
      const baseY = 100; // 100 points from bottom of page

      for (let i = 0; i < signers.length; i++) {
        // Signature field
        fields.push({
          type: 'signature',
          page: 1,
          x: 72,
          y: baseY + (i * 80),
          w: 200,
          h: 50,
          recipient_index: i,
          required: true,
        });
        // Date field next to signature
        fields.push({
          type: 'date_signed',
          page: 1,
          x: 300,
          y: baseY + (i * 80),
          w: 120,
          h: 30,
          recipient_index: i,
          required: true,
        });
      }

      // Single createEnvelope call with recipients + fields (batch)
      const envelopeData = {
        title: `${document.doc_type || 'Document'} - E-Signature`,
        document_storage_key: storageKey,
        original_filename: document.filename || document.file_name,
        loan_id: parseInt(loanId),
        recipients,
        fields,
      };

      const createResponse = await esignApi.createEnvelope(envelopeData);
      const newEnvelope = createResponse.data || createResponse;
      setEnvelope(newEnvelope);

      // Send the envelope using envelope_uuid (not integer id)
      const envelopeUuid = newEnvelope.envelope_uuid || newEnvelope.id;
      await esignApi.sendEnvelope(envelopeUuid);

      setStep('success');

      if (onSuccess) {
        onSuccess(newEnvelope);
      }
    } catch (err) {
      console.error('E-sign error:', err);
      setError(err.message || 'Failed to send for e-signature');
      setStep('signers');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="esign-modal-overlay" onClick={onClose}>
      <div className="esign-modal" onClick={(e) => e.stopPropagation()}>
        <div className="esign-modal-header">
          <h2>Send for E-Signature</h2>
          <button className="close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="esign-modal-content">
          {/* Document Info */}
          <div className="document-info-section">
            <h3>Document</h3>
            <div className="document-card">
              <span className="doc-icon">📄</span>
              <div className="doc-details">
                <span className="doc-name">
                  {document?.doc_type?.replace(/_/g, ' ') || 'Document'}
                </span>
                <span className="doc-file">{document?.filename || 'PDF Document'}</span>
              </div>
            </div>
          </div>

          {step === 'signers' && (
            <>
              {/* Signers Section */}
              <div className="signers-section">
                <div className="section-header">
                  <h3>Signers</h3>
                  <button className="add-signer-btn" onClick={addSigner}>
                    + Add Signer
                  </button>
                </div>

                <div className="signers-list">
                  {signers.map((signer, index) => (
                    <div key={signer.id} className="signer-row">
                      <span className="signer-number">{index + 1}</span>

                      <div className="signer-fields">
                        <input
                          type="text"
                          placeholder="Name"
                          value={signer.name}
                          onChange={(e) =>
                            updateSigner(signer.id, 'name', e.target.value)
                          }
                          className="signer-input"
                        />
                        <input
                          type="email"
                          placeholder="Email"
                          value={signer.email}
                          onChange={(e) =>
                            updateSigner(signer.id, 'email', e.target.value)
                          }
                          className="signer-input"
                        />
                        <select
                          value={signer.role}
                          onChange={(e) =>
                            updateSigner(signer.id, 'role', e.target.value)
                          }
                          className="signer-select"
                        >
                          {SIGNER_ROLES.map((role) => (
                            <option key={role.value} value={role.value}>
                              {role.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      {signers.length > 1 && (
                        <button
                          className="remove-signer-btn"
                          onClick={() => removeSigner(signer.id)}
                        >
                          &times;
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {error && <div className="error-message">{error}</div>}

              {/* Actions */}
              <div className="esign-modal-actions">
                <button className="btn-cancel" onClick={onClose}>
                  Cancel
                </button>
                <button
                  className="btn-send"
                  onClick={handleSendForSignature}
                  disabled={loading}
                >
                  {loading ? 'Sending...' : 'Send for Signature'}
                </button>
              </div>
            </>
          )}

          {step === 'sending' && (
            <div className="sending-status">
              <div className="spinner" />
              <p>Preparing and sending for signature...</p>
            </div>
          )}

          {step === 'success' && (
            <div className="success-status">
              <div className="success-icon">✓</div>
              <h3>Sent for Signature!</h3>
              <p>
                The document has been sent to {signers.length} signer
                {signers.length !== 1 ? 's' : ''}.
              </p>
              <ul className="sent-to-list">
                {signers.map((signer) => (
                  <li key={signer.id}>
                    {signer.name} ({signer.email})
                  </li>
                ))}
              </ul>
              <button className="btn-done" onClick={onClose}>
                Done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ESignModal;
