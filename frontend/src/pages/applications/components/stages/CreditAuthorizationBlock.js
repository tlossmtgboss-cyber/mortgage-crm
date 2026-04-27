/**
 * CreditAuthorizationBlock — FCRA credit pull consent capture
 *
 * Displays the full credit authorization disclosure text, collects
 * the borrower's typed legal name, and submits to the POS consent API.
 * Shows a green checkmark once authorization is recorded.
 */

import React, { useState, useCallback } from 'react';

const CreditAuthorizationBlock = ({
  applicationToken,
  disclosureText,
  onAuthorized,
  isAuthorized = false,
  authorizedAt = null,
}) => {
  const [typedName, setTypedName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [authorized, setAuthorized] = useState(isAuthorized);
  const [timestamp, setTimestamp] = useState(authorizedAt);

  const handleAuthorize = useCallback(async () => {
    if (!typedName.trim() || typedName.trim().length < 2) {
      setError('Please type your full legal name');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const apiBase = process.env.REACT_APP_API_URL || '';
      const response = await fetch(
        `${apiBase}/api/v1/pos/consent/${applicationToken}/credit-auth`,
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
        throw new Error(data.detail || 'Failed to record authorization');
      }

      const data = await response.json();
      setAuthorized(true);
      setTimestamp(data.authorized_at || new Date().toISOString());
      if (onAuthorized) onAuthorized(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }, [typedName, applicationToken, onAuthorized]);

  if (authorized) {
    return (
      <div className="consent-block consent-block--completed">
        <div className="consent-block__header">
          <span className="consent-block__check">✓</span>
          <strong>Credit Authorization — Completed</strong>
        </div>
        <p className="consent-block__timestamp">
          Authorized on {new Date(timestamp).toLocaleString()}
        </p>
      </div>
    );
  }

  return (
    <div className="consent-block">
      <div className="consent-block__header">
        <strong>Credit Authorization</strong>
        <span className="consent-block__required">Required</span>
      </div>

      <div className="consent-block__text">
        {disclosureText || (
          <>
            <p>
              <strong>AUTHORIZATION TO OBTAIN CREDIT REPORT</strong>
            </p>
            <p>
              I hereby authorize the lender and its designated agents to obtain my
              credit report from one or more consumer reporting agencies. This
              authorization is granted pursuant to the Fair Credit Reporting Act,
              15 U.S.C. § 1681b(a)(3)(A).
            </p>
            <p>I understand that:</p>
            <ul>
              <li>My credit report will be used to evaluate my mortgage loan application</li>
              <li>This authorization covers both initial and any subsequent credit inquiries related to this application</li>
              <li>I may revoke this authorization at any time by contacting the lender in writing</li>
              <li>A copy of this authorization will be retained in the loan file</li>
            </ul>
          </>
        )}
      </div>

      <div className="consent-block__signature">
        <label className="consent-block__label">
          Type your full legal name to authorize:
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
        className="consent-block__button consent-block__button--authorize"
        onClick={handleAuthorize}
        disabled={submitting || !typedName.trim()}
      >
        {submitting ? 'Authorizing...' : 'I Authorize'}
      </button>
    </div>
  );
};

export default CreditAuthorizationBlock;
