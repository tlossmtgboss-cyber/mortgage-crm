import React from 'react';
import { formatPhoneNumber } from '../utils/phoneUtils';

/**
 * Phone input component with automatic (XXX) XXX-XXXX formatting
 */
const PhoneInput = ({
  value,
  onChange,
  placeholder = '(555) 555-5555',
  className = '',
  disabled = false,
  required = false,
  name = 'phone',
  id,
  ...props
}) => {
  const handleChange = (e) => {
    const formatted = formatPhoneNumber(e.target.value);
    onChange(formatted);
  };

  return (
    <input
      type="tel"
      id={id || name}
      name={name}
      value={value || ''}
      onChange={handleChange}
      placeholder={placeholder}
      className={className}
      disabled={disabled}
      required={required}
      autoComplete="tel"
      {...props}
    />
  );
};

export default PhoneInput;
