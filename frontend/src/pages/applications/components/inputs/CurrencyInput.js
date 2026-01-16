/**
 * CurrencyInput - Formatted currency input with $ prefix
 */

import React, { useState, useEffect, forwardRef } from 'react';
import './CurrencyInput.css';

// Format number as currency string
const formatCurrency = (value) => {
  if (value === null || value === undefined || value === '') return '';

  // Remove non-numeric characters except decimal
  const numericValue = String(value).replace(/[^0-9.]/g, '');

  // Parse as number
  const num = parseFloat(numericValue);
  if (isNaN(num)) return '';

  // Format with commas and 2 decimal places
  return num.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
};

// Parse currency string to number
const parseCurrency = (value) => {
  if (!value) return null;
  const num = parseFloat(String(value).replace(/[^0-9.]/g, ''));
  return isNaN(num) ? null : num;
};

const CurrencyInput = forwardRef(({
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
  min,
  max,
  autoFocus = false,
}, ref) => {
  const [displayValue, setDisplayValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);

  // Sync display value with external value
  useEffect(() => {
    if (!isFocused) {
      setDisplayValue(formatCurrency(value));
    }
  }, [value, isFocused]);

  const handleChange = (e) => {
    const input = e.target.value;

    // Remove $ and commas for processing
    const cleaned = input.replace(/[$,]/g, '');

    // Allow only numbers and one decimal point
    if (!/^[0-9]*\.?[0-9]*$/.test(cleaned)) return;

    // Update display
    setDisplayValue(cleaned);

    // Parse and notify parent
    const numericValue = parseCurrency(cleaned);

    // Check bounds
    if (numericValue !== null) {
      if (min !== undefined && numericValue < min) return;
      if (max !== undefined && numericValue > max) return;
    }

    onChange(numericValue);
  };

  const handleFocus = () => {
    setIsFocused(true);
    // Show raw number on focus for easier editing
    if (value) {
      setDisplayValue(String(value));
    }
  };

  const handleBlur = (e) => {
    setIsFocused(false);
    // Format on blur
    setDisplayValue(formatCurrency(value));
    if (onBlur) onBlur(e);
  };

  return (
    <div className={`currency-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="currency-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="currency-input-container">
        <span className="currency-symbol">$</span>
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
          className="currency-input"
          autoComplete="off"
          autoFocus={autoFocus}
        />
      </div>

      {helpText && !error && (
        <div className="currency-input-help">{helpText}</div>
      )}

      {error && <div className="currency-input-error">{error}</div>}
    </div>
  );
});

CurrencyInput.displayName = 'CurrencyInput';

export default CurrencyInput;
