/**
 * DateInput - Date input with MM/DD/YYYY format
 */

import React, { useState, useEffect, forwardRef } from 'react';
import './DateInput.css';

// Format date as MM/DD/YYYY
const formatDate = (value) => {
  if (!value) return '';

  // Remove non-digits
  const digits = String(value).replace(/\D/g, '');

  if (digits.length <= 2) {
    return digits;
  } else if (digits.length <= 4) {
    return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  } else {
    return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4, 8)}`;
  }
};

// Get raw digits
const getDigits = (value) => {
  if (!value) return '';
  return String(value).replace(/\D/g, '').slice(0, 8);
};

// Validate date
const isValidDate = (value) => {
  if (!value || value.length !== 8) return false;

  const month = parseInt(value.slice(0, 2), 10);
  const day = parseInt(value.slice(2, 4), 10);
  const year = parseInt(value.slice(4, 8), 10);

  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  if (year < 1900 || year > 2100) return false;

  // Create date and check if it's valid
  const date = new Date(year, month - 1, day);
  return date.getMonth() === month - 1 && date.getDate() === day;
};

// Convert to ISO format for storage
const toISODate = (value) => {
  const digits = getDigits(value);
  if (digits.length !== 8 || !isValidDate(digits)) return null;

  const month = digits.slice(0, 2);
  const day = digits.slice(2, 4);
  const year = digits.slice(4, 8);

  return `${year}-${month}-${day}`;
};

// Convert from ISO format
const fromISODate = (isoValue) => {
  if (!isoValue) return '';

  // Handle both ISO (YYYY-MM-DD) and MMDDYYYY formats
  if (isoValue.includes('-')) {
    const parts = isoValue.split('-');
    if (parts.length === 3) {
      return `${parts[1]}${parts[2]}${parts[0]}`;
    }
  }

  return isoValue;
};

const DateInput = forwardRef(({
  value,
  onChange,
  onBlur,
  placeholder = 'MM/DD/YYYY',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
  minYear = 1900,
  maxYear = new Date().getFullYear() + 10,
  autoFocus = false,
}, ref) => {
  const [displayValue, setDisplayValue] = useState('');
  const [internalError, setInternalError] = useState('');

  // Sync display value with external value
  useEffect(() => {
    const digits = fromISODate(value);
    setDisplayValue(formatDate(digits));
  }, [value]);

  const handleChange = (e) => {
    const input = e.target.value;

    // Get raw digits
    const digits = getDigits(input);

    // Update display with formatted value
    setDisplayValue(formatDate(digits));

    // Clear internal error on change
    setInternalError('');

    // Validate and notify parent
    if (digits.length === 8) {
      if (isValidDate(digits)) {
        const iso = toISODate(digits);
        onChange(iso);
      } else {
        setInternalError('Invalid date');
      }
    } else if (digits.length === 0) {
      onChange(null);
    }
  };

  const handleBlur = (e) => {
    const digits = getDigits(displayValue);

    // Validate on blur
    if (digits.length > 0 && digits.length < 8) {
      setInternalError('Complete the date (MM/DD/YYYY)');
    } else if (digits.length === 8 && !isValidDate(digits)) {
      setInternalError('Invalid date');
    }

    if (onBlur) onBlur(e);
  };

  const displayError = error || internalError;

  return (
    <div className={`date-input-wrapper ${className} ${displayError ? 'has-error' : ''}`}>
      {label && (
        <label className="date-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="date-input-container">
        <span className="date-icon">📅</span>
        <input
          ref={ref}
          type="text"
          inputMode="numeric"
          value={displayValue}
          onChange={handleChange}
          onBlur={handleBlur}
          placeholder={placeholder}
          disabled={disabled}
          className="date-input"
          autoComplete="off"
          autoFocus={autoFocus}
          maxLength={10} // MM/DD/YYYY
        />
      </div>

      {helpText && !displayError && (
        <div className="date-input-help">{helpText}</div>
      )}

      {displayError && <div className="date-input-error">{displayError}</div>}
    </div>
  );
});

DateInput.displayName = 'DateInput';

export default DateInput;
