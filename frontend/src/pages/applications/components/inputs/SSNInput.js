/**
 * SSNInput - Masked Social Security Number input
 * Displays as XXX-XX-1234 (last 4 visible) when not focused
 * Validates: 9 digits, not all zeros, not starting with 9 or 666
 */

import React, { useState, useEffect, forwardRef } from 'react';
import './SSNInput.css';

// Format SSN with dashes
const formatSSN = (value) => {
  if (!value) return '';

  // Remove non-digits
  const digits = String(value).replace(/\D/g, '');

  if (digits.length <= 3) {
    return digits;
  } else if (digits.length <= 5) {
    return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  } else {
    return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5, 9)}`;
  }
};

// Mask SSN showing only last 4
const maskSSN = (value) => {
  if (!value) return '';

  const digits = String(value).replace(/\D/g, '');

  if (digits.length < 9) {
    return formatSSN(digits);
  }

  return `XXX-XX-${digits.slice(5, 9)}`;
};

// Get raw digits
const getDigits = (value) => {
  if (!value) return '';
  return String(value).replace(/\D/g, '').slice(0, 9);
};

// Validate SSN format
export const validateSSN = (value) => {
  if (!value) return 'Social Security Number is required';

  const digits = String(value).replace(/\D/g, '');

  if (digits.length !== 9) {
    return `SSN must be 9 digits (currently ${digits.length})`;
  }

  if (digits === '000000000') {
    return 'Please enter a valid SSN';
  }

  // Area number (first 3) cannot be 000, 666, or 900-999
  const area = digits.slice(0, 3);
  if (area === '000' || area === '666' || parseInt(area, 10) >= 900) {
    return 'Please enter a valid SSN';
  }

  // Group number (middle 2) cannot be 00
  if (digits.slice(3, 5) === '00') {
    return 'Please enter a valid SSN';
  }

  // Serial number (last 4) cannot be 0000
  if (digits.slice(5, 9) === '0000') {
    return 'Please enter a valid SSN';
  }

  return null; // Valid
};

const SSNInput = forwardRef(({
  value,
  onChange,
  onBlur,
  onKeyDown,
  placeholder = 'XXX-XX-XXXX',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
  autoFocus = false,
}, ref) => {
  const [displayValue, setDisplayValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState(null);

  // Sync display value with external value
  useEffect(() => {
    if (!isFocused) {
      setDisplayValue(maskSSN(value));
    }
  }, [value, isFocused]);

  const handleChange = (e) => {
    const input = e.target.value;

    // Get raw digits
    const digits = getDigits(input);

    // Update display with formatted value
    setDisplayValue(formatSSN(digits));

    // Clear local error while typing
    if (localError) setLocalError(null);

    // Notify parent with raw digits
    onChange(digits);
  };

  const handleFocus = () => {
    setIsFocused(true);
    // Show full formatted SSN on focus
    setDisplayValue(formatSSN(value));
  };

  const handleBlur = (e) => {
    setIsFocused(false);
    // Mask on blur
    setDisplayValue(maskSSN(value));

    // Validate on blur if there's a value
    const digits = getDigits(value);
    if (digits.length > 0 && digits.length < 9) {
      setLocalError(`SSN must be 9 digits (currently ${digits.length})`);
    } else if (digits.length === 9) {
      const validationError = validateSSN(digits);
      setLocalError(validationError);
    } else {
      setLocalError(null);
    }

    if (onBlur) onBlur(e);
  };

  const toggleVisibility = () => {
    setShowPassword(!showPassword);
    if (!showPassword) {
      setDisplayValue(formatSSN(value));
    } else {
      setDisplayValue(maskSSN(value));
    }
  };

  // Determine what to show
  const visibleValue = isFocused || showPassword ? formatSSN(value) : displayValue;
  const displayError = error || localError;

  return (
    <div className={`ssn-input-wrapper ${className} ${displayError ? 'has-error' : ''}`}>
      {label && (
        <label className="ssn-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="ssn-input-container">
        <input
          ref={ref}
          type={isFocused || showPassword ? 'text' : 'password'}
          inputMode="numeric"
          value={visibleValue}
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="ssn-input"
          autoComplete="off"
          autoFocus={autoFocus}
          maxLength={11} // XXX-XX-XXXX
          aria-required={required}
        />
        <button
          type="button"
          className="ssn-toggle"
          onClick={toggleVisibility}
          tabIndex={-1}
          aria-label={showPassword ? 'Hide SSN' : 'Show SSN'}
        >
          {showPassword || isFocused ? '🙈' : '👁️'}
        </button>
      </div>

      {helpText && !displayError && (
        <div className="ssn-input-help">{helpText}</div>
      )}

      {displayError && <div className="ssn-input-error" role="alert">{displayError}</div>}
    </div>
  );
});

SSNInput.displayName = 'SSNInput';

export default SSNInput;
