/**
 * PhoneInput - Formatted phone number input
 * Formats as (XXX) XXX-XXXX
 */

import React, { useState, useEffect, forwardRef } from 'react';
import './PhoneInput.css';

// Format phone number
const formatPhone = (value) => {
  if (!value) return '';

  // Remove non-digits
  const digits = String(value).replace(/\D/g, '');

  if (digits.length <= 3) {
    return digits.length > 0 ? `(${digits}` : '';
  } else if (digits.length <= 6) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  } else {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
  }
};

// Get raw digits
const getDigits = (value) => {
  if (!value) return '';
  return String(value).replace(/\D/g, '').slice(0, 10);
};

const PhoneInput = forwardRef(({
  value,
  onChange,
  onBlur,
  placeholder = '(555) 555-5555',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
  autoFocus = false,
}, ref) => {
  const [displayValue, setDisplayValue] = useState('');

  // Sync display value with external value
  useEffect(() => {
    setDisplayValue(formatPhone(value));
  }, [value]);

  const handleChange = (e) => {
    const input = e.target.value;

    // Get raw digits
    const digits = getDigits(input);

    // Update display with formatted value
    setDisplayValue(formatPhone(digits));

    // Notify parent with raw digits
    onChange(digits);
  };

  const handleBlur = (e) => {
    if (onBlur) onBlur(e);
  };

  return (
    <div className={`phone-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="phone-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="phone-input-container">
        <span className="phone-icon">📱</span>
        <input
          ref={ref}
          type="tel"
          inputMode="tel"
          value={displayValue}
          onChange={handleChange}
          onBlur={handleBlur}
          placeholder={placeholder}
          disabled={disabled}
          className="phone-input"
          autoComplete="tel"
          autoFocus={autoFocus}
          maxLength={14} // (XXX) XXX-XXXX
        />
      </div>

      {helpText && !error && (
        <div className="phone-input-help">{helpText}</div>
      )}

      {error && <div className="phone-input-error">{error}</div>}
    </div>
  );
});

PhoneInput.displayName = 'PhoneInput';

export default PhoneInput;
