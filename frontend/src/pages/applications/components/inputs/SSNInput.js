/**
 * SSNInput - Masked Social Security Number input
 * Displays as XXX-XX-1234 (last 4 visible) when not focused
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

const SSNInput = forwardRef(({
  value,
  onChange,
  onBlur,
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

  return (
    <div className={`ssn-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="ssn-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="ssn-input-container">
        <input
          ref={ref}
          type={isFocused || showPassword ? 'text' : 'text'}
          inputMode="numeric"
          value={visibleValue}
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder={placeholder}
          disabled={disabled}
          className="ssn-input"
          autoComplete="off"
          autoFocus={autoFocus}
          maxLength={11} // XXX-XX-XXXX
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

      {helpText && !error && (
        <div className="ssn-input-help">{helpText}</div>
      )}

      {error && <div className="ssn-input-error">{error}</div>}
    </div>
  );
});

SSNInput.displayName = 'SSNInput';

export default SSNInput;
