/**
 * AddressInput - Wrapper around AddressAutocomplete for application flow
 */

import React from 'react';
import AddressAutocomplete from '../../../../components/AddressAutocomplete';
import './AddressInput.css';

const AddressInput = ({
  value = {},
  onChange,
  placeholder = 'Start typing an address...',
  label,
  required = false,
  disabled = false,
  error,
  helpText,
  className = '',
}) => {
  // Handle address selection
  const handleAddressSelect = (addressData) => {
    onChange({
      formatted: addressData.formatted || '',
      street: addressData.street || '',
      city: addressData.city || '',
      state: addressData.state || '',
      state_code: addressData.state_code || '',
      zip: addressData.zip || '',
      county: addressData.county || '',
      lat: addressData.lat,
      lng: addressData.lng,
    });
  };

  // Handle text change (for manual entry)
  const handleChange = (textValue) => {
    onChange({
      ...value,
      formatted: textValue,
    });
  };

  return (
    <div className={`address-input-wrapper ${className} ${error ? 'has-error' : ''}`}>
      {label && (
        <label className="address-input-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <AddressAutocomplete
        value={value?.formatted || ''}
        onChange={handleChange}
        onAddressSelect={handleAddressSelect}
        placeholder={placeholder}
        disabled={disabled}
        error={error}
      />

      {helpText && !error && (
        <div className="address-input-help">{helpText}</div>
      )}

      {/* Show parsed address details if available */}
      {value?.city && value?.state_code && (
        <div className="address-parsed">
          <span className="address-parsed-item">{value.city}, {value.state_code} {value.zip}</span>
        </div>
      )}
    </div>
  );
};

export default AddressInput;
