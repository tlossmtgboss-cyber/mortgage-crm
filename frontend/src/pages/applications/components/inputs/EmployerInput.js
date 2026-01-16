/**
 * EmployerInput - Wrapper around EmployerAutocomplete for application flow
 */

import React from 'react';
import EmployerAutocomplete from '../../../../components/EmployerAutocomplete';
import './EmployerInput.css';

const EmployerInput = ({
  value = {},
  onChange,
  placeholder = 'Start typing employer name...',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
}) => {
  // Handle employer selection
  const handleEmployerSelect = (employerData) => {
    onChange({
      name: employerData.name || '',
      address: employerData.address || '',
      city: employerData.city || '',
      state: employerData.state || '',
      zip: employerData.zip || '',
      phone: employerData.phone || '',
    });
  };

  // Handle text change (for manual entry)
  const handleChange = (textValue) => {
    onChange({
      ...value,
      name: textValue,
    });
  };

  return (
    <div className={`employer-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="employer-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <EmployerAutocomplete
        value={value?.name || ''}
        onChange={handleChange}
        onEmployerSelect={handleEmployerSelect}
        placeholder={placeholder}
        disabled={disabled}
        error={error}
      />

      {helpText && !error && (
        <div className="employer-input-help">{helpText}</div>
      )}

      {/* Show employer details if available */}
      {value?.address && (
        <div className="employer-details">
          <span className="employer-details-item">{value.address}</span>
          {value.phone && (
            <span className="employer-details-item">Tel: {value.phone}</span>
          )}
        </div>
      )}
    </div>
  );
};

export default EmployerInput;
