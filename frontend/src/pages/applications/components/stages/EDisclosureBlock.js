/**
 * EDisclosureBlock — E-SIGN Act electronic disclosure consent capture
 *
 * Displays the e-disclosure agreement text including hardware/software
 * requirements, right to withdraw, and paper copy information.
 * Collects typed legal name and submits to POS consent API.
 */

import React, { useState, useCallback } from 'react';

const EDisclosureBlock = ({
  applicationToken,
  disclosureData,
  onConsented,
  isConsented = false,
  consentedAt = null,
}) => {
  const [typedName, setTypedName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [consented, setConsented] = useState(isConsented);
  const [timestamp, setTimestamp] = useState(consentedAt);

  const handleConsent = useCallback(async () => {
    if (!typedName.trim() || typedName.trim().length < 2) {
      setError('Please type your full legal name');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const apiBase = process.env.REACT_APP_API_URL || '';
      const response = await fetch(
        `${apiBase}/api/v1/pos/consent/${applicationToken}/e-disclosure`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            typed_full_name: typedName.trim(),
            consent_agreed: true,
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to record consent');
      }

      const data = await response.json();
      setConsented(true);
      setTimestamp(data.consented_at || new Date().toISOString());
      if (onConsented) onConsented(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }, [typedName, applicationToken, onConsented]);

  if (consented) {
    return (
      <div className="consent-block consent-block--completed">
        <div className="consent-block__header">
          <span className="consent-block__check">✓</span>
          <strong>Electronic Disclosure Consent — Completed</strong>
        </div>
        <p className="consent-block__timestamp">
          Consented on {new Date(timestamp).toLocaleString()}
        </p>
      </div>
    );
  }

  const hwReqs = disclosureData?.hardware_software_requirements ||
    'To access electronic disclosures, you need: a device with internet access, ' +
    'a current web browser (Chrome, Safari, Firefox, or Edge), and the ability ' +
    'to receive email. PDF documents require a PDF reader such as Adobe Acrobat.';

  const withdrawInfo = disclosureData?.right_to_withdraw ||
    'You may withdraw your consent to receive electronic disclosures at any time ' +
    'by contacting us in writing.';

  const paperInfo = disclosureData?.paper_copy_info ||
    'You may request a paper copy of any electronic disclosure at no charge by ' +
    'contacting your loan officer.';

  return (
    <div className="consent-block">
      <div className="consent-block__header">
        <strong>Electronic Disclosure Consent</strong>
        <span className="consent-block__required">Required</span>
      </div>

      <div className="consent-block__text">
        <p>
          <strong>CONSENT TO RECEIVE ELECTRONIC DISCLOSURES</strong>
        </p>
        <p>
          In accordance with the Electronic Signatures in Global and National
          Commerce Act (E-SIGN Act), I consent to receive all mortgage-related
          disclosures, notices, and documents electronically.
        </p>

        <p>I understand that:</p>
        <ul>
          <li>I am agreeing to receive the Loan Estimate, Closing Disclosure, and all other required mortgage disclosures electronically</li>
          <li>I may withdraw this consent at any time and request paper copies at no charge</li>
          <li>Withdrawing consent will not affect the legal validity of any electronic disclosures previously provided</li>
        </ul>

        <div className="consent-block__detail">
          <strong>Hardware/Software Requirements:</strong>
          <p>{hwReqs}</p>
        </div>

        <div className="consent-block__detail">
          <strong>Right to Withdraw:</strong>
          <p>{withdrawInfo}</p>
        </div>

        <div className="consent-block__detail">
          <strong>Paper Copies:</strong>
          <p>{paperInfo}</p>
        </div>
      </div>

      <div className="consent-block__signature">
        <label className="consent-block__label">
          Type your full legal name to consent:
        </label>
        <input
          type="text"
          className="consent-block__input"
          placeholder="Your full legal name"
          value={typedName}
          onChange={(e) => setTypedName(e.target.value)}
          disabled={submitting}
          autoComplete="name"
        />
      </div>

      {error && <p className="consent-block__error">{error}</p>}

      <button
        className="consent-block__button consent-block__button--consent"
        onClick={handleConsent}
        disabled={submitting || !typedName.trim()}
      >
        {submitting ? 'Recording Consent...' : 'I Agree'}
      </button>
    </div>
  );
};

export default EDisclosureBlock;
