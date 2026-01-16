/**
 * PercentageInput - Percentage input with % suffix
 */

import React, { useState, useEffect, forwardRef } from 'react';
import './PercentageInput.css';

const PercentageInput = forwardRef(({
  value,
  onChange,
  onBlur,
  placeholder = '0',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
  min = 0,
  max = 100,
  decimals = 2,
  autoFocus = false,
}, ref) => {
  const [displayValue, setDisplayValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);

  // Sync display value with external value
  useEffect(() => {
    if (!isFocused && value !== null && value !== undefined) {
      setDisplayValue(String(value));
    }
  }, [value, isFocused]);

  const handleChange = (e) => {
    const input = e.target.value;

    // Allow only numbers and decimal point
    const cleaned = input.replace(/[^0-9.]/g, '');

    // Prevent multiple decimal points
    const parts = cleaned.split('.');
    let formatted = parts[0];
    if (parts.length > 1) {
      formatted += '.' + parts[1].slice(0, decimals);
    }

    setDisplayValue(formatted);

    // Parse and validate
    const numValue = parseFloat(formatted);

    if (isNaN(numValue)) {
      onChange(null);
    } else if (numValue >= min && numValue <= max) {
      onChange(numValue);
    }
  };

  const handleFocus = () => {
    setIsFocused(true);
  };

  const handleBlur = (e) => {
    setIsFocused(false);

    // Format on blur
    if (value !== null && value !== undefined) {
      setDisplayValue(String(value));
    }

    if (onBlur) onBlur(e);
  };

  return (
    <div className={`percentage-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="percentage-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="percentage-input-container">
        <input
          ref={ref}
          type="text"
          inputMode="decimal"
          value={displayValue}
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder={placeholder}
          disabled={disabled}
          className="percentage-input"
          autoComplete="off"
          autoFocus={autoFocus}
        />
        <span className="percentage-symbol">%</span>
      </div>

      {helpText && !error && (
        <div className="percentage-input-help">{helpText}</div>
      )}

      {error && <div className="percentage-input-error">{error}</div>}
    </div>
  );
});

PercentageInput.displayName = 'PercentageInput';

export default PercentageInput;
