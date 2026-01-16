/**
 * TextInput - Basic text input with label and validation
 */

import React, { forwardRef } from 'react';
import './TextInput.css';

const TextInput = forwardRef(({
  value = '',
  onChange,
  onBlur,
  placeholder = '',
  label,
  type = 'text',
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
  maxLength,
  autoComplete = 'off',
  autoFocus = false,
  inputMode,
  ...props
}, ref) => {
  const handleChange = (e) => {
    const newValue = e.target.value;
    if (maxLength && newValue.length > maxLength) return;
    onChange(newValue);
  };

  return (
    <div className={`text-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="text-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <input
        ref={ref}
        type={type}
        value={value || ''}
        onChange={handleChange}
        onBlur={onBlur}
        placeholder={placeholder}
        disabled={disabled}
        className="text-input"
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        inputMode={inputMode}
        maxLength={maxLength}
        {...props}
      />

      {helpText && !error && (
        <div className="text-input-help">{helpText}</div>
      )}

      {error && <div className="text-input-error">{error}</div>}
    </div>
  );
});

TextInput.displayName = 'TextInput';

export default TextInput;
