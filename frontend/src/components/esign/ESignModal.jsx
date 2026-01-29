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
      // Get the document URL
      const documentUrl = document.file_url || document.s3_url;
      if (!documentUrl) {
        throw new Error('Document URL not available');
      }

      // Step 1: Create the envelope
      const envelopeData = {
        name: `${document.doc_type || 'Document'} - E-Signature`,
        document_url: documentUrl,
        loan_id: parseInt(loanId),
        metadata: {
          doc_type: document.doc_type,
          doc_id: document.id,
          loan_id: loanId,
        },
      };

      const createResponse = await esignApi.createEnvelope(envelopeData);
      const newEnvelope = createResponse.data || createResponse;
      setEnvelope(newEnvelope);

      // Step 2: Add signers
      for (const signer of signers) {
        await esignApi.addSigner(newEnvelope.id, {
          name: signer.name,
          email: signer.email,
          role: signer.role,
          signing_order: signer.order,
        });
      }

      // Step 3: Add default signature field for each signer
      let fieldY = 100; // Start 100 points from bottom of page

      for (let i = 0; i < signers.length; i++) {
        await esignApi.addField(newEnvelope.id, {
          field_type: 'signature',
          page_number: 1,
          x_position: 72, // 1 inch from left
          y_position: fieldY + (i * 80),
          width: 200,
          height: 50,
          signer_email: signers[i].email,
          required: true,
        });

        // Add date field next to signature
        await esignApi.addField(newEnvelope.id, {
          field_type: 'date_signed',
          page_number: 1,
          x_position: 300, // Right of signature
          y_position: fieldY + (i * 80),
          width: 120,
          height: 30,
          signer_email: signers[i].email,
          required: true,
        });
      }

      // Step 4: Send the envelope
      await esignApi.sendEnvelope(newEnvelope.id);

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
