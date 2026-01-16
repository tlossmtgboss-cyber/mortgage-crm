/**
 * BooleanInput - Yes/No toggle for boolean questions
 */

import React from 'react';
import './BooleanInput.css';

const BooleanInput = ({
  value,
  onChange,
  yesLabel = 'Yes',
  noLabel = 'No',
  disabled = false,
  error,
  className = '',
}) => {
  const handleSelect = (newValue) => {
    if (disabled) return;
    onChange(newValue);
  };

  return (
    <div className={`boolean-input ${className} ${error ? 'has-error' : ''}`}>
      <div className="boolean-options">
        <button
          type="button"
          className={`boolean-option ${value === true ? 'selected' : ''} ${disabled ? 'disabled' : ''}`}
          onClick={() => handleSelect(true)}
          disabled={disabled}
          aria-pressed={value === true}
        >
          <span className="boolean-icon">✓</span>
          <span className="boolean-label">{yesLabel}</span>
        </button>

        <button
          type="button"
          className={`boolean-option ${value === false ? 'selected selected-no' : ''} ${disabled ? 'disabled' : ''}`}
          onClick={() => handleSelect(false)}
          disabled={disabled}
          aria-pressed={value === false}
        >
          <span className="boolean-icon">✕</span>
          <span className="boolean-label">{noLabel}</span>
        </button>
      </div>

      {error && <div className="boolean-error">{error}</div>}
    </div>
  );
};

export default BooleanInput;
