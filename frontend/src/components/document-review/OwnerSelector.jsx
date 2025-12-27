/**
 * OwnerSelector
 *
 * Dropdown component for selecting document owner (Borrower/Co-Borrower).
 * Shows AI-detected suggestion with confidence indicator.
 */

import React from 'react';
import './OwnerSelector.css';

const OwnerSelector = ({
  borrowerName,
  coBorrowerName,
  selectedOwner,
  suggestedOwner,
  ownerConfidence,
  onChange,
}) => {
  const getConfidenceClass = (confidence) => {
    if (!confidence) return '';
    if (confidence >= 80) return 'high';
    if (confidence >= 60) return 'medium';
    return 'low';
  };

  const getConfidenceLabel = (confidence) => {
    if (!confidence) return '';
    if (confidence >= 80) return 'High confidence';
    if (confidence >= 60) return 'Medium confidence';
    return 'Low confidence';
  };

  const hasCoBorrower = coBorrowerName && coBorrowerName.trim().length > 0;

  return (
    <div className="owner-selector">
      <label className="owner-label">Document Owner:</label>

      <div className="owner-options">
        {/* Borrower Option */}
        <button
          type="button"
          className={`owner-option ${selectedOwner === 'BORROWER' ? 'selected' : ''}`}
          onClick={() => onChange('BORROWER')}
        >
          <span className="owner-name">
            {borrowerName || 'Borrower'}
          </span>
          {suggestedOwner === 'BORROWER' && ownerConfidence && (
            <span
              className={`suggestion-badge ${getConfidenceClass(ownerConfidence)}`}
              title={getConfidenceLabel(ownerConfidence)}
            >
              AI {ownerConfidence}%
            </span>
          )}
        </button>

        {/* Co-Borrower Option */}
        {hasCoBorrower && (
          <button
            type="button"
            className={`owner-option ${selectedOwner === 'CO_BORROWER' ? 'selected' : ''}`}
            onClick={() => onChange('CO_BORROWER')}
          >
            <span className="owner-name">
              {coBorrowerName}
            </span>
            {suggestedOwner === 'CO_BORROWER' && ownerConfidence && (
              <span
                className={`suggestion-badge ${getConfidenceClass(ownerConfidence)}`}
                title={getConfidenceLabel(ownerConfidence)}
              >
                AI {ownerConfidence}%
              </span>
            )}
          </button>
        )}

        {/* Joint/Both Option */}
        {hasCoBorrower && (
          <button
            type="button"
            className={`owner-option ${selectedOwner === 'BOTH' ? 'selected' : ''}`}
            onClick={() => onChange('BOTH')}
          >
            <span className="owner-name">Both</span>
          </button>
        )}
      </div>

      {/* Unknown suggestion warning */}
      {suggestedOwner === 'UNKNOWN' && (
        <div className="owner-warning">
          <span className="warning-icon">⚠</span>
          <span>Could not detect owner from document. Please select manually.</span>
        </div>
      )}
    </div>
  );
};

export default OwnerSelector;
